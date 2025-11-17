"""
Modbus RTU连接管理器
"""

import threading
import time
from typing import Optional

from pymodbus.client import ModbusSerialClient

from cdu120kw.modbus_manager.modbusconnect_manager import ModbusConnectionManagerBase


class ModbusRTUConnectionManager(ModbusConnectionManagerBase):
    """
    Modbus RTU连接管理器
    """

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        super().__init__()
        self.client = None
        self.connected = False
        self.connection_lock = threading.Lock()
        # 串口参数
        self.port = "COM10"
        self.baudrate = 115200
        self.bytesize = 8
        self.parity = "N"
        self.stopbits = 1
        self.timeout = 0.2
        self._has_logged_disconnect = False
        self._reconnect_attempts = 0
        self._last_connect_error = None

    def configure(self, port, baudrate, bytesize, parity, stopbits, timeout):
        """
        动态配置串口参数
        """
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout

    def start_rtuconnect(self):
        """
        建立RTU连接
        连接失败时不抛异常，返回False，由调用方决定后续动作
        连接成功后重置重连状态
        """
        with self.connection_lock:
            if self.connected:
                return True
            try:
                if self.client:
                    try:
                        self.client.close()
                    except Exception as e:
                        self.logger.warning(f"Error closing old RTU connection: {e}")
                self.client = ModbusSerialClient(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    timeout=self.timeout,
                )
                if self.client.connect():
                    self.connected = True
                    self.logger.info("RTU connection re-established successfully")
                    self._has_logged_disconnect = False
                    self._reconnect_attempts = 0
                    self._last_connect_error = None
                    return True
                else:
                    self.connected = False
                    self.client = None
                    self._reconnect_attempts += 1
                    if not self._has_logged_disconnect:
                        self.logger.warning(
                            "RTU connection lost, start reconnecting..."
                        )
                        self._has_logged_disconnect = True
                    # # 每10次输出一次重连失败日志，避免刷屏
                    # if self._reconnect_attempts % 10 == 0:
                    #     self.logger.warning(
                    #         f"RTU reconnect failed (Attempt #{self._reconnect_attempts}), will retry..."
                    #     )
                    # return False
            except Exception as e:
                # 只在异常信息变化时输出ERROR日志
                err_str = str(e)
                if self._last_connect_error != err_str:
                    self.logger.error(f"RTU connection error: {err_str}")
                    self._last_connect_error = err_str
                else:
                    self.logger.debug(f"RTU connection error (repeat): {err_str}")
                self.client = None
                self.connected = False
                return False

    def get_client(self) -> Optional[ModbusSerialClient]:
        """
        获取RTU客户端对象，判断socket属性
        """
        with self.connection_lock:
            if self.connected and self.client and getattr(self.client, "socket", None):
                return self.client
            return None

    def disconnect(self):
        """
        断开RTU连接，彻底释放资源
        """
        with self.connection_lock:
            if self.client:
                try:
                    self.client.close()
                    self.logger.info("RTU connection closed")
                except Exception as e:
                    self.logger.warning(f"Error closing RTU connection: {e}")
                self.client = None
            self.connected = False

    def is_connected(self):
        """
        只判断自身connected和client属性，不做读操作
        """
        return self.connected and self.client is not None

    def reset_reconnect_state(self):
        """
        重置重连状态
        """
        self.connected = False
        self.auto_reconnect = True
        self._has_logged_disconnect = False
        self._reconnect_attempts = 0


def safe_modbusrtu_call(func, *args, **kwargs):
    """
    RTU安全调用，统一异常处理和重试机制
    """
    max_retries = 2
    for attempt in range(max_retries):
        client = modbusrtu_manager.get_client()
        if not client:
            modbusrtu_manager.logger.error("No available RTU connection")
            return None
        try:
            return func(client, *args, **kwargs)
        except Exception as e:
            modbusrtu_manager.logger.warning(
                f"RTU operation failed (attempt {attempt + 1}/{max_retries}): {str(e)}"
            )
            with modbusrtu_manager.connection_lock:
                try:
                    client.close()
                except Exception as e:
                    modbusrtu_manager.logger.warning(
                        f"Error closing RTU connection: {e}"
                    )
                modbusrtu_manager.connected = False
            time.sleep(0.5)
    modbusrtu_manager.logger.error(f"RTU operation failed after {max_retries} attempts")
    return None


modbusrtu_manager = ModbusRTUConnectionManager()
