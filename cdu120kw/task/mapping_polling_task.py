"""
轮询任务管理器，只负责高频Modbus任务，支持TCP/RTU自动切换
"""

import json
import logging
import threading
import time

from cdu120kw.modbus_manager.batch_reader import ModbusBatchReader
from cdu120kw.task.task_queue import BasePollingTaskManager

# 在类外部初始化日志
write_logger = logging.getLogger("register_write")
write_logger.setLevel(logging.INFO)
if not write_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
    handler.setFormatter(formatter)
    write_logger.addHandler(handler)


class CommunicationTask:
    """
    通信任务对象，包含调度参数和任务属性
    """

    def __init__(self, params):
        self.name = params["name"]
        self.comm_type = params["communication_type"]  # 0:读, 1:写
        self.operation_type = params["communication_operation_type"]  # 0:持续, 1:单次
        self.level = params["communication_level_type"]  # 0:低, 1:高
        self.is_bit = params["is_bit"]
        self.interval = params["interval"] / 1000.0
        self.start_address = params["start_address"]
        self.length = params["length"]
        self.next_run = time.time()
        self.params = params


class RegisterMap:
    """
    本地寄存器映射，线程安全，支持写入锁
    """

    def __init__(self):
        self.registers = {}
        self.coils = {}
        self.lock = threading.Lock()
        self.write_lock = set()  # 被写入锁定的地址集合
        self._first_sync = True

    def set_write_lock(self, address):
        with self.lock:
            self.write_lock.add(address)

    def release_write_lock(self, address):
        with self.lock:
            self.write_lock.discard(address)

    def is_locked(self, address):
        with self.lock:
            return address in self.write_lock

    def update_registers(self, start_address, values):
        """
        批量更新寄存器
        只有当新值与当前值不一致时才写入，避免无效写操作
        """
        with self.lock:
            for i, v in enumerate(values):
                addr = start_address + i
                if addr in self.write_lock:
                    continue  # 跳过被锁定的地址
                old_v = self.registers.get(addr)
                if old_v == v:
                    continue  # 新旧值一致，跳过写入
                self.registers[addr] = v  # 只有值变化时才写入
                # write_logger.info(f"Register address writing:address={addr}, old value={old_v}, new value={v}")

    def update_coils(self, start_address, values):
        """
        批量更新线圈
        只有当新值与当前值不一致时才写入，避免无效写操作
        """
        with self.lock:
            for i, v in enumerate(values):
                addr = start_address + i
                if addr in self.write_lock:
                    continue  # 跳过被锁定的地址
                old_v = self.coils.get(addr)
                if old_v == v:
                    continue  # 新旧值一致，跳过写入
                self.coils[addr] = v  # 只有值变化时才写入
                # write_logger.info(f"Coil address writing:address={addr}, old value={old_v}, new value={v}")

    def set_register(self, address, value):
        with self.lock:
            self.registers[address] = value

    def get_register(self, address):
        with self.lock:
            return self.registers.get(address)


