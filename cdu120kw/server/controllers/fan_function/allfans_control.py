"""
一键控制所有风扇的启停和占空比路由
"""

import logging

from flask import jsonify, request

from server.controllers.system_states.system_switch import check_system_switch
from server.modbus_control.fan.write_fan import (
    set_all_fan_statuses,
    set_all_fan_duty_cycles
)

logger = logging.getLogger(__name__)


def control_all_fans():
    """
    批量控制所有风扇的启停和占空比
    """

    # 系统开关前置检查
    result = check_system_switch()
    if result:
        return result

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

    if "Status" not in data and "DutyCycle" not in data:
        return jsonify({
            "error": "Invalid request, must include Status or DutyCycle parameter",
            "code": "Base.1.0.PropertyMissing"
        }), 400

    # 批量处理风扇启停状态
    if "Status" in data:
        status_value = data["Status"]
        if status_value not in ["True", "False"]:
            errors.append(f"Invalid Status value: '{status_value}', must be 'True' or 'False'")
        else:
            status_list = [status_value == "True"] * 16
            result = set_all_fan_statuses(status_list)
            if result is not None:
                errors.append(f"Batch status error: {result}")
            else:
                response_messages.append(f"All fans status set to {status_value}")

    # 批量处理风扇占空比
    if "DutyCycle" in data:
        duty_cycle = data["DutyCycle"]
        if not isinstance(duty_cycle, (int, float)) or duty_cycle < 0 or duty_cycle > 100:
            errors.append(f"Invalid DutyCycle value: {duty_cycle}, must be number between 0-100")
        else:
            duty_cycle_list = [duty_cycle] * 16
            result = set_all_fan_duty_cycles(duty_cycle_list)
            if result is not None:
                errors.append(f"Batch duty cycle error: {result}")
            else:
                response_messages.append(f"All fans duty cycle set to {duty_cycle}%")

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
