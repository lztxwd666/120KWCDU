"""
组件操作任务管理器
- 支持批量写入PCBA寄存器（线圈/保持寄存器）
- 支持TCP/RTU自动切换
- 支持优先级插队写入
- 支持最小/最大占空比自动夹取
- 支持全局配置缓存（单路径只加载与预处理一次）
"""

import os
import threading
import time
from typing import Dict, Tuple, Optional

from cdu120kw.config.config_repository import (
    ConfigRepository,
    ComponentTaskParamManager,
    ComponentTaskParam,
)
from cdu120kw.modbus_manager.batch_writer import ModbusBatchWriter
from cdu120kw.task.task_queue import BasePollingTaskManager


def to_u16(value: int) -> int:
    """
    转U16（两补码），保证写保持寄存器是无符号16位
    """
    try:
        iv = int(value)
    except (ValueError, TypeError):
        iv = 0
    return iv & 0xFFFF

class ComponentOperationTaskManager(BasePollingTaskManager):
    """
    组件操作任务管理器（直接批量写入PCBA；支持优先级插队；TCP/RTU自动切换；内部重试与断线重连）
    - 使用全局缓存的配置与可写字段预映射
    - 保持寄存器写入采用U16（两补码）
    - 支持最小/最大占空比自动夹取（若配置存在）
    """

    def __init__(
        self,
        tcp_manager,
        config_path: str,
        mapping_task_manager=None,
        pool_workers=2,
        rtu_manager=None,
        tcp_reconnect_mgr=None,
        rtu_reconnect_mgr=None,
    ):
        super().__init__(pool_workers=pool_workers)
        self.tcp_manager = tcp_manager
        self.rtu_manager = rtu_manager
        self.tcp_writer = ModbusBatchWriter(self.tcp_manager)
        self.rtu_writer = ModbusBatchWriter(self.rtu_manager) if self.rtu_manager else None
        self.current_mode = "none"  # 启动由update_mode判定
        self.param_mgr: Optional[ComponentTaskParamManager] = None
        self.lock = threading.Lock()
        self.tcp_reconnect_mgr = tcp_reconnect_mgr
        self.rtu_reconnect_mgr = rtu_reconnect_mgr
        self.config_path = config_path
        self.mapping_task_manager = mapping_task_manager
        self.accept_new_task = False
        self.last_write_values: Dict[Tuple[str, int, int, str], int] = {}
        self._mode_watchdog_thread = None
        self._mode_watchdog_stop = threading.Event()

        if config_path and os.path.exists(config_path):
            self.load_tasks(config_path)

        # 初始化后立刻判定模式并启动监控线程
        self.update_mode()
        self._start_mode_watchdog()

    def load_tasks(self, config_path: str):
        # 使用统一仓库，复用预映射好的组件参数管理器
        repo = ConfigRepository.load(config_path)
        self.param_mgr = repo.component_params
        print(f"[ComponentOperationTask] INFO: Loaded component operation task")

    @staticmethod
    def _pick_first_writable(param: "ComponentTaskParam", value_dict: dict):
        for field, value in value_dict.items():
            meta = param.writable_fields.get(field)
            if meta:
                write_type, address, decimals, rng = meta
                return field, write_type, address, decimals, rng, value
        return None, None, None, None, (None, None), None

    def _start_mode_watchdog(self):
        """
        启动模式监视线程
        监视TCP/RTU连接状态，自动切换写入模式
        """
        if self._mode_watchdog_thread and self._mode_watchdog_thread.is_alive():
            return
        def _watchdog():
            while not self._mode_watchdog_stop.is_set():
                try:
                    self.update_mode()
                except Exception as e:
                    print(f"[ComponentOperationTask] ERROR: Mode watchdog exception: {e}")
                time.sleep(0.2)
        self._mode_watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
        self._mode_watchdog_thread.start()

    def update_mode(self):
        with self.lock:
            tcp_ok = self.tcp_manager.is_connected()
            rtu_ok = self.rtu_manager.is_connected() if self.rtu_manager else False
            prev_mode = self.current_mode

            if tcp_ok:
                self.current_mode = "tcp"
                self.accept_new_task = True
                self.resume()
            elif rtu_ok:
                # 从 tcp 切到 rtu 时，强制关闭 TCP 打断可能的阻塞写
                if prev_mode == "tcp":
                    with self.tcp_manager.connection_lock:
                        if getattr(self.tcp_manager, "client", None):
                            try:
                                self.tcp_manager.client.close()
                            except Exception as e:
                                print(f"[ComponentOperationTask] WARNING: Force close TCP failed: {e}")
                            self.tcp_manager.connected = False
                self.current_mode = "rtu"
                self.accept_new_task = True
                self.resume()
            else:
                # 两者都不可用：切到 none 并暂停；若从 tcp 来，亦强制关闭 TCP
                if prev_mode == "tcp":
                    with self.tcp_manager.connection_lock:
                        if getattr(self.tcp_manager, "client", None):
                            try:
                                self.tcp_manager.client.close()
                            except Exception as e:
                                print(f"[ComponentOperationTask] WARNING: Force close TCP failed: {e}")
                            self.tcp_manager.connected = False
                self.current_mode = "none"
                self.accept_new_task = False
                self.pause()

            if self.current_mode != prev_mode:
                print(f"[ComponentOperationTask] INFO: Switch hosted mode: {prev_mode} -> {self.current_mode}")

    def on_pause_check(self):
        # 暂停期间也轮询模式，便于连接恢复后立刻继续写
        self.update_mode()

    def operate_component(self, name: str, value_dict: dict, slave: int = 1, priority: int = 0):
        """
        触发写入（默认最高优先级0插队）
        value_dict: 传递具体可写字段，如 {"rw_d_duty_register_address": 123}
        """
        self.update_mode()
        with self.lock:
            if not self.accept_new_task:
                print("[ComponentOperationTask] WARNING: Communication offline, reject new write task")
                return "Communication offline, reject new write task"
            if not self.param_mgr:
                return "Param manager not initialized"
            param = self.param_mgr.get_param(name)
            if not param or not param.enabled:
                return "Component not found or disabled"

            field, write_type, address, decimals, rng, value = self._pick_first_writable(param, value_dict)
            if write_type is None or address is None:
                return "No valid writable address"

            # 占空比/范围夹取（若配置提供 min/max）
            min_v, max_v = rng if isinstance(rng, tuple) else (None, None)
            try:
                ivalue = int(value)
            except (ValueError, TypeError):
                ivalue = 0

            # 根据占空比的小数位进行动态放大（仅对 duty 字段生效）
            scale = 1
            duty_decimals = int(decimals or 0)
            # 识别占空比字段：rw_d_duty*
            if write_type == "register" and isinstance(field, str) and "rw_d_duty" in field:
                if duty_decimals == 0:
                    # 预映射未取到时，回退到配置中的 rw_d_duty_decimals
                    try:
                        duty_decimals = int(param.config.get("rw_d_duty_decimals", 0) or 0)
                    except (ValueError, TypeError):
                        duty_decimals = 0
                if duty_decimals > 0:
                    scale = 10 ** duty_decimals

            # 进行按 scale 后的范围夹取
            if min_v is not None:
                ivalue = max(ivalue, int(min_v * scale))
            if max_v is not None:
                ivalue = min(ivalue, int(max_v * scale))
            # 写入值规整
            if write_type == "coil":
                write_value = 1 if int(ivalue) else 0
            else:
                write_value = to_u16(ivalue)

            # 去重：相同地址与相同值则跳过
            last_key = (write_type, address, int(slave), self.current_mode)
            if self.last_write_values.get(last_key) == write_value:
                # print(f"[ComponentOperationTask] INFO: Skip write: {name}, type={write_type}, addr={address}, value={write_value}, (Same as last time)")
                return "Skip write: value not changed"
            self.last_write_values[last_key] = write_value

            # # 提交写入任务日志
            # print(f"[ComponentOperationTask] INFO: Submit write task: {name}, type={write_type}, addr={address}, value={write_value}, priority={priority}")
            self.task_queue.put_task(
                func=self.execute_write,
                args=(param, write_value, slave, address, write_type),
                priority=priority if isinstance(priority, int) else 0,
            )
            return "Write task submitted"

    def execute_write(self, param: ComponentTaskParam, value: int, slave: int, address: int, write_type: str):
        """
        实际写入PCBA寄存器，失败内部重试3次；无可用连接返回False交由调度层等待恢复
        """
        try:
            retry = 0
            while retry < 3:
                self.update_mode()
                self.wait_if_paused()
                writer = self.tcp_writer if self.current_mode == "tcp" else self.rtu_writer
                manager = self.tcp_manager if self.current_mode == "tcp" else self.rtu_manager
                reconnect_mgr = self.tcp_reconnect_mgr if self.current_mode == "tcp" else self.rtu_reconnect_mgr
                if not writer:
                    print("[ComponentOperationTask] WARNING: No Modbus connection available, skip write task")
                    return False

                if write_type == "coil":
                    err = writer.write_coils(address, [value], slave=slave)
                else:
                    # 保持寄存器确保为U16
                    err = writer.write_registers(address, [to_u16(value)], slave=slave)

                # 检查写入结果，无错误则退出重试
                if not err:
                    # print(f"[ComponentOperationTask] INFO: Write success: {param.name}, addr {address}, value={value}")
                    break
                else:
                    print(f"[ComponentOperationTask] WARNING: Write {write_type} failed: {param.name}, addr {address}, error: {err}")
                    if manager and hasattr(manager, "connection_lock"):
                        with manager.connection_lock:
                            manager.connected = False
                    if reconnect_mgr and reconnect_mgr.is_active():
                        reconnect_mgr.trigger_reconnect()
                    self.update_mode()
                    retry += 1
                    time.sleep(1)
            else:
                print(f"[ComponentOperationTask] ERROR: Write {write_type} failed after 3 retries: {param.name}, addr {address}")
        finally:
            pass

    # 兼容旧读接口（若无映射管理器则直接返回None）
    def get_register_map(self):
        if not self.mapping_task_manager:
            print("[ComponentOperationTask] WARNING: Mapping task manager not provided, read interface disabled")
            return None
        return self.mapping_task_manager.get_register_map()

    def get_component_holding(self, name, key_prefix="r_d", decimals_key_suffix="_decimals"):
        reg = self.get_register_map()
        if not reg:
            return None
        param = self.param_mgr.get_param(name) if self.param_mgr else None
        if not param:
            print(f"[ComponentOperationTask] WARNING: Component not found: {name}")
            return None
        address_key = None
        for k in param.config:
            if k.startswith(key_prefix) and k.endswith("address"):
                address_key = k
                break
        if not address_key:
            print(f"[ComponentOperationTask] WARNING: No {key_prefix} address found for: {name}")
            return None
        addr_info = param.get(address_key, {})
        if "local" not in addr_info:
            print(f"[ComponentOperationTask] WARNING: {address_key} not found for: {name}")
            return None
        address = addr_info["local"]
        decimals_key = address_key.replace("address", decimals_key_suffix.lstrip("_"))
        decimals = int(param.get(decimals_key, 0) or 0)
        value = reg.registers.get(address)
        if value is not None and decimals:
            value = round(value / (10 ** decimals), decimals)
        return value

    def get_component_coil(self, name, key_prefix="r_b"):
        reg = self.get_register_map()
        if not reg:
            return None
        param = self.param_mgr.get_param(name) if self.param_mgr else None
        if not param:
            print(f"[ComponentOperationTask] WARNING: Component not found: {name}")
            return None
        address_key = None
        for k in param.config:
            if k.startswith(key_prefix) and k.endswith("address"):
                address_key = k
                break
        if not address_key:
            print(f"[ComponentOperationTask] WARNING: No {key_prefix} address found for: {name}")
            return None
        addr_info = param.get(address_key, {})
        if "local" not in addr_info:
            print(f"[ComponentOperationTask] WARNING: {address_key} not found for: {name}")
            return None
        address = addr_info["local"]
        value = reg.coils.get(address)
        return value

    def shutdown(self):
        """
        优雅关闭：先停监视线程，再关闭队列与工作线程
        """
        self._mode_watchdog_stop.set()
        if self._mode_watchdog_thread:
            self._mode_watchdog_thread.join(timeout=1.0)
            if self._mode_watchdog_thread.is_alive():
                print("[ComponentOperationTask] WARNING: Mode watchdog is still alive after shutdown")
        super().shutdown()