from cache_manager.cache_manager import global_cache as cache
from server.modbus_control.system_state.read_flow import get_flow_rate
from server.modbus_control.system_state.read_temperature import get_temperature_rise_t2_t1

# 制冷量缓存时间
REFRIGERATION_CAPACITY_TTL = 5


@cache.cached(ttl=REFRIGERATION_CAPACITY_TTL)
def refrigeration_capacity() -> float | str:
    """计算制冷量"""
    try:
        # 获取流量值
        flow_result = get_flow_rate()
        if isinstance(flow_result, str):
            return f"Error: Flow rate read failed - {flow_result}"
        if not isinstance(flow_result, (int, float)):
            return "Error: Invalid flow rate (non-numeric)"

        # 获取温差值（T2-T1）
        temp_diff_result = get_temperature_rise_t2_t1()
        if isinstance(temp_diff_result, str):
            return f"Error: Temperature difference read failed - {temp_diff_result}"
        if not isinstance(temp_diff_result, (int, float)):
            return "Error: Invalid temperature difference (non-numeric)"

        # 计算制冷量
        cooling_capacity = ((flow_result / 60) * 1.01163) * 3.972 * temp_diff_result
        cooling_capacity_rounded = round(cooling_capacity, 2)
        cooling_capacity_final = max(cooling_capacity_rounded, 0.0)

        return cooling_capacity_final

    except Exception as e:
        return f"Error: {str(e)}"
