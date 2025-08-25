import logging

from flask import jsonify

from server.modbus_control.system_state.read_flow import get_flow_rate
from server.modbus_control.system_state.read_pressure import get_supply_pressure_p1, get_supply_pressure_p2, \
    pressure_difference
from utilities.cap_utils import refrigeration_capacity
from utilities.timeout import timeout_decorator

logger = logging.getLogger(__name__)


@timeout_decorator(timeout=2)
def get_all_pressure_flow():
    flow_data = {}
    errors = {}

    # 定义数据点和对应的获取函数
    data_points = {
        "Supply_Pressure_P1": get_supply_pressure_p1,
        "Supply_Pressure_P2": get_supply_pressure_p2,
        "Flow_Rate": get_flow_rate,
        "Pressure_Difference_P1-P2": pressure_difference,
        "Refrigeration_Capacity": refrigeration_capacity
    }

    # 获取所有流量相关数据
    for name, func in data_points.items():
        value = func()
        if isinstance(value, str) and value.startswith(("Error", "ReadError", "ConnectionError")):
            flow_data[name] = 0.0
            errors[name] = value
        else:
            flow_data[name] = value

    # 如果有错误，添加错误信息
    if errors:
        flow_data["Errors"] = errors

    return jsonify(flow_data)
