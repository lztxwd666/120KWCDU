"""
PID自动控制模块
实现基于流量、温度、压差的复合自动控制逻辑
"""

import threading
import time

from cdu120kw.control_logic.device_data_manipulation import (
    processed_reg_map, CONTROL_MODE, CONTROL_MODE_TARGET_FLOW_REGISTER,
    CONTROL_MODE_TARGET_TEMP_REGISTER, CONTROL_MODE_TARGET_PRESSUREDIFF_REGISTER,
    FLOW_VALUE_START, TEMP_VALUE_START, PRESS_DIFF_START,
    batch_write_pump_duty, batch_write_pv_duty, COIL_WRITE_ENABLE, CONFIG_CACHE, PUMP_CURRENT_START,
    PUMP_DUTY_READ_START, PUMP_SPEED_START
)
from cdu120kw.control_logic.pid_helper import PidHelper


class AutoControlManager:
    """
    自动控制管理器
    负责管理三种复合自动控制模式：
    - 模式3: 流量模式（只控制流量，调节水泵）
    - 模式2: 流量温度模式（控制流量和温度，流量用水泵，温度用比例阀）
    - 模式4: 压差温度模式（控制压差和温度，压差用水泵，温度用比例阀）
    """

    def __init__(self):
        # PID控制器实例
        self.flow_pid = PidHelper.create_from_cache("pid_pump")      # 流量控制PID（控制水泵）
        self.temp_pid = PidHelper.create_from_cache("pid_pv")        # 温度控制PID（控制比例阀）
        self.pressure_pid = PidHelper.create_from_cache("pid_pump")  # 压差控制PID（控制水泵）

        # 控制状态
        self.last_pump_duty = 0  # 上一次的水泵占空比
        self.last_pv_duty = 10000    # 上一次的比例阀占空比
        self.is_running = False
        self.control_thread = None

        # 添加中断标志和锁
        self._stop_requested = False
        self._stop_lock = threading.Lock()

        # 模式切换状态,用于设置切换模式设置比例阀的初始值
        self._mode_switch_in_progress = False  # 模式切换进行中标志
        self._mode_switch_lock = threading.Lock()  # 模式切换锁

        # 水泵启动状态管理
        self._pump_startup_state = "idle"  # idle, checking, starting, ready, failed
        self._pump_startup_start_time = 0
        self._pump_startup_check_count = 0
        self._initial_pump_duty_set = False
        self._pump_startup_conditions_met_time = 0
        self._pump_startup_lock = threading.Lock()

        # 注册控制模式变化回调和写入使能变化回调
        processed_reg_map.write_register_callback(self._on_control_mode_change)
        processed_reg_map.write_coil_callback(self._on_write_enable_change)

        # 获取水泵数量
        self.pump_count = len(CONFIG_CACHE.get("pumps", []))

    def _on_control_mode_change(self, address: int, value: int):
        """
        控制模式寄存器变化回调
        当HMI写入控制模式寄存器时自动触发
        """
        if address == CONTROL_MODE:
            control_mode = value
            write_enable = processed_reg_map.get_coil(COIL_WRITE_ENABLE)

            # print(f"[AutoControl] DEBUG: Control mode callback triggered - addr={address}, value={value}, write_enable={write_enable}")

            # 任何模式切换都需要将比例阀设置为100%开度
            self._set_pv_to_100_percent_for_mode_switch()

            # 模式1：手动模式，停止自动调节，保持当前值
            if control_mode == 1:
                print("[AutoControl] INFO: Manual mode - stopping auto control, maintaining current duty")
                self.stop_auto_control()
            # 模式2/3/4：自动模式，只有在写入使能为1时才启动
            elif control_mode in [2, 3, 4]:
                if write_enable == 1:
                    print(f"[AutoControl] INFO: Auto mode {control_mode} detected - starting auto control")
                    self.start_auto_control()
                else:
                    print(f"[AutoControl] WARNING: Auto mode {control_mode} detected but write enable=0 - cannot start")
            else:
                print(f"[AutoControl] WARNING: Unknown control mode: {control_mode}")
                self.stop_auto_control()

    def _on_write_enable_change(self, address: int, value: int):
        """
        写入使能寄存器变化回调
        当写入使能变为0时立即请求停止自动控制
        """
        if address == COIL_WRITE_ENABLE:
            write_enable = value
            control_mode = processed_reg_map.get_register(CONTROL_MODE)

            # print(f"[AutoControl] DEBUG: Write enable callback triggered - addr={address}, value={value}, control_mode={control_mode}")

            # 写入使能变为0时立即请求停止
            if write_enable == 0:
                # print("[AutoControl] INFO: Write enable=0 - requesting immediate stop")
                self._request_stop()
            elif write_enable == 1 and control_mode in [2, 3, 4]:
                print(f"[AutoControl] INFO: Write enable=1 and auto mode {control_mode} - starting auto control")
                self.start_auto_control()

    def _request_stop(self):
        """请求立即停止控制线程"""
        with self._stop_lock:
            self._stop_requested = True
        self.stop_auto_control()

    def _should_continue(self) -> bool:
        """检查是否应该继续执行控制操作"""
        with self._stop_lock:
            if self._stop_requested:
                return False
        return self.is_running

    def _set_pv_to_100_percent_for_mode_switch(self):
        """
        模式切换时设置比例阀为100%开度
        """
        with self._mode_switch_lock:
            if self._mode_switch_in_progress:
                return

            self._mode_switch_in_progress = True
            try:
                # 设置比例阀占空比为10000（100%）
                success = batch_write_pv_duty(10000, force=True)
                if success:
                    self.last_pv_duty = 10000
                    # print("[AutoControl] INFO: PV duty set to 10000 (100%) for mode switching")
                else:
                    print("[AutoControl] WARNING: Failed to set PV duty to 10000 for mode switching")
            except Exception as e:
                print(f"[AutoControl] ERROR: Failed to set PV duty to 10000: {e}")
            finally:
                self._mode_switch_in_progress = False


    def start_auto_control(self):
        """启动自动控制线程"""
        if self.is_running:
            print("[AutoControl] DEBUG: Auto control already running")
            return

        # 双重检查写入使能状态和控制模式
        write_enable = processed_reg_map.get_coil(COIL_WRITE_ENABLE)
        control_mode = processed_reg_map.get_register(CONTROL_MODE)

        if write_enable != 1:
            print(f"[AutoControl] WARNING: Cannot start auto control - write enable={write_enable}")
            return

        if control_mode not in [2, 3, 4]:
            print(f"[AutoControl] WARNING: Cannot start auto control - invalid control mode={control_mode}")
            return

        # 启动自动控制前，确保比例阀设置为100%
        self._set_pv_to_100_percent_for_mode_switch()

        # 重置停止请求标志
        with self._stop_lock:
            self._stop_requested = False

        # 重置水泵启动状态
        with self._pump_startup_lock:
            self._pump_startup_state = "checking"
            self._pump_startup_start_time = time.time()
            self._pump_startup_check_count = 0
            self._initial_pump_duty_set = False
            self._pump_startup_conditions_met_time = 0

        self.is_running = True
        self.control_thread = threading.Thread(
            target=self._auto_control_loop,
            daemon=True,
            name="AutoControl"
        )
        self.control_thread.start()
        print(f"[AutoControl] INFO: Auto control started for mode {control_mode} with {self.pump_count} pumps")


    def stop_auto_control(self):
        """停止机制，确保线程安全"""
        if not self.is_running:
            return

        # 立即设置停止标志
        self.is_running = False
        with self._stop_lock:
            self._stop_requested = True

        # 重置水泵启动状态
        with self._pump_startup_lock:
            self._pump_startup_state = "idle"

        # 尝试停止
        if self.control_thread and self.control_thread.is_alive():
            self.control_thread.join(timeout=2.0)  # 适当延长超时

            # 如果仍然存活，记录错误但不阻塞
            if self.control_thread.is_alive():
                print("[AutoControl] ERROR: Control thread failed to stop gracefully")
                # 不设置为None，避免线程泄露
                # 让线程自然结束或在下一次启动时处理

        print(f"[AutoControl] INFO: Auto control stopped")


    def _auto_control_loop(self):
        """自动控制主循环"""
        print("[AutoControl] DEBUG: Auto control loop started")

        loop_count = 0
        while self._should_continue():
            try:
                loop_count += 1
                loop_start_time = time.time()  # 记录循环开始时间

                # 在每个关键步骤前检查退出条件
                if not self._should_continue():
                    break

                # 新增：检查水泵启动状态
                if not self._check_pump_startup_state():
                    # 水泵未准备好，等待下一次循环
                    time.sleep(0.5)  # 缩短等待时间以便更快响应
                    continue

                control_mode = processed_reg_map.get_register(CONTROL_MODE)

                # # 每5个循环打印一次调试信息
                # if loop_count % 5 == 0:
                #     print(f"[AutoControl] DEBUG: Control loop running (cycle {loop_count}), mode={control_mode}")

                # 模式处理逻辑
                if control_mode == 3:  # 流量模式
                    if not self._flow_only_control():
                        break
                elif control_mode == 2:  # 流量温度模式
                    if not self._flow_temp_control():
                        break
                elif control_mode == 4:  # 压差温度模式
                    if not self._pressure_temp_control():
                        break
                else:
                    # 未知模式，停止控制
                    print(f"[AutoControl] WARNING: Unknown control mode in loop: {control_mode}")
                    break

                # 使用PID配置中的dt作为采样周期
                loop_end_time = time.time()
                loop_duration = loop_end_time - loop_start_time

                # 使用flow_pid的dt（只适用于所有PID实例的dt相同）
                dt_target = self.flow_pid.dt
                sleep_time = max(0, dt_target - loop_duration)

                # 将睡眠时间拆分为小段，允许更频繁的中断检查
                chunk_size = 0.1  # 每0.1秒检查一次
                num_chunks = max(1, int(sleep_time / chunk_size))
                for i in range(num_chunks):
                    if not self._should_continue():
                        break
                    remaining_sleep = sleep_time - i * chunk_size
                    time.sleep(min(chunk_size, remaining_sleep))

            except Exception as e:
                print(f"[AutoControl] ERROR: Auto control loop error: {e}")
                # 错误时也使用PID的dt作为睡眠间隔
                dt_target = self.flow_pid.dt
                chunk_size = 0.1
                num_chunks = max(1, int(dt_target / chunk_size))
                for i in range(num_chunks):
                    if not self._should_continue():
                        break
                    time.sleep(chunk_size)

        print("[AutoControl] DEBUG: Auto control loop ended")


    def _check_pump_startup_state(self) -> bool:
        """
        检查水泵启动状态，返回True表示可以开始PID调节
        """
        with self._pump_startup_lock:
            current_state = self._pump_startup_state

        # 如果已经准备就绪，直接返回True
        if current_state == "ready":
            return True

        # 如果启动失败，返回False（停止控制循环）
        if current_state == "failed":
            print("[AutoControl] ERROR: Pump startup failed - stopping auto control")
            self.stop_auto_control()
            return False

        # 检查超时（30秒超时）
        if time.time() - self._pump_startup_start_time > 30:
            print("[AutoControl] ERROR: Pump startup timeout - stopping auto control")
            with self._pump_startup_lock:
                self._pump_startup_state = "failed"
            self.stop_auto_control()
            return False

        # 执行启动检查逻辑
        return self._execute_pump_startup_sequence()

    def _execute_pump_startup_sequence(self) -> bool:
        """
        执行水泵启动序列
        """
        with self._pump_startup_lock:
            current_state = self._pump_startup_state

        # 状态1: checking - 检查水泵当前状态
        if current_state == "checking":
            return self._check_initial_pump_state()

        # 状态2: starting - 监测启动条件
        elif current_state == "starting":
            return self._monitor_pump_startup()

        # 其他状态返回False
        return False

    def _check_initial_pump_state(self) -> bool:
        """
        检查水泵初始状态
        """
        try:
            # 读取第一个水泵的占空比作为代表（所有水泵批量控制，状态相同）
            pump_duty = processed_reg_map.get_register(PUMP_DUTY_READ_START)

            # 如果占空比 > 5%，说明水泵已经启动
            if pump_duty > 500:  # 500 = 5%
                # 检查是否满足启动条件
                if self._check_pump_conditions():
                    # print("[AutoControl] INFO: Pump already running with duty > 5% - starting PID immediately")
                    with self._pump_startup_lock:
                        self._pump_startup_state = "ready"
                    return True
                else:
                    # print("[AutoControl] INFO: Pump duty > 5% but conditions not met - continuing startup check")
                    with self._pump_startup_lock:
                        self._pump_startup_state = "starting"
                    return False

            # 如果占空比 <= 5%，设置最低占空比
            else:
                # print("[AutoControl] INFO: Pump duty <= 5% - setting minimum duty cycle (5%)")
                # 批量写入所有水泵最低占空比
                success = batch_write_pump_duty(1000, force=True)  # 1000 = 10%
                if success:
                    with self._pump_startup_lock:
                        self._pump_startup_state = "starting"
                        self._initial_pump_duty_set = True
                    # print("[AutoControl] INFO: Minimum pump duty (10%) set successfully")
                else:
                    print("[AutoControl] ERROR: Failed to set minimum pump duty")
                return False

        except Exception as e:
            print(f"[AutoControl] ERROR: Error checking initial pump state: {e}")
            return False

    def _monitor_pump_startup(self) -> bool:
        """
        监测水泵启动过程
        """
        try:
            # 检查启动条件
            conditions_met = self._check_pump_conditions()

            if conditions_met:
                current_time = time.time()
                with self._pump_startup_lock:
                    # 第一次满足条件，记录时间
                    if self._pump_startup_conditions_met_time == 0:
                        self._pump_startup_conditions_met_time = current_time
                        # print("[AutoControl] INFO: Pump startup conditions met - starting 2s delay")
                        return False

                    # 检查是否已经满足条件4秒
                    elif current_time - self._pump_startup_conditions_met_time >= 4:
                        self._pump_startup_state = "ready"
                        # print("[AutoControl] INFO: Pump startup completed - starting PID control")
                        return True
                    else:
                        # 还在等待4秒延时
                        remaining = 4 - (current_time - self._pump_startup_conditions_met_time)
                        # print(f"[AutoControl] DEBUG: Waiting {remaining:.1f}s before PID start")
                        return False
            else:
                # 条件不满足，重置计时器
                with self._pump_startup_lock:
                    self._pump_startup_conditions_met_time = 0
                return False

        except Exception as e:
            print(f"[AutoControl] ERROR: Error monitoring pump startup: {e}")
            return False

    def _check_pump_conditions(self) -> bool:
        """
        检查水泵启动条件
        返回True如果所有水泵都满足条件
        """
        try:
            # 检查所有水泵的电流和转速
            all_conditions_met = True

            for i in range(self.pump_count):
                # 读取电流（转换为实际值）
                current_addr = PUMP_CURRENT_START + i
                current_raw = processed_reg_map.get_register(current_addr)
                # 将U16转换为有符号整数
                if current_raw >= 0x8000:
                    current_raw -= 0x10000
                current_actual = current_raw  # 根据实际情况可能需要转换

                # 读取转速
                speed_addr = PUMP_SPEED_START + i
                speed = processed_reg_map.get_register(speed_addr)

                # print(f"[AutoControl] DEBUG: Pump {i} - current raw: {current_raw}, actual: {current_actual}, speed: {speed}")

                # 检查条件：电流 > 0.1A (100) 且转速 > 500 RPM  【120kw的水泵低电流极不稳定，因此排除该判定项，只使用转速判定】
                # current_ok = current_actual > 100
                speed_ok = speed > 500

                if not speed_ok:
                    all_conditions_met = False
                    # print(f"[AutoControl] DEBUG: Pump {i} conditions - current: {current_actual}A (need >10), speed: {speed}RPM (need >500)")
                    break

            return all_conditions_met

        except Exception as e:
            print(f"[AutoControl] ERROR: Error checking pump conditions: {e}")
            return False

    def _flow_only_control(self) -> bool:
        """模式3: 流量模式"""
        try:
            # 在每个步骤前检查退出条件
            if not self._should_continue():
                return False

            # 获取目标流量
            target_flow = processed_reg_map.get_register(CONTROL_MODE_TARGET_FLOW_REGISTER)

            # 获取当前实际流量F2（索引1）
            current_flow = processed_reg_map.get_register(FLOW_VALUE_START + 1)

            # 将 U16 转换为有符号整数
            if current_flow >= 0x8000:  # 判断是否为负数
                current_flow -= 0x10000

            # 将寄存器值转换为实际物理值
            target_flow_physical = target_flow / 10.0
            current_flow_physical = current_flow / 10.0

            # 流量PID计算（水泵控制）
            new_pump_duty = self.flow_pid.calculate(
                target_value=target_flow_physical,
                measured_value=current_flow_physical,
                last_set_var=self.last_pump_duty,
                is_add=True  # 正向控制：流量低于目标时增加占空比
            )

            # 限制占空比范围（0-100对应0%-100%）
            new_pump_duty = max(0, min(100, new_pump_duty))

            # 更新上一次占空比
            self.last_pump_duty = new_pump_duty

            # 在写入前再次检查退出条件
            if not self._should_continue():
                return False

            # 应用新的水泵占空比（批量写入所有水泵）
            self._apply_pump_duty(new_pump_duty)

            return True

        except Exception as e:
            print(f"[AutoControl] ERROR: Flow only control error: {e}")
            return True  # 错误时继续执行

    def _flow_temp_control(self) -> bool:
        """模式2: 流量温度模式"""
        try:
            # 在每个步骤前检查退出条件
            if not self._should_continue():
                return False

            # 获取目标值
            target_flow = processed_reg_map.get_register(CONTROL_MODE_TARGET_FLOW_REGISTER)
            target_temp = processed_reg_map.get_register(CONTROL_MODE_TARGET_TEMP_REGISTER)

            # 获取当前实际值
            current_flow = processed_reg_map.get_register(FLOW_VALUE_START + 1)  # F2
            current_temp = processed_reg_map.get_register(TEMP_VALUE_START + 3)  # T4温度传感器

            # 将 U16 转换为有符号整数
            if current_flow >= 0x8000:  # 判断是否为负数
                current_flow -= 0x10000

            # 转换为物理值
            target_flow_physical = target_flow / 10.0
            current_flow_physical = current_flow / 10.0
            target_temp_physical = target_temp / 10.0
            current_temp_physical = current_temp / 10.0

            # 流量PID计算（水泵控制）
            new_pump_duty = self.flow_pid.calculate(
                target_value=target_flow_physical,
                measured_value=current_flow_physical,
                last_set_var=self.last_pump_duty,
                is_add=True  # 正向控制
            )
            new_pump_duty = max(0, min(100, new_pump_duty))
            self.last_pump_duty = new_pump_duty

            # 温度PID计算（比例阀控制）
            new_pv_duty = self.temp_pid.calculate(
                target_value=target_temp_physical,
                measured_value=current_temp_physical,
                last_set_var=self.last_pv_duty,
                is_add=False  # 反向控制：温度高于目标时增加比例阀开度
            )
            new_pv_duty = max(0, min(100, new_pv_duty))
            self.last_pv_duty = new_pv_duty

            # 在写入前再次检查退出条件
            if not self._should_continue():
                return False

            # 应用控制输出
            self._apply_pump_duty(new_pump_duty)
            self._apply_pv_duty(new_pv_duty)

            return True

        except Exception as e:
            print(f"[AutoControl] ERROR: Flow-Temp control error: {e}")
            return True  # 错误时继续执行

    def _pressure_temp_control(self) -> bool:
        """模式4: 压差温度模式"""
        try:
            # 在每个步骤前检查退出条件
            if not self._should_continue():
                return False

            # 获取目标值
            target_pressure = processed_reg_map.get_register(CONTROL_MODE_TARGET_PRESSUREDIFF_REGISTER)
            target_temp = processed_reg_map.get_register(CONTROL_MODE_TARGET_TEMP_REGISTER)

            # 获取当前实际值
            current_pressure = processed_reg_map.get_register(PRESS_DIFF_START + 0)  # 压差
            current_temp = processed_reg_map.get_register(TEMP_VALUE_START + 3)      # T4温度

            # 将 U16 转换为有符号整数
            if current_pressure >= 0x8000:  # 判断是否为负数
                current_pressure -= 0x10000

            # 转换为物理值
            target_pressure_physical = target_pressure / 10.0
            current_pressure_physical = current_pressure / 10.0
            target_temp_physical = target_temp / 10.0
            current_temp_physical = current_temp / 10.0

            print(f"[AutoControl] DEBUG: Pressure-Temp control - Pressure Target: {target_pressure_physical:.3f}MPa, Actual: {current_pressure_physical:.3f}MPa, "
                  f"Temp Target: {target_temp_physical:.1f}°C, Actual: {current_temp_physical:.1f}°C")

            # 压差PID计算（水泵控制）
            new_pump_duty = self.pressure_pid.calculate(
                target_value=target_pressure_physical,
                measured_value=current_pressure_physical,
                last_set_var=self.last_pump_duty,
                is_add=True  # 正向控制：压差低于目标时增加占空比
            )
            new_pump_duty = max(0, min(100, new_pump_duty))
            self.last_pump_duty = new_pump_duty

            # 温度PID计算（比例阀控制）
            new_pv_duty = self.temp_pid.calculate(
                target_value=target_temp_physical,
                measured_value=current_temp_physical,
                last_set_var=self.last_pv_duty,
                is_add=False  # 反向控制
            )
            new_pv_duty = max(0, min(100, new_pv_duty))
            self.last_pv_duty = new_pv_duty

            # 在写入前再次检查退出条件
            if not self._should_continue():
                return False

            # 应用控制输出
            self._apply_pump_duty(new_pump_duty)
            self._apply_pv_duty(new_pv_duty)

            return True

        except Exception as e:
            print(f"[AutoControl] ERROR: Pressure-Temp control error: {e}")
            return True  # 错误时继续执行

    def _apply_pump_duty(self, duty: int):
        """
        应用水泵占空比到所有水泵，确保在有效状态下执行写入
        """
        try:
            # 检查是否应该执行写入
            if not self._should_continue():
                print(f"[AutoControl] DEBUG: Skip pump duty write - stop requested")
                return

            success = batch_write_pump_duty(duty * 100, force=False)

        except Exception as e:
            print(f"[AutoControl] ERROR: Apply pump duty error: {e}")

    def _apply_pv_duty(self, duty: int):
        """
        应用比例阀占空比，确保在有效状态下执行写入
        """
        try:
            # 检查是否应该执行写入
            if not self._should_continue():
                print(f"[AutoControl] DEBUG: Skip PV duty write - stop requested")
                return

            success = batch_write_pv_duty(duty * 100, force=False)

        except Exception as e:
            print(f"[AutoControl] ERROR: Apply PV duty error: {e}")

