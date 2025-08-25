from modbustcp_manager.modbustcp_manager import safe_modbus_call


# ------------------------------------
# **水泵数据读取**
# ------------------------------------
def get_pump_status(pump_id: int) -> str:
    """获取水泵开关状态 (支持1/2/3号泵)"""

    def _get_pump_status(client, inner_pump_id):
        try:
            # 参数校验
            if inner_pump_id not in (1, 2, 3):
                return "Error: InvalidPumpID"

            # 动态计算寄存器地址
            reg = 783 + inner_pump_id  # 1→784, 2→785, 3→786

            # 读取线圈状态
            read_result = client.read_coils(
                address=reg,
                count=1,
                slave=1
            )

            # 检查Modbus协议错误
            if read_result.isError():
                return "Error: ReadError"
            if not read_result.bits:
                return "Error: NoData"

            return "On" if read_result.bits[0] else "Off"

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_get_pump_status, pump_id)
    if modbus_result is None:
        return "ConnectionError"
    return modbus_result


def get_pump_speed(pump_id: int) -> float | str:
    """获取水泵转速"""

    def _get_pump_speed(client, inner_pump_id):
        try:
            if inner_pump_id not in (1, 2):
                return "Error: InvalidPumpID"

            reg = 2128 if inner_pump_id == 1 else 2160

            read_result = client.read_holding_registers(
                address=reg,
                count=1,
                slave=1
            )

            if read_result.isError():
                return "Error: ReadError"
            if not read_result.registers:
                return "Error: NoData"

            return read_result.registers[0]

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_get_pump_speed, pump_id)
    if modbus_result is None:
        return "ConnectionError"
    return modbus_result


def get_pump_current(pump_id: int) -> float | str:
    """获取水泵电流"""

    def _get_pump_current(client, inner_pump_id):
        try:
            if inner_pump_id not in (1, 2):
                return "Error: InvalidPumpID"

            reg = 2129 if inner_pump_id == 1 else 2161

            read_result = client.read_holding_registers(
                address=reg,
                count=1,
                slave=1
            )

            if read_result.isError():
                return "Error: ReadError"
            if not read_result.registers:
                return "Error: NoData"

            return read_result.registers[0] / 1000.0

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_get_pump_current, pump_id)
    if modbus_result is None:
        return "ConnectionError"
    return modbus_result


def get_pump_duty_cycle(pump_id: int) -> float | str:
    """获取水泵占空比"""

    def _get_pump_duty_cycle(client, inner_pump_id):
        try:
            if inner_pump_id not in (1, 2):
                return "Error: InvalidPumpID"

            reg = 2640 if inner_pump_id == 1 else 2672

            read_result = client.read_holding_registers(
                address=reg,
                count=1,
                slave=1
            )

            if read_result.isError():
                return "Error: ReadError"
            if not read_result.registers:
                return "Error: NoData"

            return read_result.registers[0] / 100.0

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_get_pump_duty_cycle, pump_id)
    if modbus_result is None:
        return "ConnectionError"
    return modbus_result


def get_pump_pwm_amplitude() -> float | str:
    """获取PWM振幅"""

    def _get_pump_pwm_amplitude(client):
        try:
            reg = 2190

            read_result = client.read_holding_registers(
                address=reg,
                count=1,
                slave=1
            )

            if read_result.isError():
                return "Error: ReadError"
            if not read_result.registers:
                return "Error: NoData"

            return read_result.registers[0] / 1000.0

        except Exception as e:
            return f"Error: {str(e)}"

    modbus_result = safe_modbus_call(_get_pump_pwm_amplitude)
    if modbus_result is None:
        return "ConnectionError"
    return modbus_result
