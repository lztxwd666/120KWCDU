import logging

from flask import jsonify

from server.modbus_control.system_state.read_temperature import get_supply_temperature_t1, get_return_temperature_t2, \
    get_ambient_t3, get_temperature_rise_t2_t1, get_approach_temperature_t1_t3
from utilities.timeout import timeout_decorator

logger = logging.getLogger(__name__)


@timeout_decorator(timeout=2)
def get_all_temperatures():
    try:
        temp_data = {}
        errors = {}
        critical_error = False

        # 定义温度类型和对应的获取函数
        temp_types = {
            "Supply_Temperature_T1": get_supply_temperature_t1,
            "Return_Temperature_T2": get_return_temperature_t2,
            "Ambient_T3": get_ambient_t3,
            "Temperature_Rise_T2-T1": get_temperature_rise_t2_t1,
            "Approach_Temperature_T1-T3": get_approach_temperature_t1_t3,
        }

        # 获取所有温度数据
        for name, func in temp_types.items():
            value = func()

            # 处理错误情况
            if isinstance(value, str) and "Error" in value:
                errors[name] = value
                temp_data[name] = 0.0

                # 标记关键错误
                if "ConnectionError" in value:
                    critical_error = True
            else:
                temp_data[name] = value

        # 如果有错误，添加错误信息
        if errors:
            temp_data["Errors"] = errors

            # 添加整体健康状态
            health_status = "Critical" if critical_error else "Warning"
            temp_data["Health"] = health_status

        return jsonify(temp_data)

    except Exception as e:
        # 处理整个请求过程中的意外错误
        logger.critical(f"Failed to get all temperatures: {str(e)}")
        return jsonify({
            "error": {
                "code": "Base.1.0.InternalError",
                "message": "Failed to retrieve temperature data",
                "@Message.ExtendedInfo": [
                    {"MessageId": "Base.1.0.InternalError"}
                ]
            }
        }), 500
