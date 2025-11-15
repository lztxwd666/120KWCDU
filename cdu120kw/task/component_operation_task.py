import json
import logging
import os
import threading
import time
from typing import Dict, Tuple, Optional

from cdu120kw.modbus_manager.batch_writer import ModbusBatchWriter
from cdu120kw.task.task_queue import BasePollingTaskManager

logger = logging.getLogger(__name__)

# 全局配置缓存（单路径只加载与预处理一次）
_CONFIG_FILE_CACHE: Dict[str, "ComponentTaskParamManager"] = {}


def to_u16(value: int) -> int:
    """
    转U16（两补码），保证写保持寄存器是无符号16位
    """
    try:
        iv = int(value)
    except (ValueError, TypeError):
        iv = 0
    return iv & 0xFFFF


def _pick_range_from_config(cfg: dict, key: str) -> Tuple[Optional[int], Optional[int]]:
    """
    自适配多种常见命名，提取占空比范围（寄存器原始值范围）
    优先匹配与当前key同前缀的 *_min/*_max，其次通用 min/max、min_duty/max_duty 等
    """
    # key 形如 rw_d_duty_register_address / rw_d_speed_register_address ...
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
      write_type: "coil"/"register"
    """

    def __init__(self, name: str, config: dict, comp_type: str = "fan"):
        self.name = name
        self.comp_type = comp_type
        self.config = config
        self.enabled = config.get("enabled", True)
        self.writable_fields: Dict[str, Tuple[str, int, int, Tuple[Optional[int], Optional[int]]]] = {}
        self._precompute_writable_fields()

    def _precompute_writable_fields(self):
        for k, v in self.config.items():
            if not isinstance(v, dict):
                continue
            if not k.endswith("address"):
                continue
            if k.startswith("rw_b"):
                # 可写线圈
                if "local" in v:
                    addr = v["local"]
                    self.writable_fields[k] = ("coil", int(addr), 0, (None, None))
            elif k.startswith("rw_d"):
                # 可写保持寄存器
                if "local" in v:
                    addr = v["local"]
                    decimals_key = k.replace("address", "decimals")
                    decimals = int(self.config.get(decimals_key, 0) or 0)
                    rng = _pick_range_from_config(self.config, k)
                    self.writable_fields[k] = ("register", int(addr), decimals, rng)

    def get(self, key, default=None):
        return self.config.get(key, default)

class ComponentTaskParamManager:
    """
    组件参数管理器（带可写字段预映射），支持全局缓存
    """

    def __init__(self, config_path: str):
        self.lock = threading.Lock()
        self.params: Dict[str, ComponentTaskParam] = {}
        self._load_config(config_path)

    def _load_config(self, config_path: str):
        with open(config_path, "r", encoding="utf-8-sig") as f:
            config = json.load(f)

        def _add_all(kind_key: str, comp_type: str):
            for item in config.get(kind_key, []):
                name = item["name"]
                comp_config = item["config"]
                self.params[name] = ComponentTaskParam(name, comp_config, comp_type)

        _add_all("fans", "fan")
        _add_all("pumps", "pump")
        # 兼容单复数两种写法
        if "proportional_valves" in config:
            _add_all("proportional_valves", "proportional_valve")
        if "proportional_valve" in config:
            _add_all("proportional_valve", "proportional_valve")

    def get_param(self, name: str) -> Optional[ComponentTaskParam]:
        with self.lock:
            return self.params.get(name)

    def set_enabled(self, name: str, enabled: bool):
        with self.lock:
            if name in self.params:
                self.params[name].enabled = enabled
                self.params[name].config["enabled"] = enabled

    def is_enabled(self, name: str) -> bool:
        with self.lock:
            return bool(self.params.get(name) and self.params[name].enabled)

    def all_params(self):
        with self.lock:
            return list(self.params.values())

class ComponentOperationTaskManager(BasePollingTaskManager):
    """
    组件操作任务管理器（直接批量写入PCBA；支持优先级插队；TCP/RTU自动切换；内部重试与断线重连）
    - 使用全局缓存的配置与可写字段预映射
    - 保持寄存器写入采用U16（两补码）
    - 支持最小/最大占空比自动夹取（若配置存在）
    """

    def __init__(
        self,
        tcp_manager,
        config_path: str,
        mapping_task_manager=None,  # 可为空：写入不再依赖映射
        pool_workers=2,
        rtu_manager=None,
        tcp_reconnect_mgr=None,
        rtu_reconnect_mgr=None,
    ):
        super().__init__(pool_workers=pool_workers)
        self.logger = logger
        self.tcp_manager = tcp_manager
        self.rtu_manager = rtu_manager
        self.tcp_writer = ModbusBatchWriter(self.tcp_manager)
        self.rtu_writer = ModbusBatchWriter(self.rtu_manager) if self.rtu_manager else None
        self.current_mode = "tcp"
        self.param_mgr: Optional[ComponentTaskParamManager] = None
        self.lock = threading.Lock()
        self.tcp_reconnect_mgr = tcp_reconnect_mgr
        self.rtu_reconnect_mgr = rtu_reconnect_mgr
        self.config_path = config_path
        self.mapping_task_manager = mapping_task_manager  # 仅为兼容旧读接口
        self.accept_new_task = True
        self.last_write_values: Dict[Tuple[str, int], int] = {}

        if config_path and os.path.exists(config_path):
            self.load_tasks(config_path)

    def load_tasks(self, config_path: str):
        # 全局缓存：同一路径仅加载预处理一次
        mgr = _CONFIG_FILE_CACHE.get(config_path)
        if mgr is None:
            mgr = ComponentTaskParamManager(config_path)
            _CONFIG_FILE_CACHE[config_path] = mgr
        self.param_mgr = mgr
        self.logger.info("Loaded component operation task (from cache=%s)", config_path in _CONFIG_FILE_CACHE)

    def update_mode(self):
        with self.lock:
            tcp_ok = self.tcp_manager.is_connected()
            rtu_ok = self.rtu_manager.is_connected() if self.rtu_manager else False
            prev_mode = self.current_mode
            if tcp_ok:
                self.current_mode = "tcp"
                self.accept_new_task = True
                self.resume()
            elif rtu_ok:
                self.current_mode = "rtu"
                self.accept_new_task = True
                self.resume()
            else:
                self.current_mode = "none"
                self.accept_new_task = False
                self.pause()
            if self.current_mode != prev_mode:
                self.logger.info("Switch hosted mode: %s -> %s", prev_mode, self.current_mode)

    @staticmethod
    def _pick_first_writable(param: "ComponentTaskParam", value_dict: dict):
        """
        在预映射表中按传入字段匹配第一个可写项
        返回: (field, write_type, address, decimals, (min,max), value)
        """
        for field, value in value_dict.items():
            meta = param.writable_fields.get(field)
            if meta:
                wtype, addr, decimals, rng = meta
                return field, wtype, addr, decimals, rng, value
        return None, None, None, None, (None, None), None

    def operate_component(self, name: str, value_dict: dict, slave: int = 1, priority: int = 0):
        """
        触发写入（默认最高优先级0插队）
        value_dict: 传递具体可写字段，如 {"rw_d_duty_register_address": 123}
        """
        self.update_mode()
        with self.lock:
            if not self.accept_new_task:
                self.logger.warning("Communication offline, reject new write task")
                return "Communication offline, reject new write task"
            if not self.param_mgr:
                return "Param manager not initialized"
            param = self.param_mgr.get_param(name)
            if not param or not param.enabled:
                return "Component not found or disabled"

            field, write_type, address, decimals, rng, value = self._pick_first_writable(param, value_dict)
            if write_type is None or address is None:
                return "No valid writable address"

            # 占空比/范围夹取（若配置提供 min/max）
            min_v, max_v = rng if isinstance(rng, tuple) else (None, None)
            try:
                ivalue = int(value)
            except (ValueError, TypeError):
                ivalue = 0

            # 根据占空比的小数位进行动态放大（仅对 duty 字段生效）
            scale = 1
            duty_decimals = int(decimals or 0)
            # 识别占空比字段：rw_d_duty*
            if write_type == "register" and isinstance(field, str) and "rw_d_duty" in field:
                if duty_decimals == 0:
                    # 预映射未取到时，回退到配置中的 rw_d_duty_decimals
                    try:
                        duty_decimals = int(param.config.get("rw_d_duty_decimals", 0) or 0)
                    except (ValueError, TypeError):
                        duty_decimals = 0
                if duty_decimals > 0:
                    scale = 10 ** duty_decimals

            # 进行按 scale 后的范围夹取
            if min_v is not None:
                ivalue = max(ivalue, int(min_v * scale))
            if max_v is not None:
                ivalue = min(ivalue, int(max_v * scale))
            # 写入值规整
            if write_type == "coil":
                write_value = 1 if int(ivalue) else 0
            else:
                write_value = to_u16(ivalue)

            # 去重：相同地址与相同值则跳过
            last_key = (write_type, address)
            if self.last_write_values.get(last_key) == write_value:
                self.logger.info(
                    "Skip write: %s, type=%s, addr=%s, value=%s（与上次相同）",
                    name, write_type, address, write_value
                )
                return "Skip write: value not changed"
            self.last_write_values[last_key] = write_value

            # # 提交写入任务日志
            # self.logger.info(
            #     "Submit write task: %s, type=%s, addr=%s, value=%s, priority=%s",
            #     name, write_type, address, write_value, priority
            # )
            self.task_queue.put_task(
                func=self.execute_write,
                args=(param, write_value, slave, address, write_type),
                priority=priority if isinstance(priority, int) else 0,
            )
            return "Write task submitted"

    def execute_write(self, param: ComponentTaskParam, value: int, slave: int, address: int, write_type: str):
        """
        实际写入PCBA寄存器，失败内部重试3次；无可用连接返回False交由调度层等待恢复
        """
        try:
            retry = 0
            while retry < 3:
                self.update_mode()
                self.wait_if_paused()
                writer = self.tcp_writer if self.current_mode == "tcp" else self.rtu_writer
                manager = self.tcp_manager if self.current_mode == "tcp" else self.rtu_manager
                reconnect_mgr = self.tcp_reconnect_mgr if self.current_mode == "tcp" else self.rtu_reconnect_mgr
                if not writer:
                    self.logger.warning("No Modbus connection available, skip write task")
                    return False

                if write_type == "coil":
                    err = writer.write_coils(address, [value], slave=slave)
                else:
                    # 保持寄存器确保为U16
                    err = writer.write_registers(address, [to_u16(value)], slave=slave)

                # 检查写入结果，无错误则退出重试
                if not err:
                    # self.logger.info("Write success: %s, addr %s, value=%s", param.name, address, value)
                    break
                else:
                    self.logger.warning(
                        "Write %s failed: %s, addr %s, error: %s",
                        write_type, param.name, address, err
                    )
                    if manager and hasattr(manager, "connection_lock"):
                        with manager.connection_lock:
                            manager.connected = False
                    if reconnect_mgr and reconnect_mgr.is_active():
                        reconnect_mgr.trigger_reconnect()
                    self.update_mode()
                    retry += 1
                    time.sleep(1)
            else:
                self.logger.error(
                    "Write %s failed after 3 retries: %s, addr %s",
                    write_type, param.name, address
                )
        finally:
            pass

    # 兼容旧读接口（若无映射管理器则直接返回None）
    def get_register_map(self):
        if not self.mapping_task_manager:
            self.logger.warning("Mapping task manager not provided, read interface disabled")
            return None
        return self.mapping_task_manager.get_register_map()

    def get_component_holding(self, name, key_prefix="r_d", decimals_key_suffix="_decimals"):
        reg = self.get_register_map()
        if not reg:
            return None
        param = self.param_mgr.get_param(name) if self.param_mgr else None
        if not param:
            self.logger.warning("Component not found: %s", name)
            return None
        address_key = None
        for k in param.config:
            if k.startswith(key_prefix) and k.endswith("address"):
                address_key = k
                break
        if not address_key:
            self.logger.warning("No %s address found for: %s", key_prefix, name)
            return None
        addr_info = param.get(address_key, {})
        if "local" not in addr_info:
            self.logger.warning("%s not found for: %s", address_key, name)
            return None
        address = addr_info["local"]
        decimals_key = address_key.replace("address", decimals_key_suffix.lstrip("_"))
        decimals = int(param.get(decimals_key, 0) or 0)
        value = reg.registers.get(address)
        if value is not None and decimals:
            value = round(value / (10 ** decimals), decimals)
        return value

    def get_component_coil(self, name, key_prefix="r_b"):
        reg = self.get_register_map()
        if not reg:
            return None
        param = self.param_mgr.get_param(name) if self.param_mgr else None
        if not param:
            self.logger.warning("Component not found: %s", name)
            return None
        address_key = None
        for k in param.config:
            if k.startswith(key_prefix) and k.endswith("address"):
                address_key = k
                break
        if not address_key:
            self.logger.warning("No %s address found for: %s", key_prefix, name)
            return None
        addr_info = param.get(address_key, {})
        if "local" not in addr_info:
            self.logger.warning("%s not found for: %s", address_key, name)
            return None
        address = addr_info["local"]
        value = reg.coils.get(address)
        return value