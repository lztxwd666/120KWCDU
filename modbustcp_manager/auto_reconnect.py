import logging
import threading


class AutoReconnectManager:
    def __init__(self, connection_manager, reconnect_callback=None):
        self.conn_manager = connection_manager
        self.logger = logging.getLogger("auto_reconnect")
        self.reconnect_interval = 2
        self.heartbeat_interval = 0.2
        self.heartbeat_fail_threshold = 5

        self.active = False
        self.stop_requested = False
        self.heartbeat_fail_count = 0
        self.reconnect_attempts = 0
        self.is_reconnecting = False

        self.heartbeat_timer = None
        self.reconnect_timer = None
        self.reconnect_callback = reconnect_callback  # 可选回调

    def start(self):
        self.stop()
        self.active = True
        self.stop_requested = False
        self.heartbeat_fail_count = 0
        self.reconnect_attempts = 0
        self.is_reconnecting = False
        self._start_heartbeat_timer()
        self.logger.info("自动重连监控已启动")

    def stop(self):
        self.active = False
        self.stop_requested = True
        self.is_reconnecting = False
        self.heartbeat_fail_count = 0
        self.reconnect_attempts = 0
        if self.heartbeat_timer:
            self.heartbeat_timer.cancel()
        if self.reconnect_timer:
            self.reconnect_timer.cancel()
        self.logger.info("自动重连监控已停止")

    def is_active(self):
        return self.active

    def get_reconnect_attempts(self):
        return self.reconnect_attempts

    def _start_heartbeat_timer(self):
        if self.active and not self.stop_requested:
            self.heartbeat_timer = threading.Timer(self.heartbeat_interval, self._heartbeat_check)
            self.heartbeat_timer.start()

    def _heartbeat_check(self):
        if not self.active or self.stop_requested:
            self.logger.info("_heartbeat_check aborted: inactive/stopped")
            self.is_reconnecting = False
            return
        if self.is_reconnecting:
            return
        try:
            is_connected = self.conn_manager.is_connected()
            if is_connected:
                self.heartbeat_fail_count = 0
            else:
                self.heartbeat_fail_count += 1
                if self.heartbeat_fail_count >= self.heartbeat_fail_threshold:
                    if self.active and not self.stop_requested:
                        self.is_reconnecting = True
                        self.logger.warning("连接丢失，尝试重连...")
                        self._start_reconnect_timer()
        except Exception as e:
            self.logger.error(f"心跳检测异常: {str(e)}")
            self.heartbeat_fail_count += 1
        self._start_heartbeat_timer()

    def _start_reconnect_timer(self):
        self.reconnect_timer = threading.Timer(0, self._attempt_reconnect)
        self.reconnect_timer.start()

    def _attempt_reconnect(self):
        if not self.active or self.stop_requested:
            self.logger.info("_attempt_reconnect aborted: inactive/stopped")
            self.is_reconnecting = False
            return

        self.reconnect_attempts += 1
        self.logger.warning(f"尝试重连 (尝试 #{self.reconnect_attempts})")
        success = False
        try:
            ip = self.conn_manager.ip
            port = self.conn_manager.port
            self.logger.info(f"尝试重连到 {ip}:{port}")

            self.conn_manager.disconnect()
            success = self.conn_manager.connect(ip, port)

            if success:
                self.logger.info("重连成功")
                self.reconnect_attempts = 0
                self.heartbeat_fail_count = 0
                self.is_reconnecting = False
                if self.reconnect_callback:
                    self.reconnect_callback()
                return
            else:
                self.logger.warning("重连失败，稍后重试")
        except Exception as e:
            self.logger.error(f"重连尝试异常: {str(e)}")

        if self.active and not self.stop_requested:
            self.reconnect_timer = threading.Timer(self.reconnect_interval, self._attempt_reconnect)
            self.reconnect_timer.start()
        else:
            self.logger.info("_attempt_reconnect exit: inactive/stopped")
            self.is_reconnecting = False
