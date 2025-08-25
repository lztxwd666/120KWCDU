import json
import logging
from typing import Union, Tuple, Any, Dict

from flask import jsonify, request
from werkzeug.exceptions import BadRequest

from server.modbus_control.fan.read_fan import get_fan_status, get_fan_current, get_fan_speed, get_fan_duty_cycle, \
    get_fan_pwm_amplitude
from server.modbus_control.fan.write_fan import set_fan_status, set_duty_cycle, set_fan_pwm_amplitude

logger = logging.getLogger(__name__)


def fan_control(fan_id: int) -> Union[Tuple[Dict[str, Any], int], Any]:
    if fan_id < 1 or fan_id > 15:
        return jsonify({"Error": "Invalid fan ID, must be between 1-15"}), 400

    if request.method == "GET":
        # 获取风扇数据
        status = get_fan_status(fan_id)
        speed = get_fan_speed(fan_id)
        duty_cycle = get_fan_duty_cycle(fan_id)
        current = get_fan_current(fan_id)
        pwm_amplitude = get_fan_pwm_amplitude(fan_id)

        # 处理错误状态
        health = "OK"
        if any(isinstance(val, str) and "Error" in val for val in [status, speed, duty_cycle, current, pwm_amplitude]):
            health = "Warning"
            if any("ConnectionError" in val for val in [status, speed, duty_cycle, current, pwm_amplitude]):
                health = "Critical"

        # 处理状态显示
        status_display = "Unknown"
        if isinstance(status, str) and status in ("On", "Off"):
            status_display = status
        elif status == "On":
            status_display = "On"
        elif status == "Off":
            status_display = "Off"

        return jsonify(
            {
                "@odata.id": f"/redfish/v1/Chassis/1/Thermal/Fans/{fan_id}",
                "Id": str(fan_id),
                "Name": f"Fan {fan_id}",
                "Status": {
                    "State": status_display,
                    "Health": health
                },
                "Speed": speed if not isinstance(speed, str) else 0,
                "DutyCycle": duty_cycle if not isinstance(duty_cycle, str) else 0.0,
                "Current": current if not isinstance(current, str) else 0.0,
                "PwmAmplitude": pwm_amplitude if not isinstance(pwm_amplitude, str) else 0.0,
            }
        )

    if request.method == "PATCH":
        # 确保请求包含有效的JSON数据
        if not request.is_json:
            return jsonify({
                "error": "Request must be JSON format",
                "code": "Base.1.0.InvalidRequest"
            }), 400

        try:
            data = request.get_json()
        except BadRequest:
            return jsonify({
                "error": "Invalid JSON format",
                "code": "Base.1.0.MalformedJSON"
            }), 400
        except json.JSONDecodeError:
            return jsonify({
                "error": "Invalid JSON format",
                "code": "Base.1.0.MalformedJSON"
            }), 400
        except Exception as e:
            logging.error(f"Unexpected error parsing JSON: {str(e)}")
            return jsonify({
                "error": "Internal server error",
                "code": "Base.1.0.InternalError"
            }), 500

        # 验证请求是否包含有效参数
        valid_params = {"Status", "DutyCycle", "PwmAmplitude"}
        if not any(param in data for param in valid_params):
            return jsonify({
                "error": "Must include at least one valid parameter: Status, DutyCycle, or PwmAmplitude",
                "code": "Base.1.0.PropertyMissing"
            }), 400

        response_messages = []
        errors = []

        # 处理风扇启停状态
        if "Status" in data:
            status_value = data["Status"]
            if status_value not in ["On", "Off"]:
                errors.append(f"Invalid Status value: '{status_value}', must be 'On' or 'Off'")
            else:
                result = set_fan_status(fan_id, status_value == "On")
                if result is None:
                    response_messages.append(f"The switch for Fan {fan_id} is set to {status_value}")
                else:
                    errors.append(f"Failed to set fan status: {result}")

        # 处理风扇占空比
        if "DutyCycle" in data:
            duty_cycle = data["DutyCycle"]
            if not isinstance(duty_cycle, (int, float)) or duty_cycle < 0 or duty_cycle > 100:
                errors.append(f"Invalid DutyCycle value: {duty_cycle}, must be number between 0-100")
            else:
                result = set_duty_cycle(fan_id, duty_cycle)
                if result is None:
                    response_messages.append(f"The duty cycle of Fan {fan_id} is set to {duty_cycle}%")
                else:
                    errors.append(f"Failed to set duty cycle: {result}")

        # 处理PWM幅度
        if "PwmAmplitude" in data:
            pwm_amp = data["PwmAmplitude"]
            if not isinstance(pwm_amp, (int, float)):
                errors.append(f"Invalid PwmAmplitude value: {pwm_amp}, must be a number")
            else:
                result = set_fan_pwm_amplitude(fan_id, pwm_amp)
                if result is None:
                    response_messages.append(f"The PWM Amplitude of Fan {fan_id} is set to {pwm_amp}")
                else:
                    errors.append(f"Failed to set PWM amplitude: {result}")

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

    return None
