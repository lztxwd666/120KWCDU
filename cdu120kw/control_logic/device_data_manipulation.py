"""
处理原始寄存器数据，进行状态判定和数据转换，所有参数均从配置文件读取
"""

import inspect
import os
import threading
import time
from typing import Dict, Any, Optional

from cdu120kw.config.config_repository import ConfigRepository

# 基于当前文件位置构造绝对路径，保证在任意工作目录下都能找到配置
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.normpath(os.path.join(_BASE_DIR, "..", "config/cdu_120kw_component.json"))

# 使用集中式仓库加载
CONFIG_CACHE = ConfigRepository.load(_CONFIG_PATH).to_dict()

# 增加同步线程启动保护标志
_sync_thread_started = False
_sync_thread_lock = threading.Lock()

# 风扇停机定时器
_fan_shutdown_timer: Optional[threading.Timer] = None
_fan_shutdown_timer_lock = threading.Lock()

# 初始化时同步所有写入寄存器的值，为其增加标志和锁
_first_sync_flag = False  # 第一次同步标志
_first_sync_lock = threading.Lock()  # 第一次同步锁

# 防止重入标志
_we_guard = threading.local()

# 用于记录各类设备故障状态的持续时间
_fault_time = {
    "fan": {},
    "pump": {},
    "pv": {},
    "sensor": {},
}


# 线圈区（Coils）读写规划 - 基于排他性结束地址计算（END表示范围的下一个地址）

# 写入使能线圈：0（单个线圈）
COIL_WRITE_ENABLE = 0                               # 地址：0

# 风扇开关读取线圈范围：1-31（共31个线圈）
COIL_FAN_SWITCH_READ_START = 1                     # 起始地址：1
COIL_FAN_SWITCH_READ_END = 32                      # 结束地址：32（排他性，实际范围1-31）

# 风扇开关写入预留线圈范围：33-63（共31个线圈）
COIL_FAN_SWITCH_WRITE_START = 33                   # 起始地址：33
COIL_FAN_SWITCH_WRITE_END = 64                     # 结束地址：64（排他性，实际范围33-63）

# 风扇批量开关控制线圈：128（单个线圈）
FAN_BATCH_SWITCH_COIL = 128                        # 地址：128

# 水泵开关读取线圈范围：65-95（共31个线圈）
COIL_PUMP_SWITCH_READ_START = 65                   # 起始地址：65
COIL_PUMP_SWITCH_READ_END = 96                     # 结束地址：96（排他性，实际范围65-95）

# 水泵开关写入预留线圈范围：97-127（共31个线圈）
COIL_PUMP_SWITCH_WRITE_START = 97                  # 起始地址：97
COIL_PUMP_SWITCH_WRITE_END = 128                   # 结束地址：128（排他性，实际范围97-127）

# 水泵批量开关控制线圈：129（单个线圈）
PUMP_BATCH_SWITCH_COIL = 129                       # 地址：129

# IO输入线圈读取范围：200-231（共32个寄存器）
COIL_IO_INPUT_READ_START = 200                     # 起始地址：200
COIL_IO_INPUT_READ_END = 232                       # 结束地址：232（排他性，实际范围200-231）

# IO输出线圈读取范围：233-265（共32个寄存器）
COIL_IO_OUTPUT_READ_START = 233                    # 起始地址：233
COIL_IO_OUTPUT_READ_END = 265                      # 结束地址：265（排他性，实际范围233-264）

# IO输出线圈写入范围：266-295（共32个寄存器）
COIL_IO_OUTPUT_WRITE_START = 266                   # 起始地址：266
COIL_IO_OUTPUT_WRITE_END = 298                     # 结束地址：297（排他性，实际范围266-297）

# IO输出批量写入控制线圈 298 (单个线圈)
IO_OUTPUT_BATCH_SWITCH_COIL = 298                  # 地址：298


# 保持寄存器（Holding Registers）规划 - 基于排他性结束地址计算

# 自动控制模式的目标值寄存器：395、396、397（共3个寄存器）
CONTROL_MODE_TARGET_FLOW_REGISTER = 395            # 自动控制模式的目标流量寄存器地址：395
CONTROL_MODE_TARGET_TEMP_REGISTER = 396            # 自动控制模式的目标温度寄存器地址：396
CONTROL_MODE_TARGET_PRESSUREDIFF_REGISTER = 397    # 自动控制模式的目标压差寄存器地址：397

# 控制模式寄存器：399（值1/2/3/4，代表四种模式）
CONTROL_MODE = 399                # 地址：399


# 风扇寄存器定义 - 基于排他性结束地址计算

# 风扇占空比读取寄存器范围：400-431（共32个寄存器）
FAN_DUTY_READ_START = 400                          # 起始地址：400
FAN_DUTY_READ_END = FAN_DUTY_READ_START + 32       # 结束地址：432（排他性，实际范围400-431）

# 风扇占空比写入预留寄存器范围：432-463（共32个寄存器）
FAN_DUTY_WRITE_START = FAN_DUTY_READ_END           # 起始地址：432
FAN_DUTY_WRITE_END = FAN_DUTY_WRITE_START + 32     # 结束地址：464（排他性，实际范围432-463）

# 风扇电流读取寄存器范围：464-495（共32个寄存器）
FAN_CURRENT_START = FAN_DUTY_WRITE_END             # 起始地址：464
FAN_CURRENT_END = FAN_CURRENT_START + 32           # 结束地址：496（排他性，实际范围464-495）

# 风扇转速读取寄存器范围：496-527（共32个寄存器）
FAN_SPEED_START = FAN_CURRENT_END                  # 起始地址：496
FAN_SPEED_END = FAN_SPEED_START + 32               # 结束地址：528（排他性，实际范围496-527）

# 风扇状态读取寄存器范围：528-559（共32个寄存器）
FAN_STATUS_START = FAN_SPEED_END                   # 起始地址：528
FAN_STATUS_END = FAN_STATUS_START + 32             # 结束地址：560（排他性，实际范围528-559）

# 风扇批量占空比写入寄存器：560（单个寄存器）
FAN_BATCH_DUTY_REGISTER = FAN_STATUS_END           # 地址：560


# 水泵寄存器定义 - 基于排他性结束地址计算

# 水泵占空比读取寄存器范围：600-631（共32个寄存器）
PUMP_DUTY_READ_START = 600                         # 起始地址：600
PUMP_DUTY_READ_END = PUMP_DUTY_READ_START + 32     # 结束地址：632（排他性，实际范围600-631）

# 水泵占空比写入预留寄存器范围：632-663（共32个寄存器）
PUMP_DUTY_WRITE_START = PUMP_DUTY_READ_END         # 起始地址：632
PUMP_DUTY_WRITE_END = PUMP_DUTY_WRITE_START + 32   # 结束地址：664（排他性，实际范围632-663）

# 水泵电流读取寄存器范围：664-695（共32个寄存器）
PUMP_CURRENT_START = PUMP_DUTY_WRITE_END           # 起始地址：664
PUMP_CURRENT_END = PUMP_CURRENT_START + 32         # 结束地址：696（排他性，实际范围664-695）

# 水泵转速读取寄存器范围：696-727（共32个寄存器）
PUMP_SPEED_START = PUMP_CURRENT_END                # 起始地址：696
PUMP_SPEED_END = PUMP_SPEED_START + 32             # 结束地址：728（排他性，实际范围696-727）

# 水泵状态读取寄存器范围：728-759（共32个寄存器）
PUMP_STATUS_START = PUMP_SPEED_END                 # 起始地址：728
PUMP_STATUS_END = PUMP_STATUS_START + 32           # 结束地址：760（排他性，实际范围728-759）

# 水泵电压读取寄存器范围：760-763（共4个寄存器）
PUMP_VOLTAGE_START = PUMP_STATUS_END               # 起始地址：760
PUMP_VOLTAGE_END = PUMP_VOLTAGE_START + 4         # 结束地址：764（排他性，实际范围760-763）

# 水泵温度读取寄存器范围：764-767（共4个寄存器）
PUMP_TEMPERATURE_START = PUMP_VOLTAGE_END           # 起始地址：764
PUMP_TEMPERATURE_END = PUMP_TEMPERATURE_START + 4   # 结束地址：768（排他性，实际范围764-767）

# 水泵批量占空比写入寄存器：799（单个寄存器）
PUMP_BATCH_DUTY_REGISTER = 799        # 地址：799


# 比例阀寄存器定义 - 基于排他性结束地址计算

# 比例阀占空比读取寄存器范围：800-807（共8个寄存器）
PV_DUTY_READ_START = 800                           # 起始地址：800
PV_DUTY_READ_END = PV_DUTY_READ_START + 8          # 结束地址：808（排他性，实际范围800-807）

# 比例阀占空比写入预留寄存器范围：808-815（共8个寄存器）
PV_DUTY_WRITE_START = PV_DUTY_READ_END             # 起始地址：808
PV_DUTY_WRITE_END = PV_DUTY_WRITE_START + 8        # 结束地址：816（排他性，实际范围808-815）

# 比例阀实际电压读取寄存器范围：816-823（共8个寄存器）
PV_VOLTAGE_START = PV_DUTY_WRITE_END               # 起始地址：816
PV_VOLTAGE_END = PV_VOLTAGE_START + 8              # 结束地址：824（排他性，实际范围816-823）

# 比例阀状态读取寄存器范围：824-831（共8个寄存器）
PV_STATUS_START = PV_VOLTAGE_END                   # 起始地址：824
PV_STATUS_END = PV_STATUS_START + 8                # 结束地址：832（排他性，实际范围824-831）

# 比例阀批量占空比写入寄存器：832（单个寄存器）
PV_BATCH_DUTY_REGISTER = PV_STATUS_END             # 地址：832


# 温度传感器寄存器定义 - 基于排他性结束地址计算

# 温度值读取寄存器范围：900-931（共32个寄存器）
TEMP_VALUE_START = 900                             # 起始地址：900
TEMP_VALUE_END = TEMP_VALUE_START + 32             # 结束地址：932（排他性，实际范围900-931）

# 温差读取寄存器范围：932-939（共8个寄存器）
TEMP_DIFF_START = TEMP_VALUE_END                   # 起始地址：932
TEMP_DIFF_END = TEMP_DIFF_START + 8                # 结束地址：940（排他性，实际范围932-939）

# 温度状态读取寄存器范围：940-971（共32个寄存器）
TEMP_STATUS_START = TEMP_DIFF_END                  # 起始地址：940
TEMP_STATUS_END = TEMP_STATUS_START + 32           # 结束地址：972（排他性，实际范围940-971）


# 压力传感器寄存器定义 - 基于排他性结束地址计算

# 压力值读取寄存器范围：1000-1031（共32个寄存器）
PRESS_VALUE_START = 1000                           # 起始地址：1000
PRESS_VALUE_END = PRESS_VALUE_START + 32           # 结束地址：1032（排他性，实际范围1000-1031）

