from modbustcp_manager.modbustcp_manager import safe_modbus_call


# ------------------------------------
# **温度读取**
# ------------------------------------
def read_temperature(reg: int, temp_name: str) -> float | str:
    """通用温度读取函数"""

    def _read_temperature(client, inner_reg, inner_temp_name):
        try:
            response = client.read_holding_registers(address=inner_reg, count=1, slave=1)

            # 检查Modbus协议错误
            if response.isError():
                return f"Error: ReadError ({inner_temp_name})"
            if not response.registers or len(response.registers) == 0:
                return f"Error: NoData ({inner_temp_name})"

            return response.registers[0] / 10.0

        except Exception as e:
            return f"Error: {str(e)} ({inner_temp_name})"

    result = safe_modbus_call(_read_temperature, reg, temp_name)
    if result is None:
        return "ConnectionError"
    return result


# ------------------------------------
# **具体温度读取函数**
# ------------------------------------
def get_supply_temperature_t1() -> float | str:
    """读取 Supply Temperature T1"""
    return read_temperature(reg=3328, temp_name="T1")


def get_return_temperature_t2() -> float | str:
    """读取 Return Temperature T2"""
    return read_temperature(reg=3329, temp_name="T2")


def get_ambient_t3() -> float | str:
    """读取 Ambient Temperature T3"""
    return read_temperature(reg=3330, temp_name="T3")


def calculate_temperature_difference(func1, func2, diff_name: str) -> float | str:
    """通用温差计算函数"""
    try:
        temp1 = func1()
        temp2 = func2()

        # 检查是否有错误
        if isinstance(temp1, str) and "Error" in temp1:
            return f"{temp1} ({diff_name})"
        if isinstance(temp2, str) and "Error" in temp2:
            return f"{temp2} ({diff_name})"

        # 确保是数值类型
        if not (isinstance(temp1, (int, float)) and isinstance(temp2, (int, float))):
            return f"Error: InvalidData ({diff_name})"

        return round(temp1 - temp2, 1)

    except Exception as e:
        return f"Error: {str(e)} ({diff_name})"


def get_temperature_rise_t2_t1() -> float | str:
    """计算 Temperature Rise T2-T1"""
    return calculate_temperature_difference(
        func1=get_return_temperature_t2,
        func2=get_supply_temperature_t1,
        diff_name="T2-T1"
    )


def get_approach_temperature_t1_t3() -> float | str:
    """计算 Approach Temperature T1-T3"""
    return calculate_temperature_difference(
        func1=get_supply_temperature_t1,
        func2=get_ambient_t3,
        diff_name="T1-T3"
    )
