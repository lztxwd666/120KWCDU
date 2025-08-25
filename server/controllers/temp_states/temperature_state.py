import logging

from flask import jsonify

from server.modbus_control.system_state.read_temperature import get_supply_temperature_t1, get_return_temperature_t2, \
    get_ambient_t3, get_temperature_rise_t2_t1, get_approach_temperature_t1_t3
from utilities.timeout import timeout_decorator

logger = logging.getLogger(__name__)


# 获取指定温度
@timeout_decorator(timeout=2)
def get_temperature(temperature_type: str):
    temperature_map = {
        "Supply_Temperature_T1": get_supply_temperature_t1,
        "Return_Temperature_T2": get_return_temperature_t2,
        "Ambient_T3": get_ambient_t3,
        "Temperature_Rise_T2-T1": get_temperature_rise_t2_t1,
        "Approach_Temperature_T1-T3": get_approach_temperature_t1_t3,
    }

    if temperature_type not in temperature_map:
        return jsonify({
            "error": {
                "code": "Base.1.0.PropertyUnknown",
                "message": "Invalid temperature type",
                "@Message.ExtendedInfo": [
                    {"MessageId": "Base.1.0.PropertyUnknown"}
                ]
            }
        }), 400

    try:
        # 获取温度值
        value = temperature_map[temperature_type]()

        # 处理错误情况
        if isinstance(value, str) and "Error" in value:
            # 确定错误代码
            if "ConnectionError" in value:
                error_code = "Base.1.0.ConnectionError"
            else:
                error_code = "Base.1.0.PropertyValueError"

            return jsonify({
                "error": {
                    "code": error_code,
                    "message": f"Failed to read temperature {temperature_type}: {value}",
                    "@Message.ExtendedInfo": [
                        {"MessageId": error_code}
                    ]
                }
            }), 500

        return jsonify({temperature_type: value})

    except Exception as e:
        # 处理整个请求过程中的意外错误
        logger.error(f"Failed to get temperature {temperature_type}: {str(e)}")
        return jsonify({
            "error": {
                "code": "Base.1.0.InternalError",
                "message": f"Internal error while reading {temperature_type}",
                "@Message.ExtendedInfo": [
                    {"MessageId": "Base.1.0.InternalError"}
                ]
            }
        }), 500
