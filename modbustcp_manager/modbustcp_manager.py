import logging
import socket
import threading
import time
from typing import Optional

import pymodbus.exceptions
from pymodbus.client import ModbusTcpClient

from utilities.loop_writer_function import loop_writer_manager


class ModbusTCPConnectionManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.__init__()
        return cls._instance

    def __init__(self):
        """在__init__中初始化所有实例属性"""
        self.client = None
        self.connected = False
        self.auto_reconnect = False
        self.connection_lock = threading.Lock()
        self.connection_thread = None
        self.stop_event = threading.Event()
        self.ip = "192.168.1.150"
        self.port = 5000
        self.logger = logging.getLogger("modbus_manager")
        self.quick_check_timeout = 0.2  # 快速检测超时时间(秒)
        self.logger.info("已设置寄存器144写入回调")

    def connect(self, ip: str = None, port: int = None) -> bool:
        """连接到Modbus设备"""
        if ip:
            self.ip = ip
        if port:
            self.port = port

        with self.connection_lock:
            if self.connected:
                return True

            try:
                # 关闭旧连接（如果存在）
                if self.client:
                    try:
                        self.client.close()
                    except (ConnectionError, OSError) as e:
                        self.logger.warning(f"Error closing old connection: {e}")

                # 创建新连接
                self.logger.info(f"Modbus已连接到 {self.ip}:{self.port}")
                self.client = ModbusTcpClient(
                    host=self.ip,
                    port=self.port,
                    timeout=self.quick_check_timeout,
                    retries=3
                )

                if self.client.connect():
                    self.logger.info("Modbus已成功连接")
                    self.connected = True
                    self.auto_reconnect = True
                    return True
                else:
                    self.logger.error("无法连接至Modbus设备")
                    self.client = None
                    return False

            # 捕获更具体的异常类型
            except (ConnectionRefusedError, TimeoutError,
                    socket.gaierror, pymodbus.exceptions.ModbusException) as e:
                self.logger.error(f"Modbus连接错误: {str(e)}")
                self.client = None
                return False
            except OSError as e:
                self.logger.error(f"网络错误: {str(e)}")
                self.client = None
                return False

    def quick_check_connection(self):
        """区分连接状态和操作超时"""
        # 检查基础连接状态
        if not self.client or not self.client.is_socket_open():
            self.logger.debug("连接检查: 套接字未打开")
            return False

        try:
            # 尝试读取寄存器
            result = self.client.read_holding_registers(address=0, count=1, slave=1)

            # 只要没有异常就认为连接正常
            return True

        except pymodbus.exceptions.ConnectionException:
            # 连接级别异常 - 真正的连接问题
            self.logger.warning("连接检查: 连接异常")
            return False

        except pymodbus.exceptions.ModbusException as e:
            # Modbus协议级异常 - 可能是设备响应问题
            self.logger.debug(f"连接检查: Modbus异常 - {str(e)}")
            return True  # 仍然认为连接正常

        except Exception as e:
            # 其他异常 - 视为连接问题
            self.logger.warning(f"连接检查: 未知异常 - {str(e)}")
            return False

    def _safe_write_register(self, address, value):
        """安全的写入寄存器方法"""
        return safe_modbus_call(
            lambda c: c.write_register(address, value, slave=1)
        )

    def disconnect(self):
        disconnect_success = True
        if self.connected and self.is_connected():
            self.logger.info("断开前写入寄存器144值0")
            try:
                if not loop_writer_manager.write_disconnect_value():
                    self.logger.error("无法写入断开值0，无法安全断开连接")
                    disconnect_success = False
            except Exception as e:
                self.logger.error(f"写入断开值出错: {str(e)}")
                disconnect_success = False
        else:
            self.logger.info("连接已断开，跳过写入值0")

        # 执行断开操作
        with self.connection_lock:
            self.auto_reconnect = False
            if self.client and self.connected:
                try:
                    self.client.close()
                    self.logger.info("Modbus连接断开")
                except (ConnectionError, OSError) as e:
                    self.logger.error(f"Error closing Modbus connection: {str(e)}")
                    disconnect_success = False
                finally:
                    self.connected = False
                    self.client = None

        return disconnect_success

    def get_client(self) -> Optional[ModbusTcpClient]:
        """获取可用的Modbus客户端"""
        with self.connection_lock:
            if self.connected and self.client and self.client.is_socket_open():
                return self.client
            return None

    def is_connected(self):
        """更可靠的连接状态检查"""
        # 先检查基础连接状态
        if not self.client or not self.client.is_socket_open():
            return False

        try:
            # 尝试读取寄存器0（设备通常都有的寄存器）
            result = self.client.read_holding_registers(address=0, count=1, slave=1)

            # 检查响应是否有效
            if result.isError():
                self.logger.warning(f"连接响应错误: {str(result)}")
                return False

            return True
        except Exception as e:
            # 记录异常但不要重复记录相同错误
            if "WinError 10054" not in str(e):
                self.logger.error(f"连接验证失败: {str(e)}")
            return False

    def start_connection_monitor(self):
        """启动连接监控线程"""
        if self.connection_thread and self.connection_thread.is_alive():
            return

        self.stop_event.clear()
        self.connection_thread = threading.Thread(
            target=self._connection_monitor,
            daemon=True,
            name="ModbusConnectionMonitor"
        )
        self.connection_thread.start()

    def stop_connection_monitor(self):
        """停止连接监控线程"""
        self.stop_event.set()
        if self.connection_thread:
            self.connection_thread.join(timeout=1)
            self.connection_thread = None

    def _connection_monitor(self):
        """监控连接状态并自动重连"""
        while not self.stop_event.is_set():
            try:
                # 检查连接状态
                if not self.is_connected():
                    if self.auto_reconnect:
                        self.logger.warning("Modbus connection lost, attempting to reconnect...")
                        self.connected = False
                        self.connect()  # 尝试重连
                    else:
                        self.logger.info("Auto-reconnect disabled")
                time.sleep(2)
            except Exception as e:
                self.logger.error(f"Connection monitor error: {str(e)}")
                time.sleep(5)

    # 新增重置方法
    def reset_reconnect_state(self):
        """重置重连状态"""
        self.connected = False
        self.auto_reconnect = True


# 全局连接管理器
modbus_manager = ModbusTCPConnectionManager()


def safe_modbus_call(func, *args, **kwargs):
    """安全的Modbus调用封装，自动处理连接和错误"""
    max_retries = 2
    for attempt in range(max_retries):
        client = modbus_manager.get_client()
        if not client:
            modbus_manager.logger.error("无可用的Modbus连接")
            return None

        try:
            return func(client, *args, **kwargs)
        except (ConnectionResetError, pymodbus.exceptions.ModbusException, OSError) as e:
            modbus_manager.logger.warning(f"Modbus operation failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
            # 强制关闭连接以触发下次重连
            with modbus_manager.connection_lock:
                try:
                    client.close()
                except (ConnectionError, OSError) as e:
                    modbus_manager.logger.warning(f"Error closing connection: {e}")
                modbus_manager.connected = False
            time.sleep(0.5)
        # 更具体的异常处理
        except (ValueError, TypeError) as e:
            modbus_manager.logger.error(f"Invalid argument error: {str(e)}")
            return None
        except Exception as e:
            modbus_manager.logger.error(f"Unexpected error in Modbus operation: {str(e)}")
            return None

    modbus_manager.logger.error(f"Modbus operation failed after {max_retries} attempts")
    return None
