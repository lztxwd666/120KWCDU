"""
通用任务配置导入与组件参数管理
"""


import json
import os
import threading
from typing import Dict, Any, List, Optional, Tuple

def _pick_range_from_config(cfg: dict, key: str) -> Tuple[Optional[int], Optional[int]]:
    """
    从配置提取当前写入字段的范围(min, max)，支持多种常见命名。
    key 形如 rw_d_duty_register_address / rw_d_speed_register_address ...
    """
    base = key.rsplit("_address", 1)[0]
    candidates = [
        (f"{base}_min", f"{base}_max"),
        ("min_duty", "max_duty"),
        ("duty_min", "duty_max"),
        ("min", "max"),
    ]
    for min_k, max_k in candidates:
        mn = cfg.get(min_k, None)
        mx = cfg.get(max_k, None)
        if mn is not None or mx is not None:
            try:
                mn_i = int(mn) if mn is not None else None
                mx_i = int(mx) if mx is not None else None
                return mn_i, mx_i
            except (ValueError, TypeError):
                return None, None
    return None, None

class ComponentTaskParam:
    """
    组件任务参数对象（含可写字段预映射）
    - writable_fields: { field_name: (write_type, address, decimals, (min,max)) }
      write_type: "coil" / "register"
    """
    def __init__(self, name: str, config: dict, comp_type: str):
        self.name = name
        self.comp_type = comp_type
        self.config = config
        self.enabled = bool(config.get("enabled", True))
        self.writable_fields: Dict[str, Tuple[str, int, int, Tuple[Optional[int], Optional[int]]]] = {}
        self._precompute_writable_fields()

    def _precompute_writable_fields(self):
        for k, v in self.config.items():
            if not isinstance(v, dict):
                continue
            if not k.endswith("address"):
                continue
            # rw_b_*_address -> coil
            if k.startswith("rw_b"):
                if "local" in v:
                    addr = int(v["local"])
                    self.writable_fields[k] = ("coil", addr, 0, (None, None))
            # rw_d_*_address -> holding register
            elif k.startswith("rw_d"):
                if "local" in v:
                    addr = int(v["local"])
                    decimals_key = k.replace("address", "decimals")
                    try:
                        decimals = int(self.config.get(decimals_key, 0) or 0)
                    except (ValueError, TypeError):
                        decimals = 0
                    rng = _pick_range_from_config(self.config, k)
                    self.writable_fields[k] = ("register", addr, decimals, rng)

    def get(self, key, default=None):
        return self.config.get(key, default)

class ComponentTaskParamManager:
    """
    组件参数管理器（带可写字段预映射）
    - 提供按名称查找、启用/禁用、遍历
    """
    def __init__(self, config: dict):
        self._lock = threading.Lock()
        self._params: Dict[str, ComponentTaskParam] = {}
        self._build(config)

    def _build(self, config: dict):
        def _add_all(kind_key: str, comp_type: str):
            for item in config.get(kind_key, []):
                name = item.get("name")
                comp_config = item.get("config", {})
                if not name:
                    continue
                self._params[name] = ComponentTaskParam(name, comp_config, comp_type)
        _add_all("fans", "fan")
        _add_all("pumps", "pump")
        _add_all("output", "output")
        # 兼容单复数
        if "proportional_valves" in config:
            _add_all("proportional_valves", "proportional_valve")
        if "proportional_valve" in config:
            _add_all("proportional_valve", "proportional_valve")

    def get_param(self, name: str) -> Optional[ComponentTaskParam]:
        with self._lock:
            return self._params.get(name)

    def all_params(self) -> List[ComponentTaskParam]:
        with self._lock:
            return list(self._params.values())

    def set_enabled(self, name: str, enabled: bool):
        with self._lock:
            p = self._params.get(name)
            if p:
                p.enabled = bool(enabled)
                p.config["enabled"] = bool(enabled)

class ConfigRepository:
    """
    单路径只解析一次，提供视图：tasks / low_frequency_tasks / component_params
    """
    _CACHE: Dict[str, "ConfigRepository"] = {}
    _GLOBAL_LOCK = threading.Lock()

    @classmethod
    def load(cls, path: str) -> "ConfigRepository":
        abs_path = os.path.abspath(path)
        with cls._GLOBAL_LOCK:
            repo = cls._CACHE.get(abs_path)
            if repo is None:
                repo = ConfigRepository(abs_path)
                cls._CACHE[abs_path] = repo
            return repo

    @classmethod
    def clear(cls, path: Optional[str] = None):
        with cls._GLOBAL_LOCK:
            if path:
                cls._CACHE.pop(os.path.abspath(path), None)
            else:
                cls._CACHE.clear()

    def __init__(self, abs_path: str):
        self.path = abs_path
        with open(self.path, "r", encoding="utf-8-sig") as f:
            self._raw = json.load(f)
        self.tasks: List[Dict[str, Any]] = list(self._raw.get("tasks", []))
        self.low_frequency_tasks: List[Dict[str, Any]] = list(self._raw.get("low_frequency_tasks", []))
        self.component_params = ComponentTaskParamManager(self._raw)

    # 返回原始配置的浅拷贝，避免外部修改内部状态
    def to_dict(self) -> Dict[str, Any]:
        return dict(self._raw)

    # 公开读取某一段配置
    def get_section(self, key: str, default: Any = None) -> Any:
        return self._raw.get(key, default)