# 压差读取寄存器范围：1032-1039（共8个寄存器）
PRESS_DIFF_START = PRESS_VALUE_END                 # 起始地址：1032
PRESS_DIFF_END = PRESS_DIFF_START + 8              # 结束地址：1040（排他性，实际范围1032-1039）

# 压力状态读取寄存器范围：1040-1071（共32个寄存器）
PRESS_STATUS_START = PRESS_DIFF_END                # 起始地址：1040
PRESS_STATUS_END = PRESS_STATUS_START + 32         # 结束地址：1072（排他性，实际范围1040-1071）


# 流量传感器寄存器定义 - 基于排他性结束地址计算

# 流量值读取寄存器范围：1100-1107（共8个寄存器）
FLOW_VALUE_START = 1100                            # 起始地址：1100
FLOW_VALUE_END = FLOW_VALUE_START + 8              # 结束地址：1108（排他性，实际范围1100-1107）

# 流量状态读取寄存器范围：1108-1115（共8个寄存器）
FLOW_STATUS_START = FLOW_VALUE_END                 # 起始地址：1108
FLOW_STATUS_END = FLOW_STATUS_START + 8            # 结束地址：1116（排他性，实际范围1108-1115）

# 制冷量读取寄存器范围：1116-1119（共4个寄存器）
COOLING_CAPACITY_START = FLOW_STATUS_END           # 起始地址：1116
COOLING_CAPACITY_END = COOLING_CAPACITY_START + 4  # 结束地址：1120（排他性，实际范围1116-1119）

# PH值读取寄存器范围：1120-1127（共8个寄存器）
PH_VALUE_START = COOLING_CAPACITY_END              # 起始地址：1120
PH_VALUE_END = PH_VALUE_START + 8                  # 结束地址：1128（排他性，实际范围1120-1127）

# PH传感器状态读取寄存器范围：1128-1135（共8个寄存器）
PH_STATUS_START = PH_VALUE_END                     # 起始地址：1128
PH_STATUS_END = PH_STATUS_START + 8                # 结束地址：1136（排他性，实际范围1128-1135）

# 扩展传感器寄存器定义 - 基于排他性结束地址计算

# 环境传感器数值读取寄存器范围：1136-1143（共16个寄存器）
ENVIRONMENT_VALUE_START = PH_STATUS_END        # 起始地址：1136
ENVIRONMENT_VALUE_END = ENVIRONMENT_VALUE_START + 16  # 结束地址：1152（排他性，实际范围1136-1151）

# 环境传感器状态读取寄存器范围：1152-1167（共16个寄存器）
ENVIRONMENT_STATUS_START = ENVIRONMENT_VALUE_END     # 起始地址：1152
ENVIRONMENT_STATUS_END = ENVIRONMENT_STATUS_START + 16  # 结束地址：1168（排他性，实际范围1144-1167）


class ProcessedRegisterMap:
    """
    存储处理后数据的寄存器表，分为线圈(coils)和保持寄存器(registers)
    """

    def __init__(self):
        """
        初始化寄存器映射表
        线圈范围：0-379，保持寄存器范围：0-65535
        """
        # 线圈初始化：使用字典推导式预初始化 0-379
        self.coils = {c: 0 for c in range(0, 379)}

        # 保持寄存器初始化：使用字典推导式预初始化 0-65535，避免动态添加地址导致KeyError
        self.registers = {r: 0 for r in range(0, 65536)}

        # 设置目标值寄存器初始值
        self.registers[CONTROL_MODE] = 1                             # 控制模式初始值 1 (手动模式)
        self.registers[CONTROL_MODE_TARGET_FLOW_REGISTER] = 500      # 目标流量初始值 500 (50.0 L/min)
        self.registers[CONTROL_MODE_TARGET_TEMP_REGISTER] = 250      # 目标温度初始值 250 (25.0°C)
        self.registers[CONTROL_MODE_TARGET_PRESSUREDIFF_REGISTER] = 50  # 目标压差初始值 50 (0.5 MPa)

        # 设置比例阀写入寄存器初始值为10000（100%占空比）
        pv_count = len(CONFIG_CACHE.get("proportional_valve", []))
        for i in range(pv_count):
            self.registers[PV_DUTY_WRITE_START + i] = 10000

        # 回调函数列表初始化
        self._write_coil_callbacks = []
        self._write_register_callbacks = []

        # 定义所有需要初始化的寄存器范围组，便于统一管理和扩展
        self._register_range_groups = [
            # 风扇相关寄存器范围
            (FAN_DUTY_READ_START, FAN_DUTY_READ_END),
            (FAN_DUTY_WRITE_START, FAN_DUTY_WRITE_END),
            (FAN_CURRENT_START, FAN_CURRENT_END),
            (FAN_SPEED_START, FAN_SPEED_END),
            (FAN_STATUS_START, FAN_STATUS_END),

            # 水泵相关寄存器范围
            (PUMP_DUTY_READ_START, PUMP_DUTY_READ_END),
            (PUMP_DUTY_WRITE_START, PUMP_DUTY_WRITE_END),
            (PUMP_CURRENT_START, PUMP_CURRENT_END),
            (PUMP_SPEED_START, PUMP_SPEED_END),
            (PUMP_STATUS_START, PUMP_STATUS_END),
            (PUMP_VOLTAGE_START, PUMP_VOLTAGE_END),
            (PUMP_TEMPERATURE_START, PUMP_TEMPERATURE_END),

            # 比例阀相关寄存器范围
            (PV_DUTY_READ_START, PV_DUTY_READ_END),
            (PV_DUTY_WRITE_START, PV_DUTY_WRITE_END),
            (PV_VOLTAGE_START, PV_VOLTAGE_END),
            (PV_STATUS_START, PV_STATUS_END),

            # 温度传感器相关寄存器范围
            (TEMP_VALUE_START, TEMP_VALUE_END),
            (TEMP_DIFF_START, TEMP_DIFF_END),
            (TEMP_STATUS_START, TEMP_STATUS_END),

            # 压力传感器相关寄存器范围
            (PRESS_VALUE_START, PRESS_VALUE_END),
            (PRESS_DIFF_START, PRESS_DIFF_END),
            (PRESS_STATUS_START, PRESS_STATUS_END),

            # 流量传感器相关寄存器范围
            (FLOW_VALUE_START, FLOW_VALUE_END),
            (FLOW_STATUS_START, FLOW_STATUS_END),

            # 环境传感器相关寄存器范围
            (COOLING_CAPACITY_START, COOLING_CAPACITY_END),
            (PH_VALUE_START, PH_VALUE_END),
            (PH_STATUS_START, PH_STATUS_END),
            (ENVIRONMENT_VALUE_START, ENVIRONMENT_VALUE_END),
            (ENVIRONMENT_STATUS_START, ENVIRONMENT_STATUS_END),
        ]

        # 使用统一方法初始化所有寄存器范围
        self._initialize_all_registers()

        # 定义写入范围，限定回调函数作用范围只作用于写入区
        self._define_write_ranges()

    def _initialize_all_registers(self):
        """
        统一初始化所有寄存器范围
        """
        # 遍历所有寄存器范围组，确保每个范围都被正确初始化
        for start_addr, end_addr in self._register_range_groups:
            # 这里可以添加特殊初始化逻辑，目前所有寄存器都已初始化为0
            # 保留此循环以便未来可能需要特殊初始化某些寄存器范围
            pass

    def _define_write_ranges(self):
        """
        统一定义写入范围，限定回调函数作用范围
        """
        # 线圈写入范围：只允许在这些范围内的线圈写入操作触发回调
        self._coil_write_ranges = [
            # 风扇开关写入预留范围
            (COIL_FAN_SWITCH_WRITE_START, COIL_FAN_SWITCH_WRITE_END),
            # 水泵开关写入预留范围
            (COIL_PUMP_SWITCH_WRITE_START, COIL_PUMP_SWITCH_WRITE_END),
            # IO输出线圈写入范围
            (COIL_IO_OUTPUT_WRITE_START, COIL_IO_OUTPUT_WRITE_END),
            # 风扇批量开关控制线圈
            (FAN_BATCH_SWITCH_COIL, FAN_BATCH_SWITCH_COIL + 1),
            # 水泵批量开关控制线圈
            (PUMP_BATCH_SWITCH_COIL, PUMP_BATCH_SWITCH_COIL + 1),
            # IO输出批量写入控制线圈
            (IO_OUTPUT_BATCH_SWITCH_COIL, IO_OUTPUT_BATCH_SWITCH_COIL + 1),
            # 写入使能线圈
            (COIL_WRITE_ENABLE, COIL_WRITE_ENABLE + 1),
        ]

        # 保持寄存器写入范围：只允许在这些范围内的寄存器写入操作触发回调
        self._register_write_ranges = [
            # 控制模式相关寄存器
            (CONTROL_MODE, CONTROL_MODE + 1),
            (CONTROL_MODE_TARGET_FLOW_REGISTER, CONTROL_MODE_TARGET_FLOW_REGISTER + 1),
            (CONTROL_MODE_TARGET_TEMP_REGISTER, CONTROL_MODE_TARGET_TEMP_REGISTER + 1),
            (CONTROL_MODE_TARGET_PRESSUREDIFF_REGISTER, CONTROL_MODE_TARGET_PRESSUREDIFF_REGISTER + 1),

            # 风扇、水泵、比例阀占空比写入预留范围
            (FAN_DUTY_WRITE_START, FAN_DUTY_WRITE_END),
            (PUMP_DUTY_WRITE_START, PUMP_DUTY_WRITE_END),
            (PV_DUTY_WRITE_START, PV_DUTY_WRITE_END),
            # 批量占空比写入寄存器
            (FAN_BATCH_DUTY_REGISTER, FAN_BATCH_DUTY_REGISTER + 1),
            (PUMP_BATCH_DUTY_REGISTER, PUMP_BATCH_DUTY_REGISTER + 1),
            (PV_BATCH_DUTY_REGISTER, PV_BATCH_DUTY_REGISTER + 1),
        ]

    @staticmethod
    def _in_ranges(address: int, ranges) -> bool:
        """
        检查地址是否在指定的范围内

        Args:
            address: 要检查的地址
            ranges: 范围列表，每个元素为(start, end)元组

        Returns:
            bool: 如果地址在任何范围内返回True，否则返回False
        """
        return any(start <= address < end for start, end in ranges)

    def set_coil(self, address: int, value: int, force=False, trigger_callback=True):
        """
        设置线圈值，如果地址在写入范围内且存在回调函数，则触发回调
        Args:
            address: 线圈地址
            value: 要设置的值（0或1）
            force: 是否强制设置，忽略写入范围检查（默认为False）
            trigger_callback: 是否触发回调（默认为True）
        """
        # 检查地址是否在有效范围内
        if address not in self.coils:
            return

        # 设置线圈值，确保值为0或1
        self.coils[address] = 1 if value else 0

        # 如果没有回调函数或地址不在写入范围内，直接返回
        if not trigger_callback or not self._write_coil_callbacks or (not force and not self._in_ranges(address, self._coil_write_ranges)):
            return

        # 获取设置后的值并触发所有回调函数
        val = self.coils[address]
        for cb in self._write_coil_callbacks:
            cb(address, val)

    def set_register(self, address: int, value: int, trigger_callback=True):
        """
        设置寄存器值，如果地址在写入范围内且存在回调函数，则触发回调
        Args:
            address: 寄存器地址
            value: 要设置的值
            trigger_callback: 是否触发回调（默认为True）
        """
        # 检查地址是否在有效范围内
        if address not in self.registers:
            return

        # 直接写入，统一转换为整数
        self.registers[address] = int(value)

        # 如果没有回调函数或地址不在写入范围内，直接返回
        if not trigger_callback or not self._write_register_callbacks or not self._in_ranges(address, self._register_write_ranges):
            return

        # 获取设置后的值并触发所有回调函数
        val = self.registers[address]
        for cb in self._write_register_callbacks:
            cb(address, val)

    def write_coil_callback(self, cb):
        """
        添加线圈写入回调函数

        Args:
            cb: 回调函数，格式为 cb(address, value)
        """
        self._write_coil_callbacks.append(cb)

    def write_register_callback(self, cb):
        """
        添加寄存器写入回调函数

        Args:
            cb: 回调函数，格式为 cb(address, value)
        """
        self._write_register_callbacks.append(cb)

    def get_coil(self, address: int) -> int:
        """
        获取单个线圈的值

        Args:
            address: 线圈地址

        Returns:
            int: 线圈值，如果地址不存在则返回0
        """
        return self.coils.get(address, 0)

    def get_register(self, address: int) -> int:
        """
        获取单个寄存器的值

        Args:
            address: 寄存器地址

        Returns:
            int: 寄存器值，如果地址不存在则返回0
        """
        return self.registers.get(address, 0)

    def get_coils(self, address: int, count: int) -> list:
        """
        获取多个连续线圈的值

        Args:
            address: 起始地址
            count: 要获取的线圈数量

        Returns:
            list: 线圈值列表
        """
        return [self.coils.get(a, 0) for a in range(address, address + count)]

    def get_registers(self, address: int, count: int) -> list:
        """
        获取多个连续寄存器的值

        Args:
            address: 起始地址
            count: 要获取的寄存器数量

        Returns:
            list: 寄存器值列表
        """
        return [self.registers.get(a, 0) for a in range(address, address + count)]

    def reset(self):
        """
        重置所有线圈和寄存器值为0
        """
        # 重置所有线圈值为0
        for k in self.coils:
            self.coils[k] = 0

        # 重置所有寄存器值为0
        for k in self.registers:
            self.registers[k] = 0

