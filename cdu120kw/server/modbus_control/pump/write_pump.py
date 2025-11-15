"""
控制所有水泵的启停和转速
"""
from modbus_manager.batch_writer import ModbusBatchWriter
from modbus_manager.modbusrtu_manager import modbusrtu_manager
from modbus_manager.modbustcp_manager import modbustcp_manager


def set_all_pump_statuses(status_list: list[bool], mode: str = "tcp") -> str | None:
    """
    设置所有水泵的开关状态
    :param status_list: 3个水泵的开关状态
    :param mode: 工作模式，tcp 或 rtu
    :return: 错误信息或None
    """
    client_manager = modbustcp_manager if mode == "tcp" else modbusrtu_manager
    writer = ModbusBatchWriter(client_manager)
    err = writer.write_coils(784, status_list[:3])
    if err:
        return err
    return None


def set_all_pump_duty_cycles(duty_cycle_list: list[float], mode: str = "tcp") -> str | None:
    """
    设置所有水泵的占空比
    :param duty_cycle_list: 3个水泵的占空比
    :param mode: 工作模式，tcp 或 rtu
    :return: 错误信息或None
    """
    client_manager = modbustcp_manager if mode == "tcp" else modbusrtu_manager
    writer = ModbusBatchWriter(client_manager)
    values_3 = [int((dc if dc is not None else 0) * 100) for dc in duty_cycle_list[:3]]
    err = writer.write_registers(2192, values_3)
    if err:
        return err
    return None
