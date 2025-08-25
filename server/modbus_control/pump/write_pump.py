from modbustcp_manager.modbustcp_manager import safe_modbus_call


# ------------------------------------
# **水泵控制**
# ------------------------------------
def set_pump_status(pump_id: int, status: bool) -> str | None:
    """设置水泵开关状态"""

    def _set_pump_status(client, inner_pump_id, inner_status):
        try:
            if inner_pump_id not in (1, 2, 3):
                return "Error: InvalidPumpID"

            # 计算寄存器地址
            reg = 783 + inner_pump_id

            # 执行写入操作
            write_result = client.write_coil(reg, inner_status)

            # 检查写入结果
            if write_result.isError():
                return f"Error: {write_result}"
            return None

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_set_pump_status, pump_id, status)
    if modbus_result is None:
        return None
    return modbus_result


def set_pump_duty_cycle(pump_id, duty_cycle) -> str | None:
    """设置水泵占空比"""

    def _set_pump_duty_cycle(client, inner_pump_id, inner_duty_cycle):
        try:
            if inner_pump_id not in (1, 2):
                return "Error: InvalidPumpID"

            reg = 2640 if inner_pump_id == 1 else 2672

            # 将占空比转换为整数值（0-100）
            value = int(inner_duty_cycle * 100)

            # 执行写入操作
            write_result = client.write_register(reg, value)

            # 检查写入结果
            if write_result.isError():
                return f"Error: {write_result}"
            return None

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_set_pump_duty_cycle, pump_id, duty_cycle)
    if modbus_result is None:
        return None
    return modbus_result


def set_pump_pwm_amplitude(pwm_amplitude) -> str | None:
    """设置PWM振幅"""

    def _set_pump_pwm_amplitude(client, inner_amplitude):
        try:
            reg = 2190

            # 将PWM振幅转换为整数值
            value = int(inner_amplitude * 1000)

            # 执行写入操作
            write_result = client.write_register(reg, value)

            # 检查写入结果
            if write_result.isError():
                return f"Error: {write_result}"
            return None

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_set_pump_pwm_amplitude, pwm_amplitude)
    if modbus_result is None:
        return None
    return modbus_result
