"""
读取所有水泵的状态、转速、占空比、电流和PWM幅值
"""
from modbus_manager.batch_reader import ModbusBatchReader
from modbus_manager.modbusrtu_manager import modbusrtu_manager
from modbus_manager.modbustcp_manager import modbustcp_manager


def get_all_pump_statuses(mode: str = "tcp") -> list[str]:
    """
    读取所有水泵的开关状态
    :param mode: 工作模式，tcp 或 rtu
    :return: 状态列表
    """
    # 根据模式选择对应的连接管理器
    client_manager = modbustcp_manager if mode == "tcp" else modbusrtu_manager
    reader = ModbusBatchReader(client_manager)
    statuses = []
    regs, err = reader.read_coils(784, 3)
    if err:
        statuses.extend([err] * 3)
    else:
        statuses.extend(["On" if bit else "Off" for bit in regs])
    return statuses


def get_all_pump_duty_cycles(mode: str = "tcp") -> list[float | str]:
    """
    读取所有水泵的占空比
    :param mode: 工作模式，tcp 或 rtu
    :return: 占空比列表
    """
    client_manager = modbustcp_manager if mode == "tcp" else modbusrtu_manager
    reader = ModbusBatchReader(client_manager)
    duty_cycles = []
    regs, err = reader.read_holding_registers(2192, 3)
    if err:
        duty_cycles.extend([err] * 3)
    else:
        duty_cycles.extend([round(reg / 100.0, 2) for reg in regs])
    return duty_cycles


def get_all_pump_speeds(mode: str = "tcp") -> list[float | str]:
    """
    读取所有水泵的转速
    :param mode: 工作模式，tcp 或 rtu
    :return: 转速列表
    """
    client_manager = modbustcp_manager if mode == "tcp" else modbusrtu_manager
    reader = ModbusBatchReader(client_manager)
    speeds = []
    regs, err = reader.read_holding_registers(2080, 6)
    if err:
        speeds.extend([err] * 3)
    else:
        speeds.extend([regs[i] for i in range(0, 6, 2)])
    return speeds


def get_all_pump_currents(mode: str = "tcp") -> list[float | str]:
    """
    读取所有水泵的电流
    :param mode: 工作模式，tcp 或 rtu
    :return: 电流列表
    """
    client_manager = modbustcp_manager if mode == "tcp" else modbusrtu_manager
    reader = ModbusBatchReader(client_manager)
    currents = []
    regs, err = reader.read_holding_registers(2081, 6)
    if err:
        currents.extend([err] * 3)
    else:
        currents.extend([round(regs[i] / 1000.0, 3) for i in range(0, 6, 2)])
    return currents
