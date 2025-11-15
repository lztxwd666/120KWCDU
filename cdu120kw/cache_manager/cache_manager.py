"""
通用缓存管理类，支持自动过期和线程安全
"""

import time
from threading import RLock
from typing import Any, Callable, Optional


class CacheManager:
    """
    通用缓存管理类，支持自动过期和线程安全

    特性：
    - 线程安全：使用可重入锁保证多线程环境下的安全
    - 自动过期：支持设置缓存项的过期时间
    - 缓存清理：定期清理过期项目
    - 回调支持：缓存失效时自动调用原始函数重新获取数据
    - 统计功能：记录缓存命中率

    使用方法：
    1. 直接存储/获取：cache.set(key, value), cache.get(key)
    2. 装饰器模式：@cache.cached(ttl=60)

    示例：
    cache = CacheManager()

    # 直接使用
    cache.set("temperature", 25.5, ttl=10)
    temp = cache.get("temperature")

    # 装饰器使用
    @cache.cached(ttl=30)
    def get_expensive_data():
        # 复杂计算或远程调用
        return compute_data()
    """

    def __init__(self, cleanup_interval: int = 300):
        """
        初始化缓存管理器

        :param cleanup_interval: 自动清理过期缓存的时间间隔（秒）
        """
        self._store = {}  # 缓存存储: {key: (value, expiry_time)}
        self._lock = RLock()  # 线程安全锁
        self._stats = {"hits": 0, "misses": 0, "sets": 0}
        self._last_cleanup = time.time()
        self.cleanup_interval = cleanup_interval

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        设置缓存值

        :param key: 缓存键
        :param value: 缓存值
        :param ttl: 缓存有效期（秒），None表示永不过期
        """
        with self._lock:
            expiry = time.time() + ttl if ttl is not None else None
            self._store[key] = (value, expiry)
            self._stats["sets"] += 1

            # 定期清理过期缓存
            if time.time() - self._last_cleanup > self.cleanup_interval:
                self._clean_expired()

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存值

        :param key: 缓存键
        :param default: 未找到或过期时返回的默认值
        :return: 缓存值或默认值
        """
        with self._lock:
            if key in self._store:
                value, expiry = self._store[key]

                # 检查是否过期
                if expiry is None or time.time() < expiry:
                    self._stats["hits"] += 1
                    return value

                # 已过期，删除
                del self._store[key]

            self._stats["misses"] += 1
            return default

    def cached(self, ttl: int = 60):
        """
        缓存装饰器，自动缓存函数结果

        :param ttl: 缓存有效期（秒）
        :return: 装饰器函数
        """

        def decorator(func: Callable):
            def wrapper(*args, **kwargs):
                # 生成唯一缓存键（函数名+参数）
                key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

                # 尝试从缓存获取
                cached_value = self.get(key)
                if cached_value is not None:
                    return cached_value

                # 缓存未命中，执行函数
                result = func(*args, **kwargs)

                # 仅当结果有效时缓存
                if not isinstance(result, str) or not result.startswith("Error"):
                    self.set(key, result, ttl=ttl)

                return result

            return wrapper

        return decorator

    def clear(self, key: str = None) -> None:
        """
        清除缓存

        :param key: 要清除的缓存键，None表示清除所有缓存
        """
        with self._lock:
            if key is None:
                self._store = {}
            elif key in self._store:
                del self._store[key]

    def get_stats(self) -> dict:
        """
        获取缓存统计信息

        :return: 包含缓存统计信息的字典
        """
        with self._lock:
            hits = self._stats["hits"]
            misses = self._stats["misses"]
            total = hits + misses
            return {
                "total_items": len(self._store),
                "hits": hits,
                "misses": misses,
                "hit_rate": hits / total if total > 0 else 0,
                "sets": self._stats["sets"],
            }

    def _clean_expired(self) -> None:
        """清理过期缓存项"""
        current_time = time.time()
        expired_keys = [
            key
            for key, (_, expiry) in self._store.items()
            if expiry is not None and expiry < current_time
        ]

        for key in expired_keys:
            del self._store[key]

        self._last_cleanup = current_time


# 创建全局缓存实例
global_cache = CacheManager()
