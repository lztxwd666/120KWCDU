"""
控制所有风扇的启停和转速
"""

from modbus_manager.batch_writer import ModbusBatchWriter
from modbus_manager.modbusrtu_manager import modbusrtu_manager
from modbus_manager.modbustcp_manager import modbustcp_manager


def set_all_fan_statuses(status_list: list[bool], mode: str = "tcp") -> str | None:
    """
    设置所有风扇的开关状态
    :param status_list: 16个风扇的开关状态
    :param mode: 工作模式，tcp 或 rtu
    :return: 错误信息或None
    """
    client_manager = modbustcp_manager if mode == "tcp" else modbusrtu_manager
    writer = ModbusBatchWriter(client_manager)
    err = writer.write_coils(41200, status_list[:8])
    if err:
        return err
    err = writer.write_coils(41712, status_list[8:])
    if err:
        return err
    return None


def set_all_fan_duty_cycles(duty_cycle_list: list[float], mode: str = "tcp") -> str | None:
    """
    设置所有风扇的占空比
    :param duty_cycle_list: 16个风扇的占空比
    :param mode: 工作模式，tcp 或 rtu
    :return: 错误信息或None
    """
    client_manager = modbustcp_manager if mode == "tcp" else modbusrtu_manager
    writer = ModbusBatchWriter(client_manager)
    values_8 = [int((dc if dc is not None else 0) * 100) for dc in duty_cycle_list[:8]]
    err = writer.write_registers(2576, values_8)
    if err:
        return err
    values_8 = [int((dc if dc is not None else 0) * 100) for dc in duty_cycle_list[8:]]
    err = writer.write_registers(2608, values_8)
    if err:
        return err
    return None