# 全局处理后寄存器表实例，供外部访问
processed_reg_map = ProcessedRegisterMap()

def to_u16(val):
    """负数转U16输出，两补码，正数不变"""
    return (val + 0x10000) & 0xFFFF if val < 0 else val

# 风扇状态处理函数
def process_fan_state(
        fan_cfg: dict,
        registers: dict,
        coils: dict,
        fan_index: int,
        now=None):
    """
    风扇状态处理
    - 开关读取：线圈 COIL_FAN_SWITCH_READ_START + idx
    - 占空比（U16）写入：FAN_DUTY_READ_START + idx
    - 电流（S16）写入：FAN_CURRENT_START + idx
    - 转速（U16）写入：FAN_SPEED_START + idx
    - 状态写入：FAN_STATUS_START + idx
    说明：
    - 读源数据仍从原始寄存器地址（配置）获取；
    - 处理后写入到新处理映射 processed_reg_map 的新分段地址；
    - 故障判定保留 8 秒延迟确认机制。
    """
    if now is None:
        now = time.time()
    status_coil_addr = COIL_FAN_SWITCH_READ_START + fan_index
    status_val = coils.get(status_coil_addr, 0)

    # 电流原始地址
    current_addr = fan_cfg.get("r_d_current_address", {}).get("local")
    current = registers.get(current_addr, 0) if current_addr is not None else 0

    duty_cycle = 0  # 预留
    speed = 0       # 预留

    # 状态判定逻辑
    # 状态: 0=停止，1=运行正常，2=故障
    # 判定依据：风扇开关状态 + 电流
    # 风扇开启且电流大于 100mA 视为正常运行
    # 风扇开启但电流小于等于 100mA 且持续超过 8 秒视为故障
    # 风扇关闭视为停止状态

    # 状态判定逻辑
    # 状态定义：0=停止，1=运行正常，2=故障
    # 判定规则：
    # - 若开关开启
    #     - 电流>=100mA -> 1（正常）
    #     - 电流<100mA 且持续>=8s -> 2（故障）
    #     - 否则 -> 0（暂不判为故障）
    state = 0
    key = f"fan_{fan_index}"
    if status_val == 1:
        if current > 100:
            state = 1
            _fault_time["fan"][key] = 0
        else:
            if _fault_time["fan"].get(key, 0) == 0:
                _fault_time["fan"][key] = now
            elif now - _fault_time["fan"][key] >= 8:
                state = 2
            else:
                state = 0
    else:
        state = 0
        _fault_time["fan"][key] = 0

    # 写入到新地址分段
    u16_current = to_u16(current)
    processed_reg_map.set_coil(status_coil_addr, status_val)
    processed_reg_map.set_register(FAN_DUTY_READ_START + fan_index, duty_cycle)
    processed_reg_map.set_register(FAN_CURRENT_START + fan_index, u16_current)
    processed_reg_map.set_register(FAN_SPEED_START + fan_index, speed)
    processed_reg_map.set_register(FAN_STATUS_START + fan_index, state)

    return {
        "status": status_val,
        "current": u16_current,
        "duty_cycle": duty_cycle,
        "speed": speed,
        "state": state,
    }

# 水泵状态处理
def process_pump_state(
        pump_cfg: dict,
        registers: dict,
        coils: dict,
        pump_index: int,
        now=None):
    """
    水泵状态处理
    - 开关读取：线圈 COIL_PUMP_SWITCH_READ_START + idx
    - 占空比（U16）写入：PUMP_DUTY_READ_START + idx
    - 电流（S16）写入：PUMP_CURRENT_START + idx
    - 转速（U16）写入：PUMP_SPEED_START + idx
    - 状态写入：PUMP_STATUS_START + idx
    说明：
    - 读源数据仍从原始寄存器地址（配置）获取；
    - 处理后写入到新处理映射 processed_reg_map 的新分段地址；
    - 故障判定保留 8 秒延迟确认机制。
    """
    if now is None:
        now = time.time()
    name = pump_cfg.get("name", f"Pump{pump_index+1}")

    # 读取“开关”线圈（外部\*读\*区），仅用于状态判定与回显
    coil_addr = COIL_PUMP_SWITCH_READ_START + pump_index
    switch_on = 1 if coils.get(coil_addr, 0) else 0

    # 占空比（U16，来自设备原始寄存器或上位配置指定地址）
    duty_addr = pump_cfg.get("rw_d_duty_register_address", {}).get("local")
    duty_cycle = registers.get(duty_addr, 0) if duty_addr is not None else 0

    # 电流（S16）
    current_addr = pump_cfg.get("r_d_current_address", {}).get("local")
    current = registers.get(current_addr, 0) if current_addr is not None else 0

    # 转速（U16）
    speed_addr = pump_cfg.get("r_d_speed_address", {}).get("local")
    speed = registers.get(speed_addr, 0) if speed_addr is not None else 0

    # 读取电压（U16）
    voltage_addr = pump_cfg.get("r_d_voltage_address", {}).get("local")
    voltage = registers.get(voltage_addr, 0) if voltage_addr is not None else 0

    # 读取温度（U16）
    temperature_addr = pump_cfg.get("r_d_temperature_address", {}).get("local")
    temperature = registers.get(temperature_addr, 0) if temperature_addr is not None else 0


    # 状态判定逻辑
    # 状态定义：0=停止，1=运行正常，2=故障
    # 判定规则：
    # - 若开关关闭 -> 0
    # - 若开关开启且占空比>=min_duty：
    #     - 电流>=100mA -> 1（正常）
    #     - 电流<100mA 且持续>=8s -> 2（故障）
    #     - 否则 -> 0（暂不判为故障）
    min_duty = pump_cfg.get("min_duty", 0)
    state = 0
    key = f"pump_{pump_index}"
    if switch_on == 1 and duty_cycle >= int(min_duty):
        if current >= 100:
            state = 1
            _fault_time["pump"][key] = 0
        else:
            if _fault_time["pump"].get(key, 0) == 0:
                _fault_time["pump"][key] = now
            elif now - _fault_time["pump"][key] >= 8:
                state = 2
            else:
                state = 0
    else:
        state = 0
        _fault_time["pump"][key] = 0

    # 写入到新地址分段
    u16_current = to_u16(current)
    processed_reg_map.set_coil(coil_addr, switch_on)
    processed_reg_map.set_register(PUMP_DUTY_READ_START + pump_index, int(duty_cycle * 100))
    processed_reg_map.set_register(PUMP_CURRENT_START + pump_index, int(u16_current))
    processed_reg_map.set_register(PUMP_SPEED_START + pump_index, int(speed))
    processed_reg_map.set_register(PUMP_STATUS_START + pump_index, int(state))
    processed_reg_map.set_register(PUMP_VOLTAGE_START + pump_index, int(voltage * 100))
    processed_reg_map.set_register(PUMP_TEMPERATURE_START + pump_index, int(temperature * 10))

    return {
        "name": name,
        "switch": switch_on,
        "duty_cycle": int(duty_cycle),
        "current": int(u16_current),
        "speed": int(speed),
        "state": int(state),
        "voltage": int(voltage),
        "temperature": int(temperature),
    }

