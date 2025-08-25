from modbustcp_manager.modbustcp_manager import safe_modbus_call


def get_flow_rate() -> float | str:
    """读取流量"""

    def _get_flow_rate(client):
        reg = 3394
        try:
            # 使用关键字参数，并指定从站单元 ID
            rr = client.read_holding_registers(address=reg, count=1, slave=1)

            # 检查 Modbus 错误
            if rr.isError():
                return f"Error: Modbus read failed (Flow)"
            if not rr.registers:
                return "Error: No data received (Flow)"

            # 提取原始值并验证是否为整数
            raw_value = rr.registers[0]
            if not isinstance(raw_value, int):
                return "Error: Invalid ADC value (non-integer)"

            # 转换为电流值（mA）
            current_ma = raw_value / 1000.0  # 确保浮点运算

            # 下限限制（不低于4mA）
            clamped_ma = max(current_ma, 4.0)

            # 计算流量值（公式：5.313 × (I - 4)）
            flow_value = 5.313 * (clamped_ma - 4.0)

            # 可选：限制流量最大值（例如对应20mA时的理论值）
            flow_value = min(flow_value, 5.313 * 16)

            # 返回结果（保留两位小数）
            return round(flow_value, 2)

        except Exception as e:
            return f"Error: {str(e)} (Flow)"

    result = safe_modbus_call(_get_flow_rate)
    if result is None:
        return "ConnectionError"
    return result
