import logging

from flask import jsonify, request

from server.modbus_control.fan.write_fan import set_fan_status, set_duty_cycle

logger = logging.getLogger(__name__)


def control_all_fans():
    """批量控制所有风扇的启停和占空比"""
    # 确保请求包含有效的JSON数据
    if not request.is_json:
        return jsonify({
            "error": "Request must be JSON format",
            "code": "Base.1.0.InvalidRequest"
        }), 400

    try:
        data = request.get_json()
    except Exception as e:
        logger.error(f"Error parsing JSON: {str(e)}")
        return jsonify({
            "error": "Invalid JSON format",
            "code": "Base.1.0.MalformedJSON"
        }), 400

    response_messages = []
    errors = []

    # 验证请求是否包含有效参数
    if "Status" not in data and "DutyCycle" not in data:
        return jsonify({
            "error": "Invalid request, must include Status or DutyCycle parameter",
            "code": "Base.1.0.PropertyMissing"
        }), 400

    # 批量处理风扇启停状态
    if "Status" in data:
        status_value = data["Status"]
        if status_value not in ["On", "Off"]:
            errors.append(f"Invalid Status value: '{status_value}', must be 'On' or 'Off'")
        else:
            status_errors = []
            for fan_id in range(1, 16):
                result = set_fan_status(fan_id, status_value == "On")
                if result is not None:
                    status_errors.append(f"Fan {fan_id}: {result}")

            if status_errors:
                errors.extend(status_errors)
            else:
                response_messages.append(f"All fans status set to {status_value}")

    # 批量处理风扇占空比
    if "DutyCycle" in data:
        duty_cycle = data["DutyCycle"]
        if not isinstance(duty_cycle, (int, float)) or duty_cycle < 0 or duty_cycle > 100:
            errors.append(f"Invalid DutyCycle value: {duty_cycle}, must be number between 0-100")
        else:
            duty_errors = []
            for fan_id in range(1, 16):
                result = set_duty_cycle(fan_id, duty_cycle)
                if result is not None:
                    duty_errors.append(f"Fan {fan_id}: {result}")

            if duty_errors:
                errors.extend(duty_errors)
            else:
                response_messages.append(f"All fans duty cycle set to {duty_cycle}%")

    # 处理错误和响应
    if errors:
        return jsonify({
            "error": {
                "code": "Base.1.0.PropertyValueError",
                "message": "; ".join(errors),
                "@Message.ExtendedInfo": [
                    {"MessageId": "Base.1.0.PropertyValueError"}
                ]
            }
        }), 400

    return jsonify({"Messages": response_messages}), 200
