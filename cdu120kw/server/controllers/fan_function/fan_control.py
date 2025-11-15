"""
获取单个风扇状态/控制单个风扇的路由，返回标准JSON格式
"""

import json
import logging
import time
from collections import OrderedDict

from flask import Response, request, jsonify

from server.modbus_control.fan.read_fan import (
    get_all_fan_statuses,
    get_all_fan_currents,
    get_all_fan_speeds,
    get_all_fan_duty_cycles
)
from server.modbus_control.fan.write_fan import (
    set_all_fan_statuses,
    set_all_fan_duty_cycles
)

logger = logging.getLogger(__name__)

# 用于记录风扇损坏状态的持续时间
fan_fault_time_single: list[float] = [0.0] * 16


def get_single_fan(fan_id):
    """
    获取单个风扇所有数据，返回标准JSON格式
    """
    try:
        idx = int(fan_id) - 1
        if idx < 0 or idx >= 16:
            result = OrderedDict([
                ("code", 1),
                ("message", "Invalid fan id"),
                ("data", [])
            ])
            return Response(json.dumps(result, ensure_ascii=False), mimetype="application/json"), 400

        statuses = get_all_fan_statuses()
        currents = get_all_fan_currents()
        speeds = get_all_fan_speeds()
        duty_cycles = get_all_fan_duty_cycles()

        status = statuses[idx]  # "On" 或 "Off"
        current = currents[idx]
        speed = speeds[idx]
        duty_cycle = duty_cycles[idx]

        now = time.time()

        # Status参数：0关，1开
        status_val = 1 if status == "On" else 0

        # 默认状态
        state = 0  # 未运行

        # 状态判断逻辑
        if status_val == 1:  # 开关为开
            # 正常运行：转速>500且电流>0.1A
            if isinstance(speed, (int, float)) and speed > 500 and \
                    isinstance(current, (int, float)) and current > 0.1:
                state = 1  # 正常运行
                fan_fault_time_single[idx] = 0  # 清除故障计时
            # 损坏条件：占空比>5，转速<500，电流<0.1A，持续8秒
            elif isinstance(duty_cycle, (int, float)) and duty_cycle > 5 and \
                    isinstance(speed, (int, float)) and speed < 500 and \
                    isinstance(current, (int, float)) and current < 0.1:
                if fan_fault_time_single[idx] == 0:
                    fan_fault_time_single[idx] = now
                elif now - fan_fault_time_single[idx] >= 8:
                    state = 4  # 损坏
                else:
                    state = 0  # 未运行（未达到8秒）
        else:
            state = 0  # 未运行
            fan_fault_time_single[idx] = 0  # 清除故障计时

        # 构造风扇数据，字段顺序严格固定
        fan_data = OrderedDict([
            ("Id", str(fan_id)),
            ("Name", f"Fan {fan_id}"),
            ("DutyCycle", duty_cycle if isinstance(duty_cycle, (int, float)) else 0.0),
            ("Current", current if isinstance(current, (int, float)) else 0.0),
            ("Speed", speed if isinstance(speed, (int, float)) else 0.0),
            ("State", state),  # 状态（0未运行，1运行，4损坏）
            ("Status", status_val)  # 开关状态（0关，1开）
        ])

        result = OrderedDict([
            ("code", 0),
            ("message", ""),
            ("data", [fan_data])
        ])
        return Response(json.dumps(result, ensure_ascii=False), mimetype="application/json")

    except Exception as e:
        logger.error(f"Failed to get fan {fan_id}: {str(e)}")
        result = OrderedDict([
            ("code", 1),
            ("message", f"InternalError: {str(e)}"),
            ("data", [])
        ])
        return Response(json.dumps(result, ensure_ascii=False), mimetype="application/json"), 500


def control_single_fan(fan_id):
    """
    单个风扇写入
    """
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

    idx = int(fan_id) - 1
    if idx < 0 or idx >= 16:
        return jsonify({
            "error": "Invalid fan id",
            "code": "Base.1.0.PropertyValueError"
        }), 400

    errors = []
    response_messages = []

    if "Status" in data:
        status_value = data["Status"]
        if status_value not in ["True", "False"]:
            errors.append(f"Invalid Status value: '{status_value}', must be 'True' or 'False'")
        else:
            status_list = [False] * 16
            status_list[idx] = (status_value == "True")
            result = set_all_fan_statuses(status_list)
            if result is not None:
                errors.append(f"Fan {fan_id}: {result}")
            else:
                response_messages.append(f"Fan {fan_id} status set to {status_value}")

    if "DutyCycle" in data:
        duty_cycle = data["DutyCycle"]
        if not isinstance(duty_cycle, (int, float)) or duty_cycle < 0 or duty_cycle > 100:
            errors.append(f"Invalid DutyCycle value: {duty_cycle}, must be number between 0-100")
        else:
            duty_cycle_list = [0] * 16
            duty_cycle_list[idx] = duty_cycle
            result = set_all_fan_duty_cycles(duty_cycle_list)
            if result is not None:
                errors.append(f"Fan {fan_id}: {result}")
            else:
                response_messages.append(f"Fan {fan_id} duty cycle set to {duty_cycle}%")

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
