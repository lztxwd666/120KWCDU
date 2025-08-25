import configparser
import os
from typing import Any

# 单例配置实例
_config_instance = None


class Config:
    """配置类，提供类型安全的配置访问"""

    def __init__(self, parser: configparser.ConfigParser, env: str):
        self._parser = parser
        self._env = env

    @property
    def env(self) -> str:
        """获取当前环境（只读）"""
        return self._env

    def get(self, key: str, fallback: Any = None) -> Any:
        """获取配置值"""
        try:
            return self._parser.get(self._env, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def getboolean(self, key: str, fallback: bool = False) -> bool:
        """获取布尔类型配置值"""
        try:
            return self._parser.getboolean(self._env, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def getint(self, key: str, fallback: int = 0) -> int:
        """获取整数类型配置值"""
        try:
            return self._parser.getint(self._env, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def getfloat(self, key: str, fallback: float = 0.0) -> float:
        """获取浮点数类型配置值"""
        try:
            return self._parser.getfloat(self._env, key, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    @property
    def DEBUG(self) -> bool:
        return self.getboolean('DEBUG', False)

    @property
    def LOG_LEVEL(self) -> str:
        return self.get('LOG_LEVEL', 'INFO')

    @property
    def MODBUS_DEFAULT_HOST(self) -> str:
        return self.get('MODBUS_DEFAULT_HOST', '192.168.1.150')

    @property
    def MODBUS_DEFAULT_PORT(self) -> int:
        return self.getint('MODBUS_DEFAULT_PORT', 5000)

    @property
    def MODBUS_TIMEOUT(self) -> float:
        return self.getfloat('MODBUS_TIMEOUT', 5.0)

    @property
    def FLASK_HOST(self) -> str:
        return self.get('FLASK_HOST', '0.0.0.0')

    @property
    def FLASK_PORT(self) -> int:
        return self.getint('FLASK_PORT', 5000)

    @property
    def FLASK_THREADS(self) -> int:
        return self.getint('FLASK_THREADS', 4)

    @property
    def FONT_PATH(self) -> str:
        return self.get('FONT_PATH', 'font/LXGWWenKai-Regular.ttf')

    @property
    def SECRET_KEY(self) -> str:
        return self.get('SECRET_KEY', 'default-secret-key')


def get_config() -> Config:
    """获取配置实例（单例）"""
    global _config_instance
    if _config_instance:
        return _config_instance

    # 确定当前环境
    env = os.getenv('FLASK_ENV', 'production')  # 'development' 或 'production'

    # 创建配置解析器
    config_parser = configparser.ConfigParser()

    # 获取配置文件路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, 'config.ini')

    # 确保配置文件存在
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件未找到: {config_path}")

    # 读取配置文件
    config_parser.read(config_path)

    # 确保环境存在，否则使用默认配置
    if env not in config_parser:
        print(f"警告: 环境 '{env}' 未在配置文件中定义，使用默认设置")
        env = 'DEFAULT'

    # 创建并返回单例配置实例
    _config_instance = Config(config_parser, env)
    return _config_instance
