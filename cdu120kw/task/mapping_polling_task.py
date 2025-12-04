"""
轮询任务管理器，只负责高频Modbus任务，支持TCP/RTU自动切换
"""

import json
import threading
import time
import os

from cdu120kw.modbus_manager.batch_reader import ModbusBatchReader
from cdu120kw.task.task_queue import BasePollingTaskManager
from cdu120kw.config.config_repository import ConfigRepository


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
                # print(f"[MappingPollingTask] INFO: Register address writing:address={addr}, old value={old_v}, new value={v}")

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
                # print(f"[MappingPollingTask] INFO: Coil address writing:address={addr}, old value={old_v}, new value={v}")

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
        self.tcp_manager = tcp_manager
        self.rtu_manager = rtu_manager
        self.tcp_reader = ModbusBatchReader(self.tcp_manager)
        self.rtu_reader = ModbusBatchReader(self.rtu_manager) if self.rtu_manager else None
        # 启动时由update_mode决定真实模式
        self.current_mode = "none"
        self.reg_map = RegisterMap()
        self.lock = threading.Lock()
        self.tcp_reconnect_mgr = tcp_reconnect_mgr
        self.rtu_reconnect_mgr = rtu_reconnect_mgr
        self._mode_watchdog_thread = None
        self._mode_watchdog_stop = threading.Event()

        if config_path:
            self.load_tasks(config_path)

        # 启动阶段立即判定一次模式，避免初始TCP不可用但RTU可用时进入暂停
        self.update_mode()

        # 启动模式监视线程：独立周期性检查连接并切换模式
        self._start_mode_watchdog()

    def _start_mode_watchdog(self):
        """
        启动后台模式监视线程
        作用：在任务线程被TCP阻塞时，仍然能检测断链并触发模式切换
        """
        if self._mode_watchdog_thread and self._mode_watchdog_thread.is_alive():
            return

        def _watchdog():
            while not self._mode_watchdog_stop.is_set():
                try:
                    # 周期性更新模式；不依赖任务执行
                    self.update_mode()
                except Exception as e:
                    print(f"[MappingPollingTask] ERROR: Mode watchdog exception: {e}")
                # 缩短监视周期，加快切换速度
                time.sleep(0.2)

        self._mode_watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
        self._mode_watchdog_thread.start()

    def update_mode(self):
        """
        根据连接状态自动切换TCP/RTU，并控制暂停/恢复
        优化点：
        - 优先选择可用的模式（TCP优先，其次RTU）。
        - 从TCP切走时强制关闭TCP客户端，打断阻塞读。
        - 初始或运行中若RTU可用，避免长时间停在none。
        """
        with self.lock:
            tcp_ok = self.tcp_manager.is_connected()
            rtu_ok = self.rtu_manager.is_connected() if self.rtu_manager else False
            prev_mode = self.current_mode

            if tcp_ok:
                # TCP可用优先使用TCP
                if prev_mode != "tcp":
                    print(f"[MappingPollingTask] INFO: Switch hosted mode: {prev_mode} -> tcp")
                self.current_mode = "tcp"
                self.resume()
            elif rtu_ok:
                # TCP不可用但RTU可用：切到RTU
                if prev_mode == "tcp":
                    # 强制关闭TCP，打断阻塞中的读；避免任务线程一直卡在pymodbus重试
                    with self.tcp_manager.connection_lock:
                        if self.tcp_manager.client:
                            try:
                                self.tcp_manager.client.close()
                            except Exception as e:
                                print(f"[MappingPollingTask] WARNING: Force close TCP failed: {e}")
                            self.tcp_manager.connected = False
                if prev_mode != "rtu":
                    print(f"[MappingPollingTask] INFO: Switch hosted mode: {prev_mode} -> rtu")
                self.current_mode = "rtu"
                self.resume()
            else:
                # 全部不可用：进入暂停
                if prev_mode == "tcp":
                    # 同样强制关闭TCP，以免阻塞读一直占线程
                    with self.tcp_manager.connection_lock:
                        if self.tcp_manager.client:
                            try:
                                self.tcp_manager.client.close()
                            except Exception as e:
                                print(f"[MappingPollingTask] WARNING: Force close TCP failed: {e}")
                            self.tcp_manager.connected = False
                if prev_mode != "none":
                    print(f"[MappingPollingTask] INFO: Switch hosted mode: {prev_mode} -> none")
                self.current_mode = "none"
                self.pause()

    def on_pause_check(self):
        """
        暂停期间的检查逻辑：
        - 主动调用 update_mode() 检测 TCP/RTU 当前连接状态；
        - 若检测到任一连接恢复（特别是 RTU 可用），update_mode 会执行 resume() 并切换模式；
        在暂停期间也能切换到 RTU 模式。
        """
        self.update_mode()

    def load_tasks(self, config_path):
        try:
            repo = ConfigRepository.load(config_path)
            tasks = repo.tasks
            if not tasks:
                print("[MappingPollingTask] WARNING: No communication task found in config")
                return
            for task_params in tasks:
                comm_task = CommunicationTask(task_params)
                priority = 10 - comm_task.level
                self.task_queue.put_task(func=self.execute_task, args=(comm_task,), kwargs=None, priority=priority)
            print(f"[MappingPollingTask] INFO: Loaded {len(tasks)} communication task")
        except Exception as e:
            print(f"[MappingPollingTask] ERROR: Failed to load task configuration: {e}")

    def execute_task(self, comm_task):
        """
        执行单个通信任务，支持自动暂停/恢复和失败重试
        """
        now = time.time()
        if now < comm_task.next_run:
            time.sleep(comm_task.next_run - now)

        # 在执行前快速判定模式，减少等待
        self.update_mode()
        self.wait_if_paused()

        reader = self.tcp_reader if self.current_mode == "tcp" else self.rtu_reader
        manager = self.tcp_manager if self.current_mode == "tcp" else self.rtu_manager
        reconnect_mgr = (
            self.tcp_reconnect_mgr if self.current_mode == "tcp" else self.rtu_reconnect_mgr
        )
        if reader is None:
            print("[MappingPollingTask] WARNING: No Modbus connection available, skip task")
            return False

        success = False
        if comm_task.comm_type == 0:
            if comm_task.is_bit:
                values, err = reader.read_coils(comm_task.start_address, comm_task.length)
                if values:
                    self.reg_map.update_coils(comm_task.start_address, values)
                    success = True
                    # print(f"[MappingPollingTask] INFO: Coil read({self.current_mode}): {comm_task.name}, addr {comm_task.start_address}~{comm_task.start_address + comm_task.length - 1}, values: {values[:5]}")
                else:
                    print(f"[MappingPollingTask] WARNING: Coil read failed({self.current_mode}): {comm_task.name}, error: {err}")
                    # 读失败立刻标记断开，触发切换与重连
                    with manager.connection_lock:
                        manager.connected = False
                    if reconnect_mgr and reconnect_mgr.is_active():
                        reconnect_mgr.trigger_reconnect()
                    self.update_mode()
            else:
                values, err = reader.read_holding_registers(comm_task.start_address, comm_task.length)
                if values:
                    self.reg_map.update_registers(comm_task.start_address, values)
                    success = True
                    # print(f"[MappingPollingTask] INFO: Register read({self.current_mode}): {comm_task.name}, addr {comm_task.start_address}~{comm_task.start_address + comm_task.length - 1}, values: {values[:5]}")
                else:
                    print(f"[MappingPollingTask] WARNING: Register read failed({self.current_mode}): {comm_task.name}, error: {err}")
                    # 读失败立刻标记断开，触发切换与重连
                    with manager.connection_lock:
                        manager.connected = False
                        # 若是TCP失败，主动关闭以打断阻塞
                        if self.current_mode == "tcp" and self.tcp_manager.client:
                            try:
                                self.tcp_manager.client.close()
                            except Exception as e:
                                print(f"[MappingPollingTask] WARNING: Force close TCP on read fail: {e}")
                            self.tcp_manager.connected = False
                    if reconnect_mgr and reconnect_mgr.is_active():
                        reconnect_mgr.trigger_reconnect()
                    self.update_mode()

        if not success:
            return False

        # 持续任务重新入队
        if comm_task.operation_type == 0 and not self.shutdown_event.is_set():
            # 计算下一次运行时间并重新入队
            comm_task.next_run = time.time() + comm_task.interval
            self.task_queue.put_task(func=self.execute_task, args=(comm_task,), kwargs=None, priority=(10 - comm_task.level))

        return True

    def shutdown(self):
        """
        优雅关闭所有线程和队列
        """
        self._mode_watchdog_stop.set()
        super().shutdown()

    def get_register_map(self):
        """
        获取本地寄存器映射
        """
        return self.reg_map


mapping_polling_task_manager = MappingPollingTaskManager
