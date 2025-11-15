"""
配置管理模块，支持分组、动态修改和持久化
"""

import json
import os
from threading import Lock


class Config:
    """
    配置管理类，支持分组访问、动态修改和持久化
    """
    _default_config = {
        "modbus_tcp": {
            "ip": "192.168.1.150",
            "port": 5000
        },
        "modbus_rtu": {
            "port": "COM10",
            "baud_rate": 115200,
            "byte_size": 8,
            "parity": "N",
            "stop_bits": 1,
            "timeout": 1.0
        },
        "flask": {
            "host": "0.0.0.0",
            "port": 5000,
            "threads": 4,
            "secret_key": "default-secret-key",
            "debug": False
        },
        "log": {
            "level": "INFO"
        }
    }

    def __init__(self, config_path=None):
        self._lock = Lock()
        self._config_path = config_path or os.path.join(os.path.dirname(__file__), "settings.json")
        self._config = self._default_config.copy()
        self.load()

    def load(self):
        """
        从json文件加载配置
        """
        if os.path.exists(self._config_path):
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._config.update(data)

    def save(self):
        """
        保存配置到json文件
        """
        with self._lock:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)

    def get(self, section, key=None, default=None):
        """
        获取分组配置参数
        :param section: 配置分组名，如"ModbusTCP"
        :param key: 分组下的具体参数名，如"ip"
        :param default: 默认值
        """
        group = self._config.get(section, {})
        if key is None:
            return group
        return group.get(key, default)

    def set(self, section, key, value):
        """
        动态设置分组配置参数，并持久化
        :param section: 配置分组名
        :param key: 参数名
        :param value: 参数值
        """
        with self._lock:
            if section not in self._config:
                self._config[section] = {}
            self._config[section][key] = value
            self.save()

    @property
    def modbus_tcp(self):
        """获取ModbusTCP分组配置"""
        return self.get("modbus_tcp")

    @property
    def modbus_rtu(self):
        """获取ModbusRTU分组配置"""
        return self.get("modbus_rtu")

    @property
    def flask(self):
        """获取Flask分组配置"""
        return self.get("flask")

    @property
    def log(self):
        """获取日志分组配置"""
        return self.get("log")


# 单例配置实例
_config_instance = None


def get_config():
    """
    获取全局配置实例
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
