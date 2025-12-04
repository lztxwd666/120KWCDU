"""
IO控制功能类 - 独立模块，自动启动更新线程
用于控制输出IO的特殊功能，如LED灯等
"""

import threading
import time
from typing import Dict, Any


class IOControl:
    """
    IO控制类
    专门用于控制输出IO的特殊功能，如LED指示灯
    """

    # 类变量，确保单例和线程安全
    _instance = None
    _instance_lock = threading.Lock()
    _update_thread = None
    _running = False

    def __new__(cls, *args, **kwargs):
        """单例模式，确保全局只有一个IOControl实例"""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化IO控制类"""
        if hasattr(self, '_initialized') and self._initialized:
            return

        # 导入必要的模块（延迟导入，避免循环导入）
        from cdu120kw.control_logic.device_data_manipulation import (
            CONFIG_CACHE,
            processed_reg_map,
            COIL_WRITE_ENABLE,
            PUMP_DUTY_READ_START,
            PUMP_SPEED_START,
            PUMP_CURRENT_START,
            COIL_IO_OUTPUT_WRITE_START,
            batch_write_io_outputs
        )

        # 保存引用
        self._config_cache = CONFIG_CACHE
        self._processed_reg_map = processed_reg_map
        self._coil_write_enable = COIL_WRITE_ENABLE
        self._pump_duty_read_start = PUMP_DUTY_READ_START
        self._pump_speed_start = PUMP_SPEED_START
        self._pump_current_start = PUMP_CURRENT_START
        self._coil_io_output_write_start = COIL_IO_OUTPUT_WRITE_START
        self._batch_write_io_outputs = batch_write_io_outputs

        # LED灯的IO输出索引映射
        self.led_indices = self._find_led_indices()

        # 上次的LED状态，用于避免重复写入
        self.last_led_state = {}

        # 水泵索引（默认为第一个水泵）
        self.pump_index = 0

        self._initialized = True
        print(f"[IOControl] INFO: Initialized with LED indices: {self.led_indices}")

    def _find_led_indices(self) -> Dict[str, int]:
        """
        从配置文件中查找Y0、Y1、Y2对应的索引
        """
        led_indices = {}
        output_list = self._config_cache.get("output", [])

        for idx, output_cfg in enumerate(output_list):
            output_name = output_cfg.get("name", "").upper()

            # 根据名称匹配LED
            if "Y0" in output_name or "红灯" in output_name or "RED" in output_name:
                led_indices["red"] = idx
            elif "Y1" in output_name or "黄灯" in output_name or "YELLOW" in output_name:
                led_indices["yellow"] = idx
            elif "Y2" in output_name or "绿灯" in output_name or "GREEN" in output_name:
                led_indices["green"] = idx

        # 如果没有找到所有LED，使用默认索引
        if "red" not in led_indices and len(output_list) > 0:
            led_indices["red"] = 0
        if "yellow" not in led_indices and len(output_list) > 1:
            led_indices["yellow"] = 1
        if "green" not in led_indices and len(output_list) > 2:
            led_indices["green"] = 2

        return led_indices

    def is_pump_running(self, pump_index: int = None) -> bool:
        """
        判断水泵是否正在运行
        """
        try:
            # 使用传入的索引或默认索引
            index = pump_index if pump_index is not None else self.pump_index

            # 读取水泵占空比（放大100倍的值）
            duty_addr = self._pump_duty_read_start + index
            duty_cycle = self._processed_reg_map.get_register(duty_addr)

            # 读取水泵转速
            speed_addr = self._pump_speed_start + index
            speed = self._processed_reg_map.get_register(speed_addr)

            # 读取水泵电流（单位：mA）
            current_addr = self._pump_current_start + index
            current = self._processed_reg_map.get_register(current_addr)

            # 判断条件：占空比为0，转速小于500rpm，电流小于100mA
            # 注意：duty_cycle是放大100倍的值，所以0对应0%
            if duty_cycle == 0 and speed < 500 and current < 100:
                return False
            else:
                return True

        except Exception as e:
            print(f"[IOControl] ERROR: Failed to check pump status: {e}")
            return False

    def get_write_enable_status(self) -> bool:
        """
        获取写入使能状态
        """
        return self._processed_reg_map.get_coil(self._coil_write_enable) == 1

    def update_leds(self) -> None:
        """
        根据当前系统状态更新LED灯状态
        使用批量写入函数控制多个LED
        """
        try:
            # 获取写入使能状态
            write_enabled = self.get_write_enable_status()

            # 获取水泵运行状态
            pump_running = self.is_pump_running()

            # 根据逻辑确定LED状态
            led_states = {}

            # 红灯逻辑
            if "red" in self.led_indices:
                # 写入使能为0（系统待机）或水泵未启动时，红灯亮
                if not write_enabled or not pump_running:
                    led_states[self.led_indices["red"]] = 1
                else:
                    led_states[self.led_indices["red"]] = 0

            # 绿灯逻辑
            if "green" in self.led_indices:
                # 写入使能为1（系统启动）时，绿灯亮
                if write_enabled:
                    led_states[self.led_indices["green"]] = 1
                else:
                    led_states[self.led_indices["green"]] = 0

            # 黄灯逻辑
            if "yellow" in self.led_indices:
                led_states[self.led_indices["yellow"]] = 0

            # 检查LED状态是否有变化，避免重复写入
            state_changed = False
            for idx, state in led_states.items():
                if idx not in self.last_led_state or self.last_led_state[idx] != state:
                    state_changed = True
                    break

            # 如果状态有变化，使用批量写入函数更新LED
            if state_changed and led_states:
                self._batch_write_io_outputs(led_states, force=True)
                self.last_led_state = led_states.copy()

                # print(f"[IOControl] INFO: Updated LEDs - WriteEnable={write_enabled}, "
                #       f"PumpRunning={pump_running}")

        except Exception as e:
            print(f"[IOControl] ERROR: Failed to update LEDs: {e}")

    def start_update_thread(self, interval: float = 0.5) -> bool:
        """
        启动IO控制更新线程

        Args:
            interval: 更新间隔，单位秒

        Returns:
            bool: 是否成功启动
        """
        with self._instance_lock:
            if self._running:
                print("[IOControl] WARNING: Update thread already running")
                return False

            self._running = True

            def update_loop():
                """IO控制更新循环"""
                while self._running:
                    try:
                        self.update_leds()
                    except Exception as e:
                        print(f"[IOControl] ERROR in update loop: {e}")

                    # 等待指定间隔
                    time.sleep(interval)

                print("[IOControl] INFO: Update thread stopped")

            # 创建并启动更新线程
            self._update_thread = threading.Thread(
                target=update_loop,
                daemon=True,
                name="IOControlUpdate"
            )
            self._update_thread.start()

            print(f"[IOControl] INFO: Update thread started with interval {interval}s")
            return True

    def stop_update_thread(self) -> None:
        """
        停止IO控制更新线程
        """
        with self._instance_lock:
            if not self._running:
                return

            self._running = False

            # 等待线程结束
            if self._update_thread and self._update_thread.is_alive():
                self._update_thread.join(timeout=2)
                print("[IOControl] INFO: Update thread stopped")

    def is_running(self) -> bool:
        """
        检查更新线程是否在运行

        Returns:
            bool: 线程运行状态
        """
        return self._running

    # 其他方法保持不变...
    def set_led_manual(self, led_name: str, state: int) -> bool:
        """手动设置LED状态"""
        # 原有实现...
        pass

    def get_led_status(self) -> Dict[str, Any]:
        """获取当前LED状态信息"""
        # 原有实现...
        pass


# 创建全局IO控制实例
io_control = IOControl()


def start_io_control(interval: float = 0.5) -> bool:
    """
    启动IO控制模块

    Args:
        interval: 更新间隔，单位秒

    Returns:
        bool: 是否成功启动
    """
    return io_control.start_update_thread(interval)


def stop_io_control() -> None:
    """
    停止IO控制模块
    """
    io_control.stop_update_thread()


def get_io_control() -> IOControl:
    """
    获取IO控制实例

    Returns:
        IOControl: IO控制实例
    """
    return io_control
