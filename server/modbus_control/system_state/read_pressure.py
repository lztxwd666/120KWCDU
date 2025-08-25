from modbustcp_manager.modbustcp_manager import safe_modbus_call


# ------------------------------------
# **流量，压力数据读取及制冷量计算**
# ------------------------------------
def read_pressure(reg: int, pressure_name: str) -> float | str:
    """通用压力读取函数"""

    def _read_pressure(client, inner_reg, inner_pressure_name):
        try:
            rr = client.read_holding_registers(address=inner_reg, count=1, slave=1)

            # 检查 Modbus 错误
            if rr.isError():
                return f"Error: Modbus read failed ({inner_pressure_name})"
            if not rr.registers:
                return f"Error: No data received ({inner_pressure_name})"

            raw_value = rr.registers[0]
            return calculate_pressure(raw_value, inner_pressure_name)

        except Exception as e:
            return f"Error: {str(e)} ({inner_pressure_name})"

    return safe_modbus_call(_read_pressure, reg, pressure_name) or "ConnectionError"


def get_supply_pressure_p1() -> float | str:
    """读取 Supply Pressure P1（寄存器 3392）"""
    return read_pressure(reg=3392, pressure_name="P1")


def get_supply_pressure_p2() -> float | str:
    """读取 Supply Pressure P2（寄存器 3393）"""
    return read_pressure(reg=3393, pressure_name="P2")


def calculate_pressure(raw_value: int, pressure_name: str) -> float | str:
    """通用压力计算逻辑"""
    try:
        if not isinstance(raw_value, int):
            return f"Error: Invalid ADC value (non-integer) ({pressure_name})"

        # 转换为电流值（mA），并限制下限为4mA
        current_ma = raw_value / 1000.0
        clamped_ma = max(current_ma, 4.0)

        pressure_percent = 100.0 * (clamped_ma - 4.0) / 16.0

        return round(pressure_percent, 2)
    except Exception as e:
        return f"Error: {str(e)} ({pressure_name})"


def pressure_difference() -> float | str:
    """计算压差 P1-P2"""
    try:
        # 独立获取 P1 和 P2 的值
        p1 = get_supply_pressure_p1()
        p2 = get_supply_pressure_p2()

        # 检查是否存在错误（字符串类型表示错误）
        if isinstance(p1, str) or isinstance(p2, str):
            return f"Error: Dependent pressure read failed (P1: {p1}, P2: {p2})"

        # 确保数值类型
        if not (isinstance(p1, (int, float)) and isinstance(p2, (int, float))):
            return f"Error: Invalid data type (P1: {type(p1)}, P2: {type(p2)})"

        # 计算压差并保留两位小数
        return round(p1 - p2, 2)

    except Exception as e:
        return f"Error: {str(e)}"
