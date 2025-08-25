import logging
import threading
import time


class LoopWriterManager:
    def __init__(self):
        self.logger = logging.getLogger("register_writer_manager")
        self.write_thread = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.enabled = False

        self.interval_144 = 3
        self.interval_1538 = 3
        self.last_write_144 = 0
        self.last_write_1538 = 0
        self.value_144 = 1
        self.value_1538 = 0

        self.monitor_stop_event = threading.Event()  # 监控线程退出事件
        self.monitor_thread = threading.Thread(
            target=self._monitor_connection,
            daemon=True,
            name="RegisterWriterMonitor"
        )
        self.monitor_thread.start()
        self.logger.info("统一寄存器写入管理器已启动")

    def _monitor_connection(self):
        from modbustcp_manager.modbustcp_manager import modbus_manager
        last_connected = None
        while not self.monitor_stop_event.is_set():
            current_connected = modbus_manager.is_connected()
            if current_connected != last_connected:
                if current_connected:
                    self.logger.info("检测到连接建立，启动写入线程")
                    self.start_writing()
                else:
                    self.logger.info("检测到连接断开，停止写入线程")
                    self.stop_writing()
                last_connected = current_connected
            self.monitor_stop_event.wait(1)  # 用wait替代sleep，便于快速退出

    def start_writing(self):
        with self.lock:
            if self.write_thread and self.write_thread.is_alive():
                return
            self.stop_event.clear()
            self.enabled = True
            self.write_thread = threading.Thread(
                target=self._write_loop,
                daemon=True,
                name="RegisterWriterThread"
            )
            self.write_thread.start()
            self.logger.info("寄存器写入线程已启动")

    def stop_writing(self):
        with self.lock:
            self.enabled = False
            self.stop_event.set()
            if self.write_thread and self.write_thread.is_alive():
                self.write_thread.join(timeout=2)
                if self.write_thread.is_alive():
                    self.logger.warning("寄存器写入线程未能及时停止")
                else:
                    self.logger.info("寄存器写入线程已停止")
            self.write_thread = None

    def stop_all(self):
        """程序退出时彻底释放资源"""
        self.stop_writing()
        self.monitor_stop_event.set()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
            if self.monitor_thread.is_alive():
                self.logger.warning("监控线程未能及时停止")
            else:
                self.logger.info("监控线程已停止")
        self.monitor_thread = None

    def _write_loop(self):
        from modbustcp_manager.modbustcp_manager import safe_modbus_call
        self.logger.info("开始循环写入寄存器144和1538")
        self._write_144_until_success(1)
        last_144 = self.value_144
        last_1538 = self.value_1538
        while not self.stop_event.is_set() and self.enabled:
            now = time.time()
            if int(now - self.last_write_144) >= self.interval_144:
                try:
                    safe_modbus_call(lambda c: c.write_register(144, self.value_144, slave=1))
                    if self.value_144 != last_144:
                        self.logger.info(f"寄存器144写入新值: {self.value_144}")
                        last_144 = self.value_144
                except Exception as e:
                    self.logger.error(f"写入寄存器144失败: {e}")
                self.last_write_144 = now
            if int(now - self.last_write_1538) >= self.interval_1538:
                try:
                    safe_modbus_call(lambda c: c.write_register(1538, self.value_1538, slave=1))
                    if self.value_1538 != last_1538:
                        self.logger.info(f"寄存器1538写入新值: {self.value_1538}")
                        last_1538 = self.value_1538
                except Exception as e:
                    self.logger.error(f"写入寄存器1538失败: {e}")
                self.last_write_1538 = now
            self.stop_event.wait(0.1)

    def set_value_144(self, value: int):
        with self.lock:
            if self.value_144 != value:
                self.logger.info(f"寄存器144已写入: {value}")
            self.value_144 = value

    def set_value_1538(self, value: int):
        with self.lock:
            if self.value_1538 != value:
                self.logger.info(f"寄存器1538已写入: {value}")
            self.value_1538 = value

    def write_disconnect_value(self):
        self.logger.info("准备断开连接，写入寄存器144值0")
        return self._write_144_until_success(0)

    def _write_144_until_success(self, value):
        from modbustcp_manager.modbustcp_manager import safe_modbus_call
        max_attempts = 10
        attempt = 0
        success = False
        while attempt < max_attempts and not self.stop_event.is_set():
            attempt += 1
            try:
                safe_modbus_call(lambda c: c.write_register(144, value, slave=1))
            except Exception as e:
                self.logger.error(f"写入寄存器144失败: {e}")
                time.sleep(0.1)
                continue
            try:
                read_result = safe_modbus_call(
                    lambda c: c.read_holding_registers(address=144, count=1, slave=1)
                )
                if read_result and read_result.registers and read_result.registers[0] == value:
                    self.logger.info(f"寄存器144值{value}写入并验证成功")
                    success = True
                    break
                else:
                    read_value = read_result.registers[0] if read_result and read_result.registers else "N/A"
                    self.logger.warning(f"寄存器144值{value}验证失败 (实际值: {read_value})")
            except Exception as e:
                self.logger.error(f"读取验证失败: {e}")
            time.sleep(0.1)
        if not success:
            self.logger.error(f"寄存器144值{value}写入失败，超过最大尝试次数")
        return success


# 创建全局实例
loop_writer_manager = LoopWriterManager()