class MappingPollingTaskManager(BasePollingTaskManager):
    """
    高频轮询任务管理器，支持TCP/RTU自动切换
    复用基类的自动暂停/恢复/失败重试机制
    """

    def __init__(
        self,
        tcp_manager,
        config_path,
        pool_workers=4,
        rtu_manager=None,
        tcp_reconnect_mgr=None,
        rtu_reconnect_mgr=None,
    ):
        super().__init__(pool_workers=pool_workers)
        self.logger = logging.getLogger(__name__)
        self.tcp_manager = tcp_manager
        self.rtu_manager = rtu_manager
        self.tcp_reader = ModbusBatchReader(self.tcp_manager)
        self.rtu_reader = (
            ModbusBatchReader(self.rtu_manager) if self.rtu_manager else None
        )
        self.current_mode = "tcp"
        self.reg_map = RegisterMap()
        self.lock = threading.Lock()
        self.tcp_reconnect_mgr = tcp_reconnect_mgr
        self.rtu_reconnect_mgr = rtu_reconnect_mgr
        if config_path:
            self.load_tasks(config_path)

    def update_mode(self):
        """
        根据连接状态自动切换TCP/RTU，并控制暂停/恢复
        """
        with self.lock:
            tcp_ok = self.tcp_manager.is_connected()
            rtu_ok = self.rtu_manager.is_connected() if self.rtu_manager else False
            prev_mode = self.current_mode
            if tcp_ok:
                self.current_mode = "tcp"
                self.resume()  # 唤醒所有等待线程
            elif rtu_ok:
                self.current_mode = "rtu"
                self.resume()
            else:
                self.current_mode = "none"
                self.pause()  # 进入暂停
            if self.current_mode != prev_mode:
                self.logger.info(
                    f"Switch hosted mode: {prev_mode} -> {self.current_mode}"
                )

    def load_tasks(self, config_path):
        """
        从配置文件加载任务
        """
        try:
            with open(config_path, "r", encoding="utf-8-sig") as f:
                config = json.load(f)
            for task_params in config.get("tasks", []):
                comm_task = CommunicationTask(task_params)
                priority = 10 - comm_task.level
                self.task_queue.put_task(
                    func=self.execute_task,
                    args=(comm_task,),
                    kwargs=None,
                    priority=priority,
                )
            self.logger.info(
                f"Loaded {len(config.get('tasks', []))} communication task"
            )
        except Exception as e:
            self.logger.error(f"Failed to load task configuration: {e}")

    def execute_task(self, comm_task):
        """
        执行单个通信任务，支持自动暂停/恢复和失败重试
        """
        now = time.time()
        if now < comm_task.next_run:
            time.sleep(comm_task.next_run - now)
        self.wait_if_paused()  # 检查是否需要暂停
        self.update_mode()
        reader = self.tcp_reader if self.current_mode == "tcp" else self.rtu_reader
        manager = self.tcp_manager if self.current_mode == "tcp" else self.rtu_manager
        reconnect_mgr = (
            self.tcp_reconnect_mgr
            if self.current_mode == "tcp"
            else self.rtu_reconnect_mgr
        )
        if reader is None:
            self.logger.warning("No Modbus connection available, skip task")
            return False
        # 只处理读任务
        success = False
        if comm_task.comm_type == 0:
            if comm_task.is_bit:
                values, err = reader.read_coils(
                    comm_task.start_address, comm_task.length
                )
                if values:
                    self.reg_map.update_coils(comm_task.start_address, values)
                    success = True
                    # self.logger.info(
                    #     f"Coil read({self.current_mode}): {comm_task.name}, addr {comm_task.start_address}~{comm_task.start_address + comm_task.length - 1}, values: {values[:5]}"
                    # )
                else:
                    self.logger.warning(
                        f"Coil read failed({self.current_mode}): {comm_task.name}, error: {err}"
                    )
                    with manager.connection_lock:
                        manager.connected = False
                    if reconnect_mgr and reconnect_mgr.is_active():
                        reconnect_mgr.trigger_reconnect()
                    self.update_mode()
            else:
                values, err = reader.read_holding_registers(
                    comm_task.start_address, comm_task.length
                )
                if values:
                    self.reg_map.update_registers(comm_task.start_address, values)
                    success = True
                    # self.logger.info(
                    #     f"Register read({self.current_mode}): {comm_task.name}, addr {comm_task.start_address}~{comm_task.start_address + comm_task.length - 1}, values: {values[:5]}"
                    # )
                else:
                    self.logger.warning(
                        f"Register read failed({self.current_mode}): {comm_task.name}, error: {err}"
                    )
                    with manager.connection_lock:
                        manager.connected = False
                    if reconnect_mgr and reconnect_mgr.is_active():
                        reconnect_mgr.trigger_reconnect()
                    self.update_mode()
        if not success:
            return False
        # 持续任务重新入队
        if comm_task.operation_type == 0 and not self.shutdown_event.is_set():
            comm_task.next_run = time.time() + comm_task.interval
            priority = 10 - comm_task.level
            self.task_queue.put_task(
                args=(comm_task,),
                kwargs=None,
                func=self.execute_task,
                priority=priority,
            )
        return True

    def get_register_map(self):
        """
        获取本地寄存器映射
        """
        return self.reg_map


mapping_polling_task_manager = MappingPollingTaskManager
