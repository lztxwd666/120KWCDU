"""
Modbus自动重连管理器，支持线程池异步回调，TCP和RTU功能分离，公共逻辑抽象为基类
"""

import threading
from typing import Callable, Optional

from cdu120kw.task.task_thread_pool import ThreadPoolManager


class BaseAutoReconnectManager:
    """
    自动重连管理器基类，支持线程池异步执行重连回调
    """

    def __init__(
        self,
        connection_manager,
        reconnect_callback: Optional[Callable] = None,
        logger_name: str = "auto_reconnect.base",
        thread_pool: Optional[ThreadPoolManager] = None,
    ):
        self.conn_manager = connection_manager
        self.reconnect_interval = 1  # 重连间隔秒
        self.active = False
        self.stop_requested = False
        self.reconnect_attempts = 0
        self.is_reconnecting = False
        self.reconnect_timer = None
        self.reconnect_callback = reconnect_callback
        self.has_logged_disconnect = False  # 标记是否已输出断开日志
        self.thread_pool = thread_pool

    def start(self):
        """
        启动自动重连管理器
        """
        if self.active:
            return
        self.stop()
        self.active = True
        self.stop_requested = False
        self.reconnect_attempts = 0
        self.is_reconnecting = False
        self.has_logged_disconnect = False
        print("[AutoReconnect] INFO: Auto reconnection monitoring started")
        # 启动时如果未连接，立即进入重连循环
        if not self.conn_manager.is_connected():
            self.is_reconnecting = True
            self._start_reconnect_timer()

    def stop(self):
        """
        停止自动重连管理器
        """
        if not self.active:
            return
        self.active = False
        self.stop_requested = True
        self.is_reconnecting = False
        self.reconnect_attempts = 0
        self.has_logged_disconnect = False
        if self.reconnect_timer:
            self.reconnect_timer.cancel()
        print("[AutoReconnect] INFO: Auto reconnection monitoring stopped")

    def is_active(self):
        """
        返回是否处于激活状态
        """
        return self.active

    def get_reconnect_attempts(self):
        """
        获取重连尝试次数
        """
        return self.reconnect_attempts

    def trigger_reconnect(self):
        """
        由轮询任务调用，触发重连流程
        """
        if not self.active or self.stop_requested or self.is_reconnecting:
            return
        self.is_reconnecting = True
        # 只在第一次断开时输出断开日志
        if not self.has_logged_disconnect:
            print("[AutoReconnect] INFO: Connection lost, start reconnecting...")
            self.has_logged_disconnect = True
        self._start_reconnect_timer()

    def _start_reconnect_timer(self):
        """
        启动重连定时器
        """
        self.reconnect_timer = threading.Timer(0, self._attempt_reconnect)
        self.reconnect_timer.start()

    def _run_callback_async(self):
        """
        使用线程池异步执行重连回调
        """
        if self.reconnect_callback:
            if self.thread_pool:
                self.thread_pool.submit(self.reconnect_callback)
                print("[AutoReconnect] INFO: Reconnect callback submitted to thread pool")
            else:
                self.reconnect_callback()
                print("[AutoReconnect] INFO: Reconnect callback executed synchronously")

    def _attempt_reconnect(self):
        """
        子类实现具体重连逻辑
        """
        raise NotImplementedError("Subclasses must implement _attempt_reconnect()")


class TcpAutoReconnectManager(BaseAutoReconnectManager):
    """
    TCP自动重连管理器，支持线程池异步回调
    """

    def __init__(
        self,
        connection_manager,
        reconnect_callback=None,
        thread_pool: Optional[ThreadPoolManager] = None,
    ):
        super().__init__(
            connection_manager,
            reconnect_callback,
            logger_name="auto_reconnect.tcp",
            thread_pool=thread_pool,
        )

    def _attempt_reconnect(self):
        """
        执行TCP重连操作
        """
        if not self.active or self.stop_requested:
            print("[AutoReconnect] INFO: TCP _attempt_reconnect aborted: inactive/stopped")
            self.is_reconnecting = False
            return

        self.reconnect_attempts += 1
        success = False
        try:
            ip = getattr(self.conn_manager, "ip", None)
            port = getattr(self.conn_manager, "port", None)
            self.conn_manager.disconnect()
            if ip and port:
                success = self.conn_manager.start_tcpconnect(ip, port)
            else:
                success = self.conn_manager.connect()

            if success:
                print("[AutoReconnect] INFO: TCP reconnect successfully")
                self.reconnect_attempts = 0
                self.is_reconnecting = False
                self.has_logged_disconnect = False
                self._run_callback_async()  # 用线程池异步执行回调
                return
        except Exception as e:
            print(f"[AutoReconnect] ERROR: TCP reconnect attempt exception: {str(e)}")

        # 重连失败后持续调度下一次重连
        if self.active and not self.stop_requested:
            self.reconnect_timer = threading.Timer(
                self.reconnect_interval, self._attempt_reconnect
            )
            self.reconnect_timer.start()
        else:
            print("[AutoReconnect] INFO: TCP _attempt_reconnect exit: inactive/stopped")
            self.is_reconnecting = False


class RtuAutoReconnectManager(BaseAutoReconnectManager):
    """
    RTU自动重连管理器，支持线程池异步回调
    """

    def __init__(
        self,
        connection_manager,
        reconnect_callback=None,
        thread_pool: Optional[ThreadPoolManager] = None,
    ):
        super().__init__(
            connection_manager,
            reconnect_callback,
            logger_name="auto_reconnect.rtu",
            thread_pool=thread_pool,
        )

    def _attempt_reconnect(self):
        """
        执行RTU重连操作
        """
        if not self.active or self.stop_requested:
            print("[AutoReconnect] INFO: RTU _attempt_reconnect aborted: inactive/stopped")
            self.is_reconnecting = False
            return

        self.reconnect_attempts += 1
        success = False
        try:
            self.conn_manager.disconnect()
            success = self.conn_manager.start_rtuconnect()
            if success:
                self.conn_manager.connected = True
                print("[AutoReconnect] INFO: RTU connection re-established successfully")
                self.reconnect_attempts = 0
                self.is_reconnecting = False
                self.has_logged_disconnect = False
                self._run_callback_async()  # 用线程池异步执行回调
                return
        except Exception as e:
            print(f"[AutoReconnect] ERROR: RTU reconnect attempt exception: {str(e)}")

        # 重连失败后持续调度下一次重连
        if self.active and not self.stop_requested:
            self.reconnect_timer = threading.Timer(
                self.reconnect_interval, self._attempt_reconnect
            )
            self.reconnect_timer.start()
        else:
            print("[AutoReconnect] INFO: RTU _attempt_reconnect exit: inactive/stopped")
            self.is_reconnecting = False