# 比例阀状态处理
def process_proportional_valve_state(
    pv_cfg: dict,
    registers: dict,
    pv_index: int,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """
    比例阀状态处理（地址已切换到新规划）:
    - 占空比（U16）写入：PV_DUTY_READ_START + idx
    - 实际电压（U16）写入：PV_VOLTAGE_START + idx
    - 状态写入：PV_STATUS_START + idx
    说明：
    - 读源数据仍从原始寄存器地址（配置）获取；
    - 处理后写入到新处理映射 processed_reg_map 的新分段地址；
    - 状态判定带 8 秒延时确认机制。
    """
    if now is None:
        now = time.time()
    name = pv_cfg.get("name", f"Pv{pv_index+1}")

    # 占空比（U16）
    duty_addr = pv_cfg.get("rw_d_duty_register_address", {}).get("local")
    duty_cycle = registers.get(duty_addr, 0) if duty_addr is not None else 0

    # 实际电压（U16）
    voltage_addr = pv_cfg.get("r_d_voltage_address", {}).get("local")
    voltage = registers.get(voltage_addr, 0) if voltage_addr is not None else 0

    # 状态判定（带 12s 故障延时）
    # 状态定义：0=待机/关闭，1=运行正常，2=故障
    # 参考判定（示例阈值，保持与现有逻辑风格一致）：
    # - voltage < 1990：若 duty 较高但电压过低，判为故障（延时确认）；
    # - duty < 2000 且 1990 <= voltage < 2050：待机；
    # - duty >= 2000 且 voltage >= 1990：正常；
    # - 其它情况：待机。
    state = 0
    key = f"pv_{pv_index}"
    if voltage < 1990:
        # 电压明显偏低：若 duty 已经较高，持续低电压才判故障
        if duty_cycle >= 2000:
            if _fault_time["pv"].get(key, 0) == 0:
                _fault_time["pv"][key] = now
            elif now - _fault_time["pv"][key] >= 12:
                state = 2
            else:
                state = 0
        else:
            state = 0
    elif duty_cycle < 2000 and 1990 <= voltage < 2050:
        state = 0
        _fault_time["pv"][key] = 0
    elif duty_cycle >= 2000 and voltage >= 2050:
        state = 1
        _fault_time["pv"][key] = 0
    else:
        state = 0
        _fault_time["pv"][key] = 0

    # 写入“处理后寄存器映射”的新地址区间
    processed_reg_map.set_register(PV_DUTY_READ_START + pv_index, int(duty_cycle))
    processed_reg_map.set_register(PV_VOLTAGE_START + pv_index, int(voltage))
    processed_reg_map.set_register(PV_STATUS_START + pv_index, int(state))

    return {
        "name": name,
        "duty_cycle": int(duty_cycle),
        "voltage": int(voltage),
        "state": int(state),
    }

# 温度传感器状态处理
def process_temperature_state(sensor_cfg, registers, sensor_index, now=None):
    """
    温度处理:
    - 温度值区: TEMP_VALUE_START + idx
    - 温差区: TEMP_DIFF_START + idx
    - 状态区: TEMP_STATUS_START + idx
    """
    if now is None:
        now = time.time()
    raw_addr = sensor_cfg.get("r_d_temperature_address", {}).get("local")
    raw_val = registers.get(raw_addr, 0)

    offset1 = float(sensor_cfg.get("offset1", 0))
    offset2 = float(sensor_cfg.get("offset2", 0))
    gain1 = float(sensor_cfg.get("gain1", 1))
    gain2 = float(sensor_cfg.get("gain2", 1))
    gain3 = float(sensor_cfg.get("gain3", 1))
    decimals = int(sensor_cfg.get("r_d_temperature_decimals", 1))
    calc_val = (raw_val + offset1 + offset2) * gain1 * gain2 * gain3
    calc_val_int = int(round(calc_val))

    min_v = sensor_cfg.get("min_temperature", -273)
    max_v = sensor_cfg.get("max_temperature", 999)

    # 状态判定逻辑
    # 状态: 0=传感器故障，1=正常，2=低于下限，3=高于上限
    key = f"T_{sensor_index}"
    state = 1
    if calc_val > 2000 or calc_val < -1000:
        if _fault_time["sensor"].get(key, 0) == 0:
            _fault_time["sensor"][key] = now
        elif now - _fault_time["sensor"][key] >= 8:
            state = 0
    elif calc_val < min_v:
        if _fault_time["sensor"].get(key, 0) == 0:
            _fault_time["sensor"][key] = now
        elif now - _fault_time["sensor"][key] >= 8:
            state = 2
    # 此处温度值为保留一位小数值的温度，因此需要缩放10倍
    elif calc_val > (max_v * 10**decimals):
        if _fault_time["sensor"].get(key, 0) == 0:
            _fault_time["sensor"][key] = now
        elif now - _fault_time["sensor"][key] >= 8:
            state = 3
    else:
        state = 1
        _fault_time["sensor"][key] = 0

    # 写入“处理后寄存器映射”的新地址区间
    u16_calc_val_int = to_u16(calc_val_int)
    processed_reg_map.set_register(TEMP_VALUE_START + sensor_index, u16_calc_val_int)
    processed_reg_map.set_register(TEMP_DIFF_START + sensor_index, 0)
    processed_reg_map.set_register(TEMP_STATUS_START + sensor_index, state)

    # print(f"Temp Sensor {sensor_index}: Raw={raw_val}, Calc={calc_val:.2f}, State={state}")

    return {
        "value": u16_calc_val_int,
        "state": state,
    }

# 压力传感器状态处理
def process_pressure_state(sensor_cfg, registers, sensor_index, now=None):
    """
    压力传感器处理:
    - 数值（S16，建议按配置小数位缩放写入）-> PRESS_VALUE_START + idx
    - 状态 -> PRESS_STATUS_START + idx
    - 压差寄存器 PRESS_DIFF_START 仅预留（不在本函数写入）
    状态定义：0=传感器故障，1=正常，2=低于下限，3=高于上限
    故障延时：8 秒
    """
    if now is None:
        now = time.time()
    name = sensor_cfg.get("name", f"P{sensor_index+1}")
    addr = sensor_cfg.get("r_d_pressure_address", {}).get("local")
    decimals = int(sensor_cfg.get("r_d_pressure_decimals", 2))  # 小数位，仅用于缩放
    min_v = sensor_cfg.get("min_pressure", -999)
    max_v = sensor_cfg.get("max_pressure", 999)

    # 原始读数
    raw_val = registers.get(addr, 0)
    offset1 = float(sensor_cfg.get("offset1", 0))
    offset2 = float(sensor_cfg.get("offset2", 0))
    gain1 = float(sensor_cfg.get("gain1", 1))
    gain2 = float(sensor_cfg.get("gain2", 1))
    gain3 = float(sensor_cfg.get("gain3", 1))
    calc_val = (raw_val + offset1) * gain1 * gain2 * gain3 + offset2

    # 按小数位缩放写入 S16（例如 decimals=2 -> 乘以 100）
    scale = 10 ** decimals
    calc_val_int = int(round(calc_val * scale))

    # 状态判定（带 8s 延时）
    state = 1
    key = f"P_{sensor_index}"
    if calc_val_int < -50:
        # 近零判为可能断线/故障，需 8s 确认
        if _fault_time["sensor"].get(key, 0) == 0:
            _fault_time["sensor"][key] = now
        elif now - _fault_time["sensor"][key] >= 8:
            state = 0
        else:
            state = 1
    elif calc_val_int < min_v:
        if _fault_time["sensor"].get(key, 0) == 0:
            _fault_time["sensor"][key] = now
        elif now - _fault_time["sensor"][key] >= 8:
            state = 2
        else:
            state = 1
    elif calc_val_int > (max_v * 10**decimals):
        if _fault_time["sensor"].get(key, 0) == 0:
            _fault_time["sensor"][key] = now
        elif now - _fault_time["sensor"][key] >= 8:
            state = 3
        else:
            state = 1
    else:
        state = 1
        _fault_time["sensor"][key] = 0

    # 写入“处理后寄存器映射”的新地址区间
    u16_calc_val_int = to_u16(calc_val_int)
    processed_reg_map.set_register(PRESS_VALUE_START + sensor_index, int(u16_calc_val_int))
    processed_reg_map.set_register(PRESS_STATUS_START + sensor_index, int(state))

    # print(f"Pressure Sensor {sensor_index}: Raw={raw_val}, Calc={calc_val:.2f}, State={state}")

    return {
        "name": name,
        "value": int(u16_calc_val_int),
        "state": int(state),
    }

# 流量传感器状态处理
def process_flow_state(sensor_cfg, registers, sensor_index, now=None):
    """
    流量传感器处理
    - 数值（S16，按配置小数位缩放写入）-> FLOW_VALUE_START + idx
    - 状态 -> FLOW_STATUS_START + idx
    状态定义：0=传感器故障，1=正常，2=低于下限，3=高于上限
    故障延时：8 秒
    """
    if now is None:
        now = time.time()
    name = sensor_cfg.get("name", f"F{sensor_index+1}")
    addr = sensor_cfg.get("r_d_flow_address", {}).get("local")
    decimals = int(sensor_cfg.get("r_d_flow_decimals", 1))  # 缩放小数位
    min_v = sensor_cfg.get("min_flow", -999)
    max_v = sensor_cfg.get("max_flow", 999)

    # 原始读数
    raw_val = registers.get(addr, 0)
    offset1 = float(sensor_cfg.get("offset1", 0))
    offset2 = float(sensor_cfg.get("offset2", 0))
    gain1 = float(sensor_cfg.get("gain1", 1))
    gain2 = float(sensor_cfg.get("gain2", 1))
    gain3 = float(sensor_cfg.get("gain3", 1))
    calc_val = (raw_val + offset1) * gain1 * gain2 * gain3 + offset2

    # 按小数位缩放写入 S16（例如 decimals=1 -> 乘以 10）
    scale = 10 ** decimals
    calc_val_int = int(round(calc_val * scale))

    # 状态判定（带 8s 延时）
    state = 1
    key = f"F_{sensor_index}"
    if calc_val < -20:
        if _fault_time["sensor"].get(key, 0) == 0:
            _fault_time["sensor"][key] = now
        elif now - _fault_time["sensor"][key] >= 8:
            state = 0
        else:
            state = 1
    elif calc_val < min_v:
        if _fault_time["sensor"].get(key, 0) == 0:
            _fault_time["sensor"][key] = now
        elif now - _fault_time["sensor"][key] >= 8:
            state = 2
        else:
            state = 1
    elif calc_val > max_v:
        if _fault_time["sensor"].get(key, 0) == 0:
            _fault_time["sensor"][key] = now
        elif now - _fault_time["sensor"][key] >= 8:
            state = 3
        else:
            state = 1
    else:
        state = 1
        _fault_time["sensor"][key] = 0

    # 写入“处理后寄存器映射”的新地址区间
    u16_calc_val_int = to_u16(calc_val_int)
    processed_reg_map.set_register(FLOW_VALUE_START + sensor_index, int(u16_calc_val_int))
    processed_reg_map.set_register(FLOW_STATUS_START + sensor_index, int(state))

    # print(f"Flow Sensor {sensor_index}: Raw={raw_val}, Calc={calc_val:.2f}, State={state}")

    return {
        "name": name,
        "value": int(u16_calc_val_int),
        "state": int(state),
    }

# PH 传感器状态处理
def process_ph_state(sensor_cfg: dict, registers: dict, sensor_index: int, now: float = None):
    """
    PH 传感器处理:
    - 数值（S16，按配置小数位缩放写入）-> PH_VALUE_START + idx
    - 状态 -> PH_STATUS_START + idx
    状态定义：0=异常，1=正常（边界值正常）
    """
    if now is None:
        now = time.time()

    # 读取配置参数
    addr = sensor_cfg.get("r_d_ph_address", {}).get("local")
    decimals = int(sensor_cfg.get("r_d_ph_decimals", 1))
    min_v = float(sensor_cfg.get("min_ph", 0))
    max_v = float(sensor_cfg.get("max_ph", 14))

    # 原始寄存器值（未校准）
    raw_val = registers.get(addr, 0)

    # 校准参数
    offset1 = float(sensor_cfg.get("offset1", 0))
    offset2 = float(sensor_cfg.get("offset2", 0))
    gain1 = float(sensor_cfg.get("gain1", 1))
    gain2 = float(sensor_cfg.get("gain2", 1))
    gain3 = float(sensor_cfg.get("gain3", 1))

    # 计算物理量
    calc_val = (raw_val + offset1) * gain1 * gain2 * gain3 + offset2

    # 缩放为整数寄存器值
    scale = 10 ** decimals
    calc_val_int = int(round(calc_val * scale))

    # 状态判定（带 8s 延时）
    key = f"PH_{sensor_index}"
    state = 1
    if calc_val < min_v or calc_val > max_v:
        if _fault_time["sensor"].get(key, 0) == 0:
            _fault_time["sensor"][key] = now
        elif now - _fault_time["sensor"][key] >= 8:
            state = 0
        else:
            state = 1
    else:
        state = 1
        _fault_time["sensor"][key] = 0

    # 写入处理后寄存器
    u16_calc_val_int = to_u16(calc_val_int)
    processed_reg_map.set_register(PH_VALUE_START + sensor_index, u16_calc_val_int)
    processed_reg_map.set_register(PH_STATUS_START + sensor_index, state)

    # print(f"PH Sensor {sensor_index}: Raw={raw_val}, Calc={calc_val:.2f}, State={state}")

    return {
        "name": sensor_cfg.get("name", "PH"),
        "value": u16_calc_val_int,
        "state": state,
    }

# 环境传感器状态处理
def process_environment_state(sensor_cfg, registers, sensor_index, now=None):
    """
    环境传感器处理:
    - 数值区: ENVIRONMENT_VALUE_START + idx
    - 状态区: ENVIRONMENT_STATUS_START + idx
    状态: 0=传感器故障，1=正常，2=低于下限，3=高于上限
    """
    if now is None:
        now = time.time()
    raw_addr = sensor_cfg.get("r_d_pht_address", {}).get("local")
    raw_val = registers.get(raw_addr, 0)

    offset1 = float(sensor_cfg.get("offset1", 0))
    offset2 = float(sensor_cfg.get("offset2", 0))
    gain1 = float(sensor_cfg.get("gain1", 1))
    gain2 = float(sensor_cfg.get("gain2", 1))
    gain3 = float(sensor_cfg.get("gain3", 1))
    decimals = int(sensor_cfg.get("r_d_pht_decimals", 1))
    min_v = float(sensor_cfg.get("min_pht", -273))
    max_v = float(sensor_cfg.get("max_pht", 999))

    # 计算物理量
    calc_val = (raw_val + offset1 + offset2) * gain1 * gain2 * gain3

    # 上位机取的三个值只保留一位小数，读取上来的值保留两位小数，因此需要 /10
    calc_val_int = int(round(calc_val / 10))

    # 状态判定逻辑
    key = f"PHT_{sensor_index}"
    state = 1

    # 每个传感器的独立判定参数（可根据需要调整）
    # extreme\_low/high：极端值视为传感器故障的保护范围
    # min/max：上下限超界的报警范围（优先使用配置中的 min\_pht/max\_pht）
    rules = {
        1: {  # 温度
            "extreme_low": -100.0, "extreme_high": 200.0,
            "default_min": 0.0, "default_max": 60.0,
        },
        2: {  # 湿度
            "extreme_low": -10.0, "extreme_high": 100.0,
            "default_min": 0.0, "default_max": 80.0,
        },
        3: {  # 露点
            "extreme_low": -50.0, "extreme_high": 80.0,
            "default_min": -20.0, "default_max": 50.0,
        },
    }
    r = rules.get(sensor_index, {
        "extreme_low": -100.0, "extreme_high": 200.0,
        "default_min": float(sensor_cfg.get("min_pht", -273)),
        "default_max": float(sensor_cfg.get("max_pht", 999)),
    })

    extreme_low = float(r["extreme_low"])
    extreme_high = float(r["extreme_high"])
    min_v = float(sensor_cfg.get("min_pht", r["default_min"]))
    max_v = float(sensor_cfg.get("max_pht", r["default_max"]))

    # 先做极端值的传感器故障保护（延时8秒确认）
    if calc_val > (extreme_high * 10**decimals) or calc_val < (extreme_low * 10**decimals):
        if _fault_time["sensor"].get(key, 0) == 0:
            _fault_time["sensor"][key] = now
        elif now - _fault_time["sensor"][key] >= 8:
            state = 0
    else:
        # 各自的上下限报警（延时8秒确认），正常清零故障计时
        if calc_val < min_v:
            if _fault_time["sensor"].get(key, 0) == 0:
                _fault_time["sensor"][key] = now
            elif now - _fault_time["sensor"][key] >= 8:
                state = 2
        elif calc_val > (max_v * 10**decimals):
            if _fault_time["sensor"].get(key, 0) == 0:
                _fault_time["sensor"][key] = now
            elif now - _fault_time["sensor"][key] >= 8:
                state = 3
        else:
            state = 1
            _fault_time["sensor"][key] = 0

    u16_calc_val_int = to_u16(calc_val_int)
    processed_reg_map.set_register(ENVIRONMENT_VALUE_START + sensor_index, u16_calc_val_int)
    processed_reg_map.set_register(ENVIRONMENT_STATUS_START + sensor_index, state)

    # print(f"Environment Sensor {sensor_index}: Raw={raw_val}, Calc={calc_val:.2f}, State={state}")

    return {
        "value": u16_calc_val_int,
        "state": state,
    }

# 温差计算
def get_temperature_diff(reg_map=None):
    """
    计算温差（T4-T1），结果*1000，负数转U16，写入 TEMP_DIFF_START
    从 processed_reg_map 读取处理后的温度值
    """
    reg = reg_map or processed_reg_map
    t1 = reg.get_register(TEMP_VALUE_START + 0) or 0
    t4 = reg.get_register(TEMP_VALUE_START + 3) or 0
    t1 = t1 / 1000.0
    t4 = t4 / 1000.0
    diff_val = int(round((t4 - t1) * 1000))
    u16_diff_val = to_u16(diff_val)
    reg.set_register(TEMP_DIFF_START + 0, u16_diff_val)
    # print(f"[ControlLogic] INFO: T1={t1:.3f}, T4={t4:.3f}, 温差寄存器[{TEMP_DIFF_START}]={reg.get_register(TEMP_DIFF_START + 0)}")
    return u16_diff_val

# 压差计算
def get_pressure_diff(reg_map=None):
    """
    计算压差（P4-P3），结果*1000，负数转U16，写入 PRESS_DIFF_START
    从 processed_reg_map 读取处理后的压力值
    """
    reg = reg_map or processed_reg_map
    p3 = reg.get_register(PRESS_VALUE_START + 2) or 0
    p4 = reg.get_register(PRESS_VALUE_START + 3) or 0
    p3 = p3 / 1000.0
    p4 = p4 / 1000.0
    diff_val = int(round((p4 - p3) * 1000))
    u16_diff_val = to_u16(diff_val)
    reg.set_register(PRESS_DIFF_START + 0, u16_diff_val)
    # print(f"[ControlLogic] INFO: P3={p3:.3f}, P4={p4:.3f}, 压差寄存器[{PRESS_DIFF_START}]={reg.get_register(PRESS_DIFF_START + 0)}")
    return u16_diff_val

# 制冷量计算
def get_cooling_capacity(reg_map=None):
    """
    制冷量计算逻辑:
    公式: cap_val = F2 * (T3 - T4) * density * specific_heat_capacity / 60
      - F2: 处理后流量寄存器 FLOW_VALUE_START + 1（需除以 10**F2小数位 得到物理量）
      - T3: TEMP_VALUE_START + 2（存储为 *1000 的整数，需 /1000 还原）
      - T4: TEMP_VALUE_START + 3（同上）
    常量:
      density = 1.0163
      specific_heat_capacity = 4.182
    写入:
      - 物理量 cap_val *1000 四舍五入为整数 scaled
      - 若 scaled 为负数，转换为 U16 两补码
      - 若 scaled 为正但非常小导致 round 后为 0，直接写 0（正常量化，不强行置 1）
    寄存器:
      COOLING_CAPACITY_START + 0
    日志:
      打印 F2, T3, T4, ΔT, cap_val 以及最终写入的整数值
    """

    density = 1.0163 # kg/L 水
    specific_heat_capacity = 4.182 # kJ/(kg·°C) 水

    reg = reg_map or processed_reg_map

    # # 获取 F2 小数位
    # f2_decimals = 2
    # for item in CONFIG_CACHE.get("sensor", []):
    #     cfg = item.get("config", {})
    #     if str(cfg.get("name", "")).upper() == "F2":
    #         f2_decimals = int(cfg.get("r_d_flow_decimals", 2))
    #         break

    # 读取处理后寄存器的流量与温度
    f2_raw_scaled = reg.get_register(FLOW_VALUE_START + 1)

    # 将 U16 转换为有符号整数
    if f2_raw_scaled >= 0x8000:  # 判断是否为负数
        f2_raw_scaled -= 0x10000

    f2_val = f2_raw_scaled / 10.0  # F2 小数位为 1

    t3_int = reg.get_register(TEMP_VALUE_START + 2)
    t4_int = reg.get_register(TEMP_VALUE_START + 3)
    t3 = t3_int / 10.0
    t4 = t4_int / 10.0

    delta_t = t3 - t4

    # ΔT 为 0 直接屏蔽本次输出
    if abs(delta_t) < 1e-12:
        return reg.get_register(COOLING_CAPACITY_START + 0)

    cap_val = f2_val * delta_t * density * specific_heat_capacity / 60.0  # kW 假设单位
    scaled = int(round(cap_val * 1000))

    # 强制非 0（只在 ΔT != 0 且四舍五入后为 0 时）
    if scaled == 0:
        scaled = 1 if cap_val > 0 else -1

    # 输出制冷量范围限制（暂时注释）
    # if scaled < 0:
    #     scaled = 0

    # print(f"[ControlLogic] INFO: calc: F2={f2_val:.3f} L/min, T3={t3:.3f} °C, T4={t4:.3f} °C, ΔT={delta_t:.3f} °C, cap_val={cap_val:.3f} kW")

    # 物理量缩放 *1000 并四舍五入
    scaled = int(round(cap_val * 10))

    u16_scaled = to_u16(scaled)
    processed_reg_map.set_register(COOLING_CAPACITY_START + 0, u16_scaled)

    return u16_scaled

# Input状态处理
def process_io_input_state(
        input_cfg: dict,
        coils: dict,
        input_index: int,
        now=None):
    """
    Input状态处理（只读）
    - 开关读取：线圈 COIL_IO_INPUT_READ_START + idx
    说明：
    - 读源数据从原始线圈地址（配置）获取；
    - 处理后写入到新处理映射 processed_reg_map 的IO输入读取区域；
    """
    if now is None:
        now = time.time()

    # 读取原始Input状态（从配置中的地址）
    status_addr = input_cfg.get("r_b_input_address", {}).get("local")
    status_val = coils.get(status_addr, 0) if status_addr is not None else 0

    # 写入到处理后寄存器映射的读取区域
    read_coil_addr = COIL_IO_INPUT_READ_START + input_index
    processed_reg_map.set_coil(read_coil_addr, status_val)

    # 调试信息
    # print(f"[ControlLogic] DEBUG: process_input_state - index={input_index}, raw_addr={status_addr}, value={status_val}, read_addr={read_coil_addr}")

    return {
        "status": status_val,
        "coil_address": read_coil_addr,
        "raw_address": status_addr,
        "index": input_index,
    }

# IO Output状态处理
def process_io_output_state(
        iooutput_cfg: dict,
        coils: dict,
        iooutput_index: int,
        now=None):
    """
    IO Output状态处理
    - 开关读取：线圈 COIL_IO_OUTPUT_READ_START + idx
    说明：
    - 读源数据从原始线圈地址（配置）获取；
    - 处理后写入到新处理映射 processed_reg_map 的新分段地址；
    """
    if now is None:
        now = time.time()

    # 读取原始IO Output状态（从配置中的地址）
    status_addr = iooutput_cfg.get("rw_b_output_address", {}).get("local")
    status_val = coils.get(status_addr, 0) if status_addr is not None else 0

    # 写入到处理后寄存器映射的读取区域
    read_coil_addr = COIL_IO_OUTPUT_READ_START + iooutput_index
    processed_reg_map.set_coil(read_coil_addr, status_val)

    # print(f"[ControlLogic] DEBUG: process_io_output_state - index={iooutput_index}, raw_addr={status_addr}, value={status_val}, read_addr={read_coil_addr}")

    return {
        "status": status_val,
        "coil_address": read_coil_addr,
        "raw_address": status_addr,
        "index": iooutput_index,
    }

# 风扇寄存器值获取
def get_all_fan_states(reg_map) -> list:
    fans = CONFIG_CACHE.get("fans", [])
    now = time.time()
    return [
        process_fan_state(fan["config"], reg_map.registers, reg_map.coils, i, now)
        for i, fan in enumerate(fans)
    ]

# 水泵寄存器值获取
def get_all_pump_states(reg_map) -> list:
    pumps = CONFIG_CACHE.get("pumps", [])
    now = time.time()
    return [
        process_pump_state(pump["config"], reg_map.registers, reg_map.coils, i, now)
        for i, pump in enumerate(pumps)
    ]

# 比例阀寄存器值获取
def get_all_proportional_valve_states(reg_map) -> list:
    pvs = CONFIG_CACHE.get("proportional_valve", [])
    now = time.time()
    return [
        process_proportional_valve_state(pv["config"], reg_map.registers, i, now)
        for i, pv in enumerate(pvs)
    ]

# 传感器寄存器值获取(温度、压力、流量、PH， 温湿度传感器)
def get_all_sensor_states(reg_map) -> list:
    sensors = CONFIG_CACHE.get("sensor", [])
    now = time.time()
    results = []
    temp_idx = 0
    press_idx = 0
    flow_idx = 0
    ph_idx = 0
    pht_idx = 0

    for item in sensors:
        cfg = item.get("config", {})
        if "r_d_temperature_address" in cfg:
            results.append(process_temperature_state(cfg, reg_map.registers, temp_idx, now))
            temp_idx += 1
        elif "r_d_pressure_address" in cfg:
            results.append(process_pressure_state(cfg, reg_map.registers, press_idx, now))
            press_idx += 1
        elif "r_d_flow_address" in cfg:
            results.append(process_flow_state(cfg, reg_map.registers, flow_idx, now))
            flow_idx += 1
        elif "r_d_ph_address" in cfg:
            results.append(process_ph_state(cfg, reg_map.registers, ph_idx, now))
            ph_idx += 1
        elif "r_d_pht_address" in cfg:
            results.append(process_environment_state(cfg, reg_map.registers, pht_idx, now))
            pht_idx += 1
        else:
            # 未知类型，跳过
            continue

    return results

# IO Input线圈值获取
def get_all_io_input_states(reg_map) -> list:
    """
    获取所有Input的状态（只读）
    """
    inputs = CONFIG_CACHE.get("input", [])
    now = time.time()
    return [
        process_io_input_state(input_cfg["config"], reg_map.coils, i, now)
        for i, input_cfg in enumerate(inputs)
    ]

# IO Output线圈值获取
def get_all_io_output_states(reg_map) -> list:
    """
    获取所有IO Output的状态
    """
    iooutputs = CONFIG_CACHE.get("output", [])
    now = time.time()
    return [
        process_io_output_state(iooutput["config"], reg_map.coils, i, now)
        for i, iooutput in enumerate(iooutputs)
    ]

# 第一次同步时，将写入寄存器的值也同步，避免程序启动后写入寄存器的值和实际值不匹配
def _sync_read_to_write_registers_once():
    """
    第一次同步时，将读取寄存器的值同步到对应的写入寄存器
    只执行一次，用于解决程序启动时显示状态不一致的问题
    """
    global _first_sync_flag

    with _first_sync_lock:
        if _first_sync_flag:
            return  # 已经执行过第一次同步，直接返回
        _first_sync_flag = True

    # print("[ControlLogic] INFO: First sync - copying read registers to write registers")

    try:
        # 同步水泵占空比：读取寄存器600-631 -> 写入寄存器632-663
        pump_count = len(CONFIG_CACHE.get("pumps", []))
        for i in range(pump_count):
            read_addr = PUMP_DUTY_READ_START + i
            write_addr = PUMP_DUTY_WRITE_START + i
            read_value = processed_reg_map.get_register(read_addr)
            # 将读取寄存器的值同步到写入寄存器
            processed_reg_map.set_register(write_addr, read_value, trigger_callback=False)
            # print(f"[ControlLogic] DEBUG: Sync pump duty - pump_index={i}, read_addr={read_addr}(value={read_value}) -> write_addr={write_addr}")

        # 同步比例阀占空比：读取寄存器800-807 -> 写入寄存器808-815
        pv_count = len(CONFIG_CACHE.get("proportional_valve", []))
        for i in range(pv_count):
            read_addr = PV_DUTY_READ_START + i
            write_addr = PV_DUTY_WRITE_START + i
            read_value = processed_reg_map.get_register(read_addr)
            processed_reg_map.set_register(write_addr, read_value, trigger_callback=False)
            # print(f"[ControlLogic] DEBUG: Sync PV duty - pv_index={i}, read_addr={read_addr}(value={read_value}) -> write_addr={write_addr}")

        # 同步风扇占空比：读取寄存器400-431 -> 写入寄存器432-463
        fan_count = len(CONFIG_CACHE.get("fans", []))
        for i in range(fan_count):
            read_addr = FAN_DUTY_READ_START + i
            write_addr = FAN_DUTY_WRITE_START + i
            read_value = processed_reg_map.get_register(read_addr)
            processed_reg_map.set_register(write_addr, read_value, trigger_callback=False)
            # print(f"[ControlLogic] DEBUG: Sync fan duty - fan_index={i}, read_addr={read_addr}(value={read_value}) -> write_addr={write_addr}")

        # 同步风扇开关：读取线圈1-31 -> 写入线圈33-63
        for i in range(fan_count):
            read_addr = COIL_FAN_SWITCH_READ_START + i
            write_addr = COIL_FAN_SWITCH_WRITE_START + i
            read_value = processed_reg_map.get_coil(read_addr)
            processed_reg_map.set_coil(write_addr, read_value, trigger_callback=False)
            # print(f"[ControlLogic] DEBUG: Sync fan switch - fan_index={i}, read_addr={read_addr}(value={read_value}) -> write_addr={write_addr}")

        # 同步水泵开关：读取线圈65-95 -> 写入线圈97-127
        for i in range(pump_count):
            read_addr = COIL_PUMP_SWITCH_READ_START + i
            write_addr = COIL_PUMP_SWITCH_WRITE_START + i
            read_value = processed_reg_map.get_coil(read_addr)
            processed_reg_map.set_coil(write_addr, read_value, trigger_callback=False)
            # print(f"[ControlLogic] DEBUG: Sync pump switch - pump_index={i}, read_addr={read_addr}(value={read_value}) -> write_addr={write_addr}")

        # 同步IO output：读取线圈233-265 -> 写入线圈266-297
        iooutput_count = len(CONFIG_CACHE.get("output", []))
        for i in range(iooutput_count):
            read_addr = COIL_IO_OUTPUT_READ_START + i
            write_addr = COIL_IO_OUTPUT_WRITE_START + i
            read_value = processed_reg_map.get_coil(read_addr)
            processed_reg_map.set_coil(write_addr, read_value, trigger_callback=False)
            # print(f"[ControlLogic] DEBUG: Sync fan switch - iooutput_index={i}, read_addr={read_addr}(value={read_value}) -> write_addr={write_addr}")

        # print("[ControlLogic] INFO: First sync completed - all read to write registers synchronized")

    except Exception as e:
        print(f"[ControlLogic] ERROR: First sync failed: {e}")

# 处理后寄存器同步线程启动标志与锁
def start_processed_register_sync(get_register_map_func, interval=0.15):
    """
    启动处理后寄存器同步线程，防止多次启动
    """
    global _sync_thread_started

    with _sync_thread_lock:
        if _sync_thread_started:
            print("[ControlLogic] WARNING: processed_register_sync thread started skip duplicate starts")
            return
        _sync_thread_started = True

    def sync_loop():
        # 第一次同步标志，确保只执行一次
        first_run = True
        data_ready_check_count = 0

        while True:
            reg_map = get_register_map_func()
            get_all_fan_states(reg_map)
            get_all_pump_states(reg_map)
            get_all_proportional_valve_states(reg_map)
            get_all_sensor_states(reg_map)
            get_all_io_output_states(reg_map)
            get_all_io_input_states(reg_map)
            get_pressure_diff(processed_reg_map)
            get_temperature_diff(processed_reg_map)
            get_cooling_capacity(processed_reg_map)

            # 第一次循环时执行读取寄存器到写入寄存器的同步，并且检查数据有效性
            if first_run:
                data_ready_check_count += 1

                # 检查是否有实际设备数据（非0值）
                has_actual_data = False
                # 简单检查几个关键设备
                if processed_reg_map.get_register(PUMP_DUTY_READ_START) != 0:
                    has_actual_data = True
                elif processed_reg_map.get_register(FAN_DUTY_READ_START) != 0:
                    has_actual_data = True
                elif processed_reg_map.get_register(PV_DUTY_READ_START) != 0:
                    has_actual_data = True

                if has_actual_data or data_ready_check_count >= 10:
                    _sync_read_to_write_registers_once()
                    first_run = False

            time.sleep(interval)
    t = threading.Thread(target=sync_loop, daemon=True)
    t.start()

# 写入使能寄存器绑定业务逻辑
def apply_write_enable_effect(enable: int):
    """
    纯业务逻辑函数：根据写使能变化执行设备动作
    - 如果写入使能写0，不管什么模式，都立即关停水泵和比例阀，风扇延迟关闭，同时立即停止自动控制线程
    - 如果写入使能写1，设置比例阀占空比为10000（100%）
    - 如果切换到手动模式，只停止自动控制线程，保持当前设备状态
    """
    global _fan_shutdown_timer

    # 保存上一次的状态，防止重复执行
    prev = getattr(apply_write_enable_effect, "last", None)
    if prev == enable:
        print(f"[ControlLogic] INFO: Write enable unchanged: {enable}")
        return

    fans = CONFIG_CACHE.get("fans", [])
    pumps = CONFIG_CACHE.get("pumps", [])
    pvs = CONFIG_CACHE.get("proportional_valve", [])

    # 获取当前控制模式
    control_mode = processed_reg_map.get_register(CONTROL_MODE)

    # 记录是否存在待执行关停定时器
    had_pending_timer = False
    replaced_timer = False

    if enable == 1:
        # 取消延迟关停
        with _fan_shutdown_timer_lock:
            if _fan_shutdown_timer is not None:
                had_pending_timer = True
                try:
                    _fan_shutdown_timer.cancel()
                finally:
                    _fan_shutdown_timer = None

        # 启动全部风扇（force=True 跳过写使能判定）
        for i in range(len(fans)):
            write_fan_switch(i, 1, force=True)

        # 设置比例阀占空比为10000（100%）
        for i in range(len(pvs)):
            batch_write_pv_duty(10000, force=True)

        # print(f"[ControlLogic] INFO: Write enable=1 - starting all fans, setting PV duty to 10000, control_mode={control_mode}")

    else:
        # 写入使能为0：立即停止水泵与比例阀（占空比置 0），风扇延迟关闭
        print(f"[ControlLogic] INFO: Write enable=0 - immediate stop pumps & PVs, schedule fan delayed stop, control_mode={control_mode}")

        # 立即停止自动控制线程
        from cdu120kw.control_logic.auto_control import auto_control_manager
        auto_control_manager.stop_auto_control()

        # 停止水泵和比例阀
        for i in range(len(pumps)):
            write_pump_duty(i, 0, force=True)

        # for i in range(len(pvs)):
        #     write_pv_duty(i, 0, force=True)

        # 创建/替换风扇延迟关停定时器
        def delayed_shutdown():
            print("[ControlLogic] INFO: Delayed fan shutdown triggered")
            for idx in range(len(fans)):
                write_fan_switch(idx, 0, force=True)

        with _fan_shutdown_timer_lock:
            if _fan_shutdown_timer is not None:
                try:
                    _fan_shutdown_timer.cancel()
                finally:
                    replaced_timer = True
            _fan_shutdown_timer = threading.Timer(15.0, delayed_shutdown)
            _fan_shutdown_timer.start()

    apply_write_enable_effect.last = enable

# 风扇开关写入函数
def write_fan_switch(fan_index: int, switch_on: int, slave: int = 1, priority: int = 0, force: bool = False):
    """
    写入风扇开关（线圈）到本地寄存器表，并同步写入到PCBA实际寄存器
    1. 先判断写入使能寄存器（COIL_WRITE_ENABLE）是否为1，若为0则禁止写入
    2. 写入本地寄存器表（COIL_FAN_SWITCH_WRITE_START + fan_index）
    3. 查找风扇配置，获取可写线圈字段
    4. 调用ComponentOperationTaskManager写入PCBA
    """

    from cdu120kw.service_function.controller_app import app_controller
    component_task_mgr = app_controller.component_task_manager

    # 步骤1：判断写入使能，延迟关停风扇时允许强制写入
    if not force and processed_reg_map.get_coil(COIL_WRITE_ENABLE) != 1:
        print("[ControlLogic] WARNING: Fan switch write denied: write enable=0")
        return False

    # # 步骤2：写入本地寄存器
    # coil_addr = COIL_FAN_SWITCH_WRITE_START + fan_index
    # processed_reg_map.set_coil(coil_addr, switch_on)
    # print(f"[ControlLogic] INFO: Local fan switch written: addr={coil_addr}, value={switch_on}")

    # 步骤3：查找风扇配置
    fan_list = CONFIG_CACHE.get("fans", [])
    if fan_index >= len(fan_list):
        print(f"[ControlLogic] WARNING: Fan index {fan_index} out of range")
        return False
    fan_name = fan_list[fan_index]["name"]

    param = component_task_mgr.param_mgr.get_param(fan_name)
    if not param:
        print(f"[ControlLogic] WARNING: Fan config not found: {fan_name}")
        return False

    field = None
    for k, v in param.writable_fields.items():
        if v[0] == "coil":
            field = k
            break
    if not field:
        print(f"[ControlLogic] WARNING: No writable coil field for fan: {fan_name}")
        return False

    # 步骤4：写入PCBA
    result = component_task_mgr.operate_component(
        name=fan_name,
        value_dict={field: int(switch_on)},
        slave=slave,
        priority=priority
    )
    # print(f"[ControlLogic] INFO: Fan switch submit (force={force}): {fan_name}={switch_on}, result={result}")
    return result

# 水泵占空比写入函数
def write_pump_duty(pump_index: int, duty: int, slave: int = 1, priority: int = 0, force: bool = False):
    """
    写入水泵占空比到本地寄存器表，并同步写入到PCBA实际寄存器
    1. 判断写入使能
    2. 写入本地寄存器（PUMP_DUTY_WRITE_START + pump_index）
    3. 查找水泵配置，获取可写保持寄存器字段
    4. 调用ComponentOperationTaskManager写入PCBA
    """
    from cdu120kw.service_function.controller_app import app_controller
    component_task_mgr = app_controller.component_task_manager

    # 步骤1：判断写入使能， 延迟关停水泵时允许强制写入
    if not force and processed_reg_map.get_coil(COIL_WRITE_ENABLE) != 1:
        print("[ControlLogic] WARNING: Pump duty write denied: write enable=0")
        return False

    # # 步骤2：写入本地寄存器
    # reg_addr = PUMP_DUTY_WRITE_START + pump_index
    # processed_reg_map.set_register(reg_addr, duty)
    # print(f"[ControlLogic] INFO: Local pump duty written: addr={reg_addr}, value={duty}")

    # 步骤3：查找水泵配置
    pump_list = CONFIG_CACHE.get("pumps", [])
    if pump_index >= len(pump_list):
        print(f"[ControlLogic] WARNING: Pump index {pump_index} out of range")
        return False
    pump_name = pump_list[pump_index]["name"]

    param = component_task_mgr.param_mgr.get_param(pump_name)
    if not param:
        print(f"[ControlLogic] WARNING: Pump config not found: {pump_name}")
        return False

    # 找到可写保持寄存器字段
    field = None
    for k, v in param.writable_fields.items():
        if v[0] == "register":
            field = k
            break
    if not field:
        print(f"[ControlLogic] WARNING: No writable register field for pump: {pump_name}")
        return False

    # 步骤4：写入PCBA
    result = component_task_mgr.operate_component(
        name=pump_name,
        value_dict={field: int(duty / 100)},
        slave=slave,
        priority=priority
    )
    # print(f"Pump duty submit (force={force}): {pump_name}={duty}, result={result}")
    return result

# 比例阀占空比写入函数
def write_pv_duty(pv_index: int, duty: int, slave: int = 1, priority: int = 0, force: bool = False):
    """
    写入比例阀占空比到本地寄存器表，并同步写入到PCBA实际寄存器
    1. 判断写入使能
    2. 写入本地寄存器（PV_DUTY_WRITE_START + pv_index）
    3. 查找比例阀配置，获取可写保持寄存器字段
    4. 调用ComponentOperationTaskManager写入PCBA
    """

    from cdu120kw.service_function.controller_app import app_controller
    component_task_mgr = app_controller.component_task_manager

    # 步骤1：判断写入使能， 延迟关停比例阀时允许强制写入
    if not force and processed_reg_map.get_coil(COIL_WRITE_ENABLE) != 1:
        print("[ControlLogic] WARNING: PV duty write denied: write enable=0")
        return False

    # # 步骤2：写入本地寄存器
    # reg_addr = PV_DUTY_WRITE_START + pv_index
    # processed_reg_map.set_register(reg_addr, duty)
    # print(f"Local proportional valve duty written: addr={reg_addr}, value={duty}")

    # 步骤3：查找比例阀配置
    pv_list = CONFIG_CACHE.get("proportional_valve", [])
    if pv_index >= len(pv_list):
        print(f"[ControlLogic] WARNING: PV index {pv_index} out of range")
        return False
    pv_name = pv_list[pv_index]["name"]

    param = component_task_mgr.param_mgr.get_param(pv_name)
    if not param:
        print(f"[ControlLogic] WARNING: PV config not found: {pv_name}")
        return False

    field = None
    for k, v in param.writable_fields.items():
        if v[0] == "register":
            field = k
            break
    if not field:
        print(f"[ControlLogic] WARNING: No writable register field for PV: {pv_name}")
        return False

    # 步骤4：写入PCBA
    result = component_task_mgr.operate_component(
        name=pv_name,
        value_dict={field: int(duty)},
        slave=slave,
        priority=priority
    )
    # print(f"[ControlLogic] INFO: PV duty submit (force={force}): {pv_name}={duty}, result={result}")
    return result

# IO Output输出线圈写入函数
def write_io_output(iooutput_index: int, switch_on: int, slave: int = 1, priority: int = 0, force: bool = False):
    """
    写入IO Output输出（线圈）到本地寄存器表，并同步写入到PCBA实际寄存器
    1. 先判断写入使能寄存器（COIL_WRITE_ENABLE）是否为1，若为0则禁止写入
    2. 写入本地寄存器表（COIL_IO_OUTPUT_WRITE_START + iooutput_index）
    3. 查找iooutput配置，获取可写线圈字段
    4. 调用ComponentOperationTaskManager写入PCBA
    """

    from cdu120kw.service_function.controller_app import app_controller
    component_task_mgr = app_controller.component_task_manager

    # 步骤1：判断写入使能，延迟关停风扇时允许强制写入
    if not force and processed_reg_map.get_coil(COIL_WRITE_ENABLE) != 1:
        print("[ControlLogic] WARNING: IO Output write denied: write enable=0")
        return False

    # # 步骤2：写入本地寄存器
    # coil_addr = COIL_IO_OUTPUT_WRITE_START + iooutput_index
    # processed_reg_map.set_coil(coil_addr, switch_on)
    # print(f"[ControlLogic] INFO: Local IO Output written: addr={coil_addr}, value={switch_on}")

    # 步骤3：查找IO Output配置
    iooutput_list = CONFIG_CACHE.get("output", [])
    if iooutput_index >= len(iooutput_list):
        print(f"[ControlLogic] WARNING: IO Output index {iooutput_index} out of range")
        return False
    iooutput_name = iooutput_list[iooutput_index]["name"]

    param = component_task_mgr.param_mgr.get_param(iooutput_name)
    if not param:
        print(f"[ControlLogic] WARNING: IO Output config not found: {iooutput_name}")
        return False

    field = None
    for k, v in param.writable_fields.items():
        if v[0] == "coil":
            field = k
            break
    if not field:
        print(f"[ControlLogic] WARNING: No writable coil field for IO Output: {iooutput_name}")
        return False

    # 步骤4：写入PCBA
    result = component_task_mgr.operate_component(
        name=iooutput_name,
        value_dict={field: int(switch_on)},
        slave=slave,
        priority=priority
    )
    # print(f"[ControlLogic] INFO: IO Output submit (force={force}): {iooutput_name}={switch_on}, result={result}")
    return result

# 水泵批量占空比写入函数
def batch_write_pump_duty(duty: int, slave: int = 1, priority: int = 0, force: bool = False):
    """
    水泵批量占空比写入函数
    通过设置所有水泵的单个写入寄存器来触发回调，实现批量写入
    """
    # 重入保护
    if getattr(batch_write_pump_duty, '_executing', False):
        print("[ControlLogic] WARNING: Batch write reentrancy detected")
        return False

    batch_write_pump_duty._executing = True

    try:
        # 检查写入使能
        if not force and processed_reg_map.get_coil(COIL_WRITE_ENABLE) != 1:
            print("[ControlLogic] WARNING: Pump batch duty write denied: write enable=0")
            return False

        # 获取水泵列表
        pump_list = CONFIG_CACHE.get("pumps", [])
        if not pump_list:
            print("[ControlLogic] INFO: No pumps configured for batch duty write")
            return False

        # 批量设置所有水泵的写入寄存器
        # print(f"[ControlLogic] INFO: Starting batch duty write for {len(pump_list)} pumps, duty={duty}")

        for pump_index in range(len(pump_list)):
            write_addr = PUMP_DUTY_WRITE_START + pump_index
            processed_reg_map.set_register(write_addr, duty)

        # print(f"[ControlLogic] INFO: Batch duty write completed - {len(pump_list)} registers updated")
        return True

    finally:
        batch_write_pump_duty._executing = False

# 初始化重入保护标志
batch_write_pump_duty._executing = False

# 比例阀批量占空比写入函数
def batch_write_pv_duty(duty: int, slave: int = 1, priority: int = 0, force: bool = False):
    """
    比例阀批量占空比写入函数
    通过设置所有比例阀的单个写入寄存器来触发回调，实现批量写入
    """
    # 重入保护
    if getattr(batch_write_pv_duty, '_executing', False):
        print("[ControlLogic] WARNING: Batch write reentrancy detected")
        return False

    batch_write_pv_duty._executing = True

    try:
        # 检查写入使能
        if not force and processed_reg_map.get_coil(COIL_WRITE_ENABLE) != 1:
            print("[ControlLogic] WARNING: Pump batch duty write denied: write enable=0")
            return False

        # 获取比例阀列表
        pv_list = CONFIG_CACHE.get("proportional_valve", [])
        if not pv_list:
            print("[ControlLogic] INFO: No pv configured for batch duty write")
            return False

        # 批量设置所有比例阀的写入寄存器
        # print(f"[ControlLogic] INFO: Starting batch duty write for {len(pv_list)} pvs, duty={duty}")

        for pv_index in range(len(pv_list)):
            write_addr = PV_DUTY_WRITE_START + pv_index
            processed_reg_map.set_register(write_addr, duty)

        # print(f"[ControlLogic] INFO: Batch duty write completed - {len(pv_list)} registers updated")
        return True

    finally:
        batch_write_pv_duty._executing = False

# 比例阀初始化重入保护标志
batch_write_pv_duty._executing = False

# IO Output批量写入函数
def batch_write_io_outputs(output_dict: dict, slave: int = 1, priority: int = 0, force: bool = False):
    """
    IO Output批量写入函数
    通过设置多个IO Output的单个写入寄存器来触发回调，实现批量写入
    """
    # 重入保护
    if getattr(batch_write_io_outputs, '_executing', False):
        print("[ControlLogic] WARNING: IO Output batch write reentrancy detected")
        return False

    batch_write_io_outputs._executing = True

    try:
        # 检查写入使能
        if not force and processed_reg_map.get_coil(COIL_WRITE_ENABLE) != 1:
            print("[ControlLogic] WARNING: IO Output batch write denied: write enable=0")
            return False

        # 获取IO Output列表
        iooutput_list = CONFIG_CACHE.get("output", [])
        if not iooutput_list:
            print("[ControlLogic] INFO: No IO Outputs configured for batch write")
            return False

        # print(f"[ControlLogic] INFO: Starting batch write for {len(output_dict)} IO Outputs")

        for iooutput_index, switch_on in output_dict.items():
            if iooutput_index >= len(iooutput_list):
                print(f"[ControlLogic] WARNING: IO Output index {iooutput_index} out of range")
                continue

            write_addr = COIL_IO_OUTPUT_WRITE_START + iooutput_index
            processed_reg_map.set_coil(write_addr, 1 if switch_on else 0)

        # print(f"[ControlLogic] INFO: Batch write completed - {len(output_dict)} registers updated")
        return True

    finally:
        batch_write_io_outputs._executing = False

# IO Output初始化重入保护标志
batch_write_io_outputs._executing = False

# HMI写入触发回调函数
def hmi_write_trigger(address: int, value: int):
    """
    HMI写入触发回调函数
    处理所有HMI写入操作，包括新增的水泵批量控制
    """

    write_enable = processed_reg_map.get_coil(COIL_WRITE_ENABLE)

    # 写使能线圈
    if address == COIL_WRITE_ENABLE:
        apply_write_enable_effect(int(value))
        # print("[ControlLogic] WARNING: Write enable updated: %s", int(value))
        return

    # 写使能关闭时直接拒绝其他写入（批量控制也受此限制）
    if write_enable != 1:
        return

    # 获取当前控制模式
    control_mode = processed_reg_map.get_register(CONTROL_MODE)

    # 自动控制模式时拒绝手动控制水泵
    if control_mode in [2, 3, 4]:  # 2=流量温度模式, 3=流量模式, 4=压差温度模式
        # 检查调用栈，确定是否来自自动控制模块
        stack = inspect.stack()
        is_auto_control = any(
            'auto_control' in frame.filename.lower() or
            'AutoControlManager' in str(frame.frame.f_locals.get('self', ''))
            for frame in stack
        )

        # 如果不是自动控制系统发起的写入，则拒绝水泵控制
        if not is_auto_control:
            # 水泵占空比写入区
            if PUMP_DUTY_WRITE_START <= address < PUMP_DUTY_WRITE_END:
                # print(f"[ControlLogic] WARNING: Manual pump control rejected in auto mode {control_mode}")
                return

            # 水泵批量占空比写入寄存器
            if address == PUMP_BATCH_DUTY_REGISTER:
                # print(f"[ControlLogic] WARNING: Manual batch pump control rejected in auto mode {control_mode}")
                return

    # 风扇开关写入区
    if COIL_FAN_SWITCH_WRITE_START <= address < COIL_FAN_SWITCH_WRITE_END:
        fan_index = address - COIL_FAN_SWITCH_WRITE_START
        write_fan_switch(fan_index, value)
        # print("[ControlLogic] INFO: Fan switch: idx=%s addr=%s value=%s",
        #             fan_index, address, int(value))
        return

    # 水泵占空比写入区
    if PUMP_DUTY_WRITE_START <= address < PUMP_DUTY_WRITE_END:
        pump_index = address - PUMP_DUTY_WRITE_START
        write_pump_duty(pump_index, value)
        # print("[ControlLogic] INFO: Pump duty: idx=%s addr=%s duty=%s",
        #             pump_index, address, int(value))
        return

    # 比例阀占空比写入区
    if PV_DUTY_WRITE_START <= address < PV_DUTY_WRITE_END:
        pv_index = address - PV_DUTY_WRITE_START
        write_pv_duty(pv_index, value)
        # print("[ControlLogic] INFO: PV duty: idx=%s addr=%s duty=%s",
        #             pv_index, address, int(value))
        return

    # IO Output写入区
    if COIL_IO_OUTPUT_WRITE_START <= address < COIL_IO_OUTPUT_WRITE_END:
        iooutput_index = address - COIL_IO_OUTPUT_WRITE_START
        write_io_output(iooutput_index, value)
        # print("[ControlLogic] INFO: IO Output: idx=%s addr=%s value=%s",
        #             iooutput_index, address, int(value))
        return

    # 水泵批量占空比写入寄存器
    if address == PUMP_BATCH_DUTY_REGISTER:
        batch_write_pump_duty(value)
        # print("[ControlLogic] INFO: Pump batch duty triggered: addr=%s duty=%s", address, int(value))
        return

    # 比例阀批量占空比写入寄存器
    if address == PV_BATCH_DUTY_REGISTER:
        batch_write_pv_duty(value)
        # print("[ControlLogic] INFO: Pump batch duty triggered: addr=%s duty=%s", address, int(value))
        return

    if address == IO_OUTPUT_BATCH_SWITCH_COIL:
        iooutput_list = CONFIG_CACHE.get("output", [])
        output_dict = {}

        for i in range(len(iooutput_list)):
            output_dict[i] = 1 if value else 0

        batch_write_io_outputs(output_dict)
        # print(f"[ControlLogic] INFO: IO Output batch switch triggered: addr={address}, value={value}, {len(output_dict)} outputs")
        return

# 注册写入回调
processed_reg_map.write_coil_callback(hmi_write_trigger)
processed_reg_map.write_register_callback(hmi_write_trigger)