auto_control_manager = AutoControlManager()

def initialize_auto_control():
    """初始化自动控制系统"""

    # 确保启动时处于手动模式
    current_mode = processed_reg_map.get_register(CONTROL_MODE)
    if current_mode == 0:  # 如果控制模式未设置，设置为手动模式
        processed_reg_map.set_register(CONTROL_MODE, 1)
        print("[AutoControl] INFO: Set default control mode to manual (1)")

    # 检查当前控制模式和写入使能状态
    current_mode = processed_reg_map.get_register(CONTROL_MODE)
    write_enable = processed_reg_map.get_coil(COIL_WRITE_ENABLE)

    # 只有在写入使能为1且控制模式为2/3/4时才启动自动控制
    if write_enable == 1 and current_mode in [2, 3, 4]:
        auto_control_manager.start_auto_control()
        print(f"[AutoControl] INFO: Auto control auto-started for mode {current_mode}")
    else:
        # 记录为什么不启动
        if write_enable != 1:
            print(f"[AutoControl] INFO: Auto control not started - write enable is {write_enable} (required: 1)")
        elif current_mode not in [2, 3, 4]:
            print(f"[AutoControl] INFO: Auto control not started - control mode is {current_mode} (required: 2,3,4)")
        else:
            print(f"[AutoControl] INFO: Auto control not started - mode: {current_mode}, write_enable: {write_enable}")

    print("[AutoControl] DEBUG: Auto control system initialization completed")
