"""
Modbus HMI 从站数据接口实现
- 基于 pymodbus 实现 Modbus RTU 从站
- 直接对接 control_logic 层的 processed_reg_map，提供高性能读写接口
- 支持动态配置加载与日志记录
- 新增写入回调接口：可在写入前/后执行业务逻辑（预留扩展点）
"""

import json
import logging
import os
import threading
import time
from typing import Tuple

from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import StartSerialServer

from cdu120kw.control_logic.device_data_manipulation import processed_reg_map

# Logger（避免重复 handler 与冒泡）
logger = logging.getLogger("modbus_hmi")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)
logger.propagate = False  # 不向上冒泡，避免重复日志

# 仅允许启动一次 Modbus HMI 线程，防止单例多开、重启
_modbus_hmi_thread_started = False
_modbus_hmi_thread_lock = threading.Lock()

# 配置加载（仅一次）
def _load_modbus_settings() -> Tuple[dict, dict, dict]:
    config_path = os.path.join(os.path.dirname(__file__), "../../config/settings.json")
    with open(config_path, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    hmi_cfg = cfg.get("modbus_hmi", {})
    return (
        hmi_cfg.get("rtu", {}) or {},
        hmi_cfg.get("tcp", {}) or {},
        hmi_cfg.get("identity", {}) or {},
    )


_RTU_CFG, _TCP_CFG, _IDENTITY_CFG = _load_modbus_settings()


def _to_bit(value: int) -> int:
    """
    转为线圈位(0/1)，仅捕获可预期的类型/值错误。
    """
    try:
        return 1 if int(value) else 0
    except (ValueError, TypeError):
        return 0

def _to_u16(value: int) -> int:
    """
    转为无符号16位（两补码）
    """
    try:
        iv = int(value)
    except (ValueError, TypeError):
        iv = 0
    return iv & 0xFFFF

class DynamicModbusSlaveContext(ModbusSlaveContext):
    """
    直接从 processed_reg_map 提供数据。
    - FX=1: 线圈 -> 返回 int(0/1)
    - FX=3: 保持寄存器 -> 返回 16 位无符号
    - setValues 支持写入前/后回调，便于扩展业务逻辑
    """

    __slots__ = ("_req_count", "_last_beat_ts", "_beat_interval")

    def __init__(self, beat_interval: float = 5.0):
        super().__init__()
        self._req_count = 0
        self._last_beat_ts = time.time()
        self._beat_interval = beat_interval

    def _heartbeat(self) -> None:
        # 轻量级心跳日志（每 beat_interval 秒一次）
        now = time.time()
        elapsed = now - self._last_beat_ts
        if elapsed >= self._beat_interval:
            rps = self._req_count / elapsed if elapsed > 0 else 0.0
            logger.info("HMI Read heartbeat: count=%d, rps=%.1f", self._req_count, rps)
            self._req_count = 0
            self._last_beat_ts = now

    def getValues(self, fx, address, count=1):
        self._req_count += 1
        try:
            if fx == 1:
                # 线圈区读取，返回 0/1
                raw = processed_reg_map.get_coils(address, count)
                values = [1 if v else 0 for v in raw]
            elif fx == 3:
                # 保持寄存器区读取
                raw = processed_reg_map.get_registers(address, count)
                values = [_to_u16(v) for v in raw]
            else:
                values = [0] * count
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("HMI read fx=%s addr=%s cnt=%s -> %s", fx, address, count, values)
            self._heartbeat()
            return values
        except Exception as e:
            logger.error("HMI read error fx=%s addr=%s cnt=%s: %s", fx, address, count, e, exc_info=True)
            return [0] * count

    def setValues(self, fx, address, values):

        # 线圈相关写入
        if fx in (1, 5, 15):
            norm = [_to_bit(v) for v in values]
            for i, v in enumerate(norm):
                processed_reg_map.set_coil(address + i, v)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("HMI write coils fx=%s addr=%s values=%s", fx, address, norm)
            # logger.info("HMI write coils fx=%s addr=%s values=%s", fx, address, norm)
            return

        # 保持寄存器相关写入
        if fx in (3, 6, 16):
            norm = [_to_u16(v) for v in values]
            for i, v in enumerate(norm):
                processed_reg_map.set_register(address + i, v)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("HMI write registers fx=%s addr=%s values=%s", fx, address, norm)
            # logger.info("HMI write registers fx=%s addr=%s values=%s", fx, address, norm)
            return

        # 其他功能码忽略
        logger.debug("HMI write ignored fx=%s addr=%s values=%s", fx, address, values)

# Server 构建与运行
def _build_modbus_context(single: bool = True) -> ModbusServerContext:
    store = DynamicModbusSlaveContext()
    # single=True 性能更高，适配所有单元号；若必须区分单元号，可改为 single=False 并使用 {1: store}
    if single:
        return ModbusServerContext(slaves=store, single=True)
    return ModbusServerContext(slaves={1: store}, single=False)


def _run_modbus_rtu_server():
    """
    启动 Modbus RTU 服务器，失败自动重试。
    注意：StartSerialServer 为阻塞调用，需在后台线程中运行。
    """
    context = _build_modbus_context(single=True)

    identity = ModbusDeviceIdentification()
    identity.VendorName = _IDENTITY_CFG.get("VendorName", "")
    identity.ProductCode = _IDENTITY_CFG.get("ProductCode", "")
    identity.VendorUrl = _IDENTITY_CFG.get("VendorUrl", "")
    identity.ProductName = _IDENTITY_CFG.get("ProductName", "")
    identity.ModelName = _IDENTITY_CFG.get("ModelName", "")
    identity.MajorMinorRevision = _IDENTITY_CFG.get("MajorMinorRevision", "")

    logger.info("Preparing to start ModbusRTU slave...")
    # 更积极的串口参数，降低卡顿：较短超时与无重试
    port = _RTU_CFG.get("port", "COM1")
    baudrate = _RTU_CFG.get("baud_rate", 9600)
    bytesize = _RTU_CFG.get("byte_size", 8)
    parity = _RTU_CFG.get("parity", "N")
    stopbits = _RTU_CFG.get("stop_bits", 1)
    timeout = float(_RTU_CFG.get("timeout", 0.1))  # 建议 0.2~0.5
    # 额外 pyserial 参数（按需存在则传入）
    xonxoff = bool(_RTU_CFG.get("xonxoff", False))
    rtscts = bool(_RTU_CFG.get("rtscts", False))
    dsrdtr = bool(_RTU_CFG.get("dsrdtr", False))

    while True:
        try:
            StartSerialServer(
                context,
                identity=identity,
                port=port,
                baudrate=baudrate,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                timeout=timeout,
                xonxoff=xonxoff,
                rtscts=rtscts,
                dsrdtr=dsrdtr,
            )
            # 正常退出（一般不会发生）
            return
        except Exception as e:
            logger.warning("RTU slave startup failed:% s, will retry in 5 seconds...", e)
            time.sleep(5)


def start_modbus_hmi_server():
    """
    启动 Modbus HMI 从站（仅一次）。线程守护，不阻塞主流程。
    """
    global _modbus_hmi_thread_started
    with _modbus_hmi_thread_lock:
        if _modbus_hmi_thread_started:
            logger.warning("Modbus HMI Thread is already running, skipping duplicate starts")
            return
        _modbus_hmi_thread_started = True

    t = threading.Thread(target=_run_modbus_rtu_server, name="HMI-RTU-Server", daemon=True)
    t.start()
    logger.info("Modbus HMI server thread started.")