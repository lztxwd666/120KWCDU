import json
import logging
from typing import Union, Tuple, Any, Dict

from flask import jsonify, request
from werkzeug.exceptions import BadRequest

from server.modbus_control.pump.read_pump import get_pump_status, get_pump_speed, get_pump_current, get_pump_duty_cycle, \
    get_pump_pwm_amplitude
from server.modbus_control.pump.write_pump import set_pump_status, set_pump_duty_cycle, set_pump_pwm_amplitude

logger = logging.getLogger(__name__)


def pump_control(pump_id: int) -> Union[Tuple[Dict[str, Any], int], Any]:
    # 允许1/2/3号水泵
    if pump_id not in [1, 2, 3]:
        return jsonify({
            "error": {
                "code": "Base.1.0.PropertyValueOutOfRange",
                "message": "Invalid pump ID, must be 1/2/3",
                "@Message.ExtendedInfo": [
                    {"MessageId": "Base.1.0.PropertyValueOutOfRange"}
                ]
            }
        }), 400

    if request.method == "GET":
        # 获取基础状态
        status = get_pump_status(pump_id)

        # 处理可能的错误状态
        health = "OK"
        if isinstance(status, str) and "Error" in status:
            health = "Critical" if "ConnectionError" in status else "Warning"
            state = "Unknown"
        else:
            state = status if status in ("On", "Off") else "Unknown"

        # 基础信息
        base_data = {
            "Id": str(pump_id),
            "Name": f"Pump {pump_id}",
            "Status": {
                "State": state,
                "Health": health
            }
        }

        # 仅水泵1/2显示完整数据
        if pump_id in [1, 2]:
            detailed_data = {}
            errors = {}
            critical_error = False

            # 获取详细数据
            for key, func in [
                ("Speed", get_pump_speed),
                ("DutyCycle", get_pump_duty_cycle),
                ("Current", get_pump_current),
                ("PwmAmplitude", get_pump_pwm_amplitude)
            ]:
                # 区分PWM振幅的特殊调用
                result = func(pump_id) if key != "PwmAmplitude" else func()

                # 统一错误处理
                if isinstance(result, str) and "Error" in result:
                    # 记录错误信息
                    errors[key] = result

                    # 更新健康状态（Critical优先级最高）
                    if "ConnectionError" in result:
                        critical_error = True
                    elif health == "OK":
                        health = "Warning"

                    # 保持原始数值类型
                    detailed_data[key] = 0.0
                else:
                    detailed_data[key] = result

            # 处理连接错误优先级
            if critical_error:
                health = "Critical"

            # 更新健康状态
            base_data["Status"]["Health"] = health

            # 添加详细数据
            base_data.update(detailed_data)

            # 如果有错误，添加错误信息
            if errors:
                base_data["Errors"] = errors

        return jsonify(base_data)

    if request.method == "PATCH":
        # 确保请求包含有效的JSON数据
        if not request.is_json:
            return jsonify({
                "error": {
                    "code": "Base.1.0.InvalidRequest",
                    "message": "Request must be JSON format",
                    "@Message.ExtendedInfo": [
                        {"MessageId": "Base.1.0.InvalidRequest"}
                    ]
                }
            }), 400

        try:
            data = request.get_json()
        except (BadRequest, json.JSONDecodeError):
            return jsonify({
                "error": {
                    "code": "Base.1.0.MalformedJSON",
                    "message": "Invalid JSON format",
                    "@Message.ExtendedInfo": [
                        {"MessageId": "Base.1.0.MalformedJSON"}
                    ]
                }
            }), 400
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON: {str(e)}")
            return jsonify({
                "error": {
                    "code": "Base.1.0.InternalError",
                    "message": "Internal server error",
                    "@Message.ExtendedInfo": [
                        {"MessageId": "Base.1.0.InternalError"}
                    ]
                }
            }), 500

        response_messages = []
        errors = []
        forbidden_params = []

        # 处理水泵启停状态
        if "Status" in data:
            status_value = data["Status"]
            if status_value not in ["On", "Off"]:
                errors.append(f"Invalid Status value: '{status_value}', must be 'On' or 'Off'")
            else:
                result = set_pump_status(pump_id, status_value == "On")
                if result is None:
                    response_messages.append(f"Pump {pump_id} switch set to {status_value}")
                else:
                    errors.append(f"Failed to set pump status: {result}")

        # 处理水泵占空比
        if "DutyCycle" in data:
            # 检查水泵3是否允许此参数
            if pump_id == 3:
                forbidden_params.append("DutyCycle")
            else:
                duty_cycle = data["DutyCycle"]
                if not isinstance(duty_cycle, (int, float)) or duty_cycle < 0 or duty_cycle > 100:
                    errors.append(f"Invalid DutyCycle value: {duty_cycle}, must be number between 0-100")
                else:
                    result = set_pump_duty_cycle(pump_id, duty_cycle)
                    if result is None:
                        response_messages.append(f"DutyCycle set to {duty_cycle}%")
                    else:
                        errors.append(f"Failed to set duty cycle: {result}")

        # 处理PWM幅度
        if "PwmAmplitude" in data:
            # 检查水泵3是否允许此参数
            if pump_id == 3:
                forbidden_params.append("PwmAmplitude")
            else:
                pwm_amp = data["PwmAmplitude"]
                if not isinstance(pwm_amp, (int, float)):
                    errors.append(f"Invalid PwmAmplitude value: {pwm_amp}, must be a number")
                else:
                    result = set_pump_pwm_amplitude(pwm_amp)
                    if result is None:
                        response_messages.append(f"PWM Amplitude set to {pwm_amp}")
                    else:
                        errors.append(f"Failed to set PWM amplitude: {result}")

        # 处理水泵3不允许的参数
        if forbidden_params:
            errors.append(f"Pump {pump_id} only supports Status control")
            return jsonify({
                "error": {
                    "code": "Base.1.0.PropertyNotWritable",
                    "message": f"Invalid parameters for pump {pump_id}: {', '.join(forbidden_params)}",
                    "@Message.ExtendedInfo": [
                        {"MessageId": "Base.1.0.PropertyNotWritable"}
                    ]
                }
            }), 400

        # 处理其他错误
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
