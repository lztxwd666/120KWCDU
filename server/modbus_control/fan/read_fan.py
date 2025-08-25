from modbustcp_manager.modbustcp_manager import safe_modbus_call


# ------------------------------------
# **风扇数据读取**
# ------------------------------------
def get_fan_status(fan_id: int) -> str:
    """获取风扇开关状态"""

    def _get_fan_status(client, inner_fan_id):
        try:
            # 参数校验
            if inner_fan_id not in range(1, 16):
                return "Error: InvalidFan"

            # 计算寄存器地址
            if inner_fan_id <= 7:
                reg = 41200 + (inner_fan_id - 1)
            else:
                reg = 41712 + (inner_fan_id - 8)

            # 读取线圈状态（假设单元ID为1）
            read_result = client.read_coils(address=reg, count=1, slave=1)

            # 检查Modbus协议错误
            if read_result.isError():
                return "Error: ReadError"
            if not read_result.bits:
                return "Error: NoData"

            return "On" if read_result.bits[0] else "Off"

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_get_fan_status, fan_id)
    if modbus_result is None:
        return "ConnectionError"
    return modbus_result


def get_fan_speed(fan_id: int) -> float | str:
    """获取风扇转速（RPM）"""

    def _get_fan_speed(client, inner_fan_id):
        try:
            if inner_fan_id not in range(1, 16):
                return "Error: InvalidFan"

            if inner_fan_id <= 7:
                reg = 2064 + 2 * (inner_fan_id - 1)
            else:
                reg = 2096 + 2 * (inner_fan_id - 8)

            read_result = client.read_holding_registers(address=reg, count=1, slave=1)

            if read_result.isError():
                return "Error: ReadError"
            if not read_result.registers:
                return "Error: NoData"

            return read_result.registers[0]

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_get_fan_speed, fan_id)
    if modbus_result is None:
        return "ConnectionError"
    return modbus_result


def get_fan_current(fan_id: int) -> float | str:
    """获取风扇电流（A）"""

    def _get_fan_current(client, inner_fan_id):
        try:
            if inner_fan_id not in range(1, 16):
                return "Error: InvalidFan"

            if inner_fan_id <= 7:
                reg = 2065 + 2 * (inner_fan_id - 1)
            else:
                reg = 2097 + 2 * (inner_fan_id - 8)

            read_result = client.read_holding_registers(address=reg, count=1, slave=1)

            if read_result.isError():
                return "Error: ReadError"
            if not read_result.registers:
                return "Error: NoData"

            return read_result.registers[0] / 1000.0

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_get_fan_current, fan_id)
    if modbus_result is None:
        return "ConnectionError"
    return modbus_result


def get_fan_duty_cycle(fan_id: int) -> float | str:
    """获取风扇占空比（%）"""

    def _get_fan_duty_cycle(client, inner_fan_id):
        try:
            if inner_fan_id not in range(1, 16):
                return "Error: InvalidFan"

            if inner_fan_id <= 7:
                reg = 2576 + (inner_fan_id - 1)
            else:
                reg = 2608 + (inner_fan_id - 8)

            read_result = client.read_holding_registers(address=reg, count=1, slave=1)

            if read_result.isError():
                return "Error: ReadError"
            if not read_result.registers:
                return "Error: NoData"

            return round(read_result.registers[0] / 100.0, 2)

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_get_fan_duty_cycle, fan_id)
    if modbus_result is None:
        return "ConnectionError"
    return modbus_result


def get_fan_pwm_amplitude(fan_id: int) -> float | str:
    """获取PWM幅值（V）"""

    def _get_fan_pwm_amplitude(client, inner_fan_id):
        try:
            if inner_fan_id not in range(1, 16):
                return "Error: InvalidFan"

            # 根据风扇组选择基地址
            base_reg = 2574 if inner_fan_id <= 7 else 2606

            read_result = client.read_holding_registers(address=base_reg, count=1, slave=1)

            if read_result.isError():
                return "Error: ReadError"
            if not read_result.registers:
                return "Error: NoData"

            return round(read_result.registers[0] / 1000.0, 3)

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_get_fan_pwm_amplitude, fan_id)
    if modbus_result is None:
        return "ConnectionError"
    return modbus_result
