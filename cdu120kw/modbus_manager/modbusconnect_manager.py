"""
Modbus连接管理器基类
"""

import threading


class ModbusConnectionManagerBase:
    """
    Modbus连接管理器基类
    只封装通用连接、断开等功能，去除心跳和监控线程，连接状态由轮询任务判断
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.client = None
        self.connected = False
        self.connection_lock = threading.Lock()
        self.auto_reconnect = True

    def connect(self, *args, **kwargs) -> bool:
        """
        建立连接（抽象方法，需子类实现）
        """
        raise NotImplementedError("Please implement connect method in subclass")

    def disconnect(self) -> bool:
        """
        断开连接，释放资源
        """
        with self.connection_lock:
            if self.client:
                try:
                    self.client.close()
                    print("Connection closed")
                except Exception as e:
                    print(f"Close connection exception: {str(e)}")
                finally:
                    self.connected = False
                    self.client = None
        return True

    def get_client(self):
        """
        获取连接对象（抽象方法，需子类实现）
        """
        raise NotImplementedError("Please implement get_client method in subclass")

    def is_connected(self) -> bool:
        """
        检查连接状态（抽象方法，需子类实现）
        只判断底层连接对象是否存在，不主动发起读操作
        """
        raise NotImplementedError("Please implement is_connected method in subclass")
