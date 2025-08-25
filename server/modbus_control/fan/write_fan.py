from modbustcp_manager.modbustcp_manager import safe_modbus_call


# ------------------------------------
# **风扇控制（修复变量名冲突）**
# ------------------------------------
def set_fan_status(fan_id, status) -> str | None:
    """设置风扇开关状态"""

    def _set_fan_status(client, inner_fan_id, inner_status):
        try:
            if inner_fan_id <= 7:
                reg = 41200 + (inner_fan_id - 1)
            elif 8 <= fan_id <= 15:
                reg = 41712 + (inner_fan_id - 8)
            else:
                return "Error: InvalidFanID"

            # 执行写入操作
            write_result = client.write_coil(reg, inner_status)

            # 检查写入结果
            if write_result.isError():
                return f"Error: {write_result}"
            return None

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_set_fan_status, fan_id, status)
    if modbus_result is None:
        return None
    return modbus_result


def set_duty_cycle(fan_id, duty_cycle) -> str | None:
    """设置风扇占空比"""

    def _set_duty_cycle(client, inner_fan_id, inner_duty_cycle):
        try:
            if inner_fan_id <= 7:
                reg = 2576 + (inner_fan_id - 1)
            elif 8 <= inner_fan_id <= 15:
                reg = 2608 + (inner_fan_id - 8)
            else:
                return "Error: InvalidFanID"

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

    modbus_result = safe_modbus_call(_set_duty_cycle, fan_id, duty_cycle)
    if modbus_result is None:
        return None
    return modbus_result


def set_fan_pwm_amplitude(fan_id, pwm_amplitude) -> str | None:
    """设置风扇PWM振幅"""

    def _set_fan_pwm_amplitude(client, inner_fan_id, inner_amplitude):
        try:
            if inner_fan_id <= 7:
                reg = 2574
            elif 8 <= inner_fan_id <= 15:
                reg = 2606
            else:
                return "Error: InvalidFanID"

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

    modbus_result = safe_modbus_call(_set_fan_pwm_amplitude, fan_id, pwm_amplitude)
    if modbus_result is None:
        return None
    return modbus_result
