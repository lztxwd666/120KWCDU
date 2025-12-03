"""
Modbus TCP连接管理器
"""

import socket
import time
from typing import Optional

import pymodbus.exceptions
from pymodbus.client import ModbusTcpClient

from cdu120kw.config.config_manager import get_config
from cdu120kw.modbus_manager.modbusconnect_manager import ModbusConnectionManagerBase


class ModbusTCPConnectionManager(ModbusConnectionManagerBase):
    """
    Modbus TCP连接管理器
    """

    def __init__(self):
        # 从配置文件读取参数
        super().__init__()
        config = get_config().modbus_tcp
        self.ip = config.get("ip", "192.168.1.150")
        self.port = config.get("port", 5000)
        self._has_logged_disconnect = False
        self._reconnect_attempts = 0

    def start_tcpconnect(self, ip: str = None, port: int = None) -> bool:
        """
        建立TCP连接，支持动态配置IP和端口
        连接失败时不抛异常，返回False，由调用方决定后续动作
        更短的超时与重试次数，降低阻塞时长
        """
        if ip:
            self.ip = ip
        if port:
            self.port = port
        with self.connection_lock:
            if self.connected:
                return True
            try:
                if self.client:
                    try:
                        self.client.close()
                    except (ConnectionError, OSError) as e:
                        print(f"[ModbusTCPConnection] ERROR: Error closing old connection: {e}")
                # 加快失败返回
                self.client = ModbusTcpClient(host=self.ip, port=self.port, retries=0, timeout=0.3)
                if self.client.connect():
                    self.connected = True
                    self.auto_reconnect = True
                    print("[ModbusTCPConnection] INFO: TCP connection re-established successfully")
                    self._has_logged_disconnect = False
                    self._reconnect_attempts = 0
                    return True
                else:
                    self.client = None
                    self.connected = False
                    self._reconnect_attempts += 1
                    if not self._has_logged_disconnect:
                        print("[ModbusTCPConnection] WARNING: TCP connection lost, start reconnecting...")
                        self._has_logged_disconnect = True
            except (ConnectionRefusedError, TimeoutError, socket.gaierror, pymodbus.exceptions.ModbusException) as e:
                print(f"[ModbusTCPConnection] ERROR: TCP connection exception: {str(e)}")
                self.client = None
                self.connected = False
                return False
            except OSError as e:
                print(f"[ModbusTCPConnection] ERROR: Network anomaly: {str(e)}")
                self.client = None
                self.connected = False
                return False
            return False

    def get_client(self) -> Optional[ModbusTcpClient]:
        """
        获取TCP客户端对象，判断socket是否打开
        """
        with self.connection_lock:
            if self.connected and self.client and self.client.is_socket_open():
                return self.client
            return None

    def is_connected(self) -> bool:
        """
        只判断TCP底层连接对象是否存在，不主动发起读操作
        """
        return self.connected and self.client and self.client.is_socket_open()

    def reset_reconnect_state(self):
        """
        重置重连状态
        """
        with self.connection_lock:
            self.connected = False
            self.auto_reconnect = True
            self._has_logged_disconnect = False
            self._reconnect_attempts = 0


def safe_modbustcp_call(manager, func, *args, **kwargs):
    """
    TCP安全调用，统一异常处理和重试机制
    失败后立即关闭并标记断开，加快上层切换判断
    """
    max_retries = 1  # 降低内部重试次数，加速失败返回
    for attempt in range(max_retries):
        client = manager.get_client()
        if not client:
            print("[ModbusTCPConnection] ERROR: No available TCP connection")
            return None
        try:
            return func(client, *args, **kwargs)
        except (ConnectionResetError, pymodbus.exceptions.ModbusException, OSError) as e:
            print(f"[ModbusTCPConnection] WARNING: TCP operation failed {attempt + 1}/{max_retries}): {str(e)}")
            with manager.connection_lock:
                try:
                    client.close()
                except (ConnectionError, OSError) as e2:
                    print(f"[ModbusTCPConnection] WARNING: Error closing TCP connection: {e2}")
                manager.connected = False
            time.sleep(0.1)
        except (ValueError, TypeError) as e:
            print(f"[ModbusTCPConnection] ERROR: TCP parameter error: {str(e)}")
            return None
        except Exception as e:
            print(f"[ModbusTCPConnection] ERROR: TCP unknown error: {str(e)}")
            return None
    print(f"[ModbusTCPConnection] ERROR: TCP operation retry {max_retries} still Failed")
    return None

# 实例化管理器
modbustcp_manager = ModbusTCPConnectionManager()