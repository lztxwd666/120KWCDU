import logging

from flask import jsonify

from server.modbus_control.pump.read_pump import get_pump_status, get_pump_speed, get_pump_current, get_pump_duty_cycle, \
    get_pump_pwm_amplitude
from utilities.timeout import timeout_decorator

logger = logging.getLogger(__name__)


@timeout_decorator(timeout=2)
def get_all_pumps():
    try:
        pumps_info = []
        for pump_id in range(1, 4):  # 包含1-3号水泵
            # 获取基础状态
            status = get_pump_status(pump_id)

            # 处理可能的错误状态
            health = "OK"
            if isinstance(status, str) and "Error" in status:
                health = "Critical" if "ConnectionError" in status else "Warning"
                state = "Unknown"
            else:
                state = status if status in ("On", "Off") else "Unknown"

            # 基础信息（所有水泵共有）
            pump_data = {
                "Id": str(pump_id),
                "Name": f"Pump {pump_id}",
                "Status": {
                    "State": state,
                    "Health": health
                }
            }

            # 仅水泵1/2添加详细参数
            if pump_id in (1, 2):
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
                pump_data["Status"]["Health"] = health

                # 添加详细数据
                pump_data.update(detailed_data)

                # 如果有错误，添加错误信息
                if errors:
                    pump_data["Errors"] = errors

            pumps_info.append(pump_data)

        return jsonify({"Pumps": pumps_info})

    except Exception as e:
        # 处理整个请求过程中的意外错误
        logger.critical(f"Failed to get all pumps: {str(e)}")
        return jsonify({
            "error": {
                "code": "Base.1.0.InternalError",
                "message": "Failed to retrieve pump data",
                "@Message.ExtendedInfo": [
                    {"MessageId": "Base.1.0.InternalError"}
                ]
            }
        }), 500


def get_pump_parameter(pump_id, parameter):
    if pump_id not in [1, 2]:
        return jsonify({
            "error": {
                "code": "Base.1.0.PropertyValueOutOfRange",
                "message": "Invalid pump ID, must be 1 or 2",
                "@Message.ExtendedInfo": [
                    {"MessageId": "Base.1.0.PropertyValueOutOfRange"}
                ]
            }
        }), 400

    # 参数映射
    param_map = {
        "Speed": lambda: get_pump_speed(pump_id),
        "Current": lambda: get_pump_current(pump_id),
        "DutyCycle": lambda: get_pump_duty_cycle(pump_id),
        "PwmAmplitude": get_pump_pwm_amplitude,
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
    value = param_map[parameter]()

    # 处理错误情况 - 增强错误检测
    if isinstance(value, str) and "Error" in value:
        return jsonify({
            "error": {
                "code": "Base.1.0.PropertyValueError",
                "message": f"Failed to read {parameter} for pump {pump_id}: {value}",
                "@Message.ExtendedInfo": [
                    {"MessageId": "Base.1.0.PropertyValueError"}
                ]
            }
        }), 500

    return jsonify({parameter: value})
