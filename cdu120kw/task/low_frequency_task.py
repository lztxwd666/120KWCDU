"""
低频任务管理器，支持RTU心跳和后续低频任务扩展
继承BasePollingTaskManager，实现低频任务调度
"""

import json
import time

from cdu120kw.modbus_manager.batch_reader import ModbusBatchReader
from cdu120kw.task.task_queue import BasePollingTaskManager


class LowFrequencyTask:
    """
    低频任务对象，包含调度参数和任务属性
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


class LowFrequencyTaskManager(BasePollingTaskManager):
    """
    低频任务管理器，支持RTU心跳和后续低频任务扩展
    """

    def __init__(
        self,
        tcp_manager,
        rtu_manager,
        config_path,
        pool_workers=1,
        rtu_reconnect_mgr=None,
    ):
        super().__init__(pool_workers=pool_workers)
        self.tcp_manager = tcp_manager
        self.rtu_manager = rtu_manager
        self.tcp_reader = ModbusBatchReader(self.tcp_manager)
        self.rtu_reader = ModbusBatchReader(self.rtu_manager)
        self.rtu_reconnect_mgr = rtu_reconnect_mgr
        self._rtu_heartbeat_failed = False
        self._rtu_heartbeat_lost_logged = False  # 日志只输出一次
        self.rtu_heartbeat_enabled = True
        self._rtu_heartbeat_task_params = None
        if config_path:
            self.load_tasks(config_path)

    def load_tasks(self, config_path):
        """
        从配置文件加载低频任务
        """
        try:
            with open(config_path, "r", encoding="utf-8-sig") as f:
                config = json.load(f)
            for task_params in config.get("low_frequency_tasks", []):
                comm_task = LowFrequencyTask(task_params)
                if comm_task.name == "RTUHeartbeat":
                    self._rtu_heartbeat_task_params = task_params
                priority = 5
                self.task_queue.put_task(
                    func=self.execute_task,
                    args=(comm_task,),
                    kwargs=None,
                    priority=priority,
                )
            print(f"[LowFrequencyTask] INFO: Loaded {len(config.get('low_frequency_tasks', []))} low frequency task")
        except Exception as e:
            print(f"[LowFrequencyTask] ERROR: Failed to load low frequency task configuration: {e}")

    def execute_task(self, comm_task):
        """
        执行单个低频任务，支持RTU心跳和默认TCP读取
        任务执行完成后，如果是持续任务则重新入队
        """
        if comm_task.name == "RTUHeartbeat" and not self.rtu_heartbeat_enabled:
            return
        now = time.time()
        if now < comm_task.next_run:
            time.sleep(comm_task.next_run - now)
        try:
            force_rtu_tasks = ["RTUHeartbeat"]
            if comm_task.name in force_rtu_tasks:
                self._force_read_rtu(comm_task)
            else:
                self._default_tcp_read(comm_task)
        except Exception as e:
            print(f"[LowFrequencyTask] ERROR: LowFrequencyTask execute_task exception: {e}")
        # 持续任务重新入队
        if comm_task.operation_type == 0 and not self.shutdown_event.is_set():
            if comm_task.name != "RTUHeartbeat" or self.rtu_heartbeat_enabled:
                comm_task.next_run = time.time() + comm_task.interval
                priority = 5
                self.task_queue.put_task(
                    func=self.execute_task,
                    args=(comm_task,),
                    kwargs=None,
                    priority=priority,
                )

    def _force_read_rtu(self, comm_task):
        """
        强制使用RTU连接读取任务，主要用于RTU心跳
        """
        if self.rtu_reader is None:
            if not self._rtu_heartbeat_lost_logged:
                print("[LowFrequencyTask] WARNING: No RTU connection available, skip force RTU task")
                self._rtu_heartbeat_lost_logged = True
            return
        if comm_task.is_bit:
            values, err = self.rtu_reader.read_coils(
                comm_task.start_address, comm_task.length
            )
            # if values:
            #     print(f"[LowFrequencyTask] INFO: Coil read(rtu): {comm_task.name}, addr {comm_task.start_address}~{comm_task.start_address + comm_task.length - 1}, values: {values[:5]}")
            # else:
            #     print(f"[LowFrequencyTask] INFO: Coil read(rtu): {comm_task.name}, addr {comm_task.start_address}~{comm_task.start_address + comm_task.length - 1}, values: []")
        else:
            values, err = self.rtu_reader.read_holding_registers(
                comm_task.start_address, comm_task.length
            )
            # if values:
            #     print(f"[LowFrequencyTask] INFO: Register read(rtu): {comm_task.name}, addr {comm_task.start_address}~{comm_task.start_address + comm_task.length - 1}, values: {values[:5]}")
            # else:
            #     print(f"[LowFrequencyTask] INFO: Register read(rtu): {comm_task.name}, addr {comm_task.start_address}~{comm_task.start_address + comm_task.length - 1}, values: []")
        if values:
            if self._rtu_heartbeat_failed:
                print("[LowFrequencyTask] INFO: RTUHeartbeat recovered")
            self._rtu_heartbeat_failed = False
            self._rtu_heartbeat_lost_logged = False
        else:
            if not self._rtu_heartbeat_failed:
                if not self._rtu_heartbeat_lost_logged:
                    print(f"[LowFrequencyTask] WARNING: RTUHeartbeat lost, error: {err}")
                    self._rtu_heartbeat_lost_logged = True
                self._rtu_heartbeat_failed = True
            if self.rtu_manager:
                with self.rtu_manager.connection_lock:
                    self.rtu_manager.connected = False
            if self.rtu_reconnect_mgr and self.rtu_reconnect_mgr.is_active():
                self.rtu_reconnect_mgr.trigger_reconnect()
            if self.rtu_heartbeat_enabled:
                self.rtu_heartbeat_enabled = False
                self.task_queue.remove_tasks_by_name("RTUHeartbeat")

    def on_rtu_reconnected(self):
        """
        RTU重连成功后由重连管理器回调，恢复心跳任务
        """
        if not self.rtu_heartbeat_enabled and self._rtu_heartbeat_task_params:
            self.rtu_heartbeat_enabled = True
            comm_task = LowFrequencyTask(self._rtu_heartbeat_task_params)
            priority = 5
            self.task_queue.put_task(
                func=self.execute_task,
                args=(comm_task,),
                kwargs=None,
                priority=priority,
            )
            print("[LowFrequencyTask] INFO: RTUHeartbeat task re-enabled after reconnection")

    def _default_tcp_read(self, comm_task):
        """
        默认使用TCP连接读取任务
        """
        if self.tcp_reader is None:
            print("[LowFrequencyTask] WARNING: No TCP connection available, skip low frequency task")
            return
        if comm_task.is_bit:
            values, err = self.tcp_reader.read_coils(
                comm_task.start_address, comm_task.length
            )
            if values:
                print(f"[LowFrequencyTask] INFO: Coil read(tcp): {comm_task.name}, addr {comm_task.start_address}~{comm_task.start_address + comm_task.length - 1}, values: {values[:5]}")
            else:
                print(f"[LowFrequencyTask] WARNING: Coil read failed(tcp): {comm_task.name}, error: {err}")
        else:
            values, err = self.tcp_reader.read_holding_registers(
                comm_task.start_address, comm_task.length
            )
            if values:
                print(f"[LowFrequencyTask] INFO: Register read(tcp): {comm_task.name}, addr {comm_task.start_address}~{comm_task.start_address + comm_task.length - 1}, values: {values[:5]}")
            else:
                print(f"[LowFrequencyTask] WARNING: Register read failed(tcp): {comm_task.name}, error: {err}")