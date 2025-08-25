import logging
from collections import OrderedDict

from flask import jsonify

from server.modbus_control.fan.read_fan import get_fan_status, get_fan_current, get_fan_speed, get_fan_duty_cycle, \
    get_fan_pwm_amplitude
from utilities.timeout import timeout_decorator

logger = logging.getLogger(__name__)


@timeout_decorator(timeout=10)
def get_all_fans():
    try:
        fans_info = []
        for fan_id in range(1, 16):
            # 初始化风扇数据结构
            fan_data = OrderedDict([
                ("Id", str(fan_id)),
                ("Name", f"Fan {fan_id}"),
                ("Status", OrderedDict([
                    ("State", "Unknown"),
                    ("Health", "OK")
                ]))
            ])

            # 获取风扇状态并处理错误
            status = get_fan_status(fan_id)
            if isinstance(status, str) and "Error" in status:
                fan_data["Status"]["Health"] = "Critical" if "ConnectionError" in status else "Warning"
            else:
                fan_data["Status"]["State"] = status if status in ("On", "Off") else "Unknown"

            # 获取风扇参数并处理错误
            errors = OrderedDict()
            parameters = {
                "DutyCycle": get_fan_duty_cycle(fan_id),
                "Current": get_fan_current(fan_id),
                "Speed": get_fan_speed(fan_id),
                "PwmAmplitude": get_fan_pwm_amplitude(fan_id)
            }

            # 处理每个参数，更新健康状态
            for key, value in parameters.items():
                # noinspection PyTypeChecker
                if isinstance(value, str) and "Error" in value:
                    # 记录错误信息
                    errors[key] = value

                    # 更新健康状态（不覆盖Critical状态）
                    current_health = fan_data["Status"]["Health"]
                    if "ConnectionError" in value and current_health != "Critical":
                        fan_data["Status"]["Health"] = "Critical"
                    elif current_health == "OK":
                        fan_data["Status"]["Health"] = "Warning"

                    # 设置默认值
                    fan_data[key] = 0.0  # typ: ignore
                else:
                    fan_data[key] = value

            # 如果有错误，添加错误信息
            if errors:
                fan_data["Errors"] = errors

            fans_info.append(fan_data)

        return jsonify({"Fans": fans_info})

    except Exception as e:
        # 处理整个请求过程中的意外错误
        logger.critical(f"Failed to get all fans: {str(e)}")
        return jsonify({
            "error": {
                "code": "Base.1.0.InternalError",
                "message": "Failed to retrieve fan data",
                "@Message.ExtendedInfo": [
                    {"MessageId": "Base.1.0.InternalError"}
                ]
            }
        }), 500


def get_fan_parameter(fan_id, parameter):
    if fan_id < 1 or fan_id > 15:
        return jsonify({
            "error": {
                "code": "Base.1.0.PropertyValueOutOfRange",
                "message": "Invalid fan ID, must be between 1-15",
                "@Message.ExtendedInfo": [
                    {"MessageId": "Base.1.0.PropertyValueOutOfRange"}
                ]
            }
        }), 400

    # 参数映射
    param_map = {
        "Speed": get_fan_speed,
        "Current": get_fan_current,
        "DutyCycle": get_fan_duty_cycle,
        "PwmAmplitude": get_fan_pwm_amplitude,
    }

    if parameter not in param_map:
        return jsonify({
            "error": {
                "code": "Base.1.0.PropertyUnknown",
                "message": "Invalid parameter, must be one of Speed, Current, DutyCycle, PwmAmplitude",
                "@Message.ExtendedInfo": [
                    {"MessageId": "Base.1.0.PropertyUnknown"}
                ]
            }
        }), 400

    # 获取参数值
    value = param_map[parameter](fan_id)

    # 处理错误情况
    if isinstance(value, str) and "Error" in value:
        return jsonify({
            "error": {
                "code": "Base.1.0.PropertyValueError",
                "message": f"Failed to read {parameter} for fan {fan_id}: {value}",
                "@Message.ExtendedInfo": [
                    {"MessageId": "Base.1.0.PropertyValueError"}
                ]
            }
        }), 500

    return jsonify({parameter: value})
