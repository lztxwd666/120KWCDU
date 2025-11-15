"""
系统总开关路由功能及辅助函数
"""

import logging

from flask import request, jsonify

from server.modbus_control.fan.write_fan import set_all_fan_statuses, set_all_fan_duty_cycles
from server.modbus_control.pump.write_pump import set_all_pump_statuses, set_all_pump_duty_cycles

logger = logging.getLogger(__name__)

# 实时系统开关状态，默认0
SYSTEM_SWITCH_STATUS = 0


def get_switch_status():
    """
    读取系统开关状态（0关，1开），默认1
    """
    global SYSTEM_SWITCH_STATUS
    return SYSTEM_SWITCH_STATUS


def set_switch_status(status: int):
    """
    设置系统开关状态
    """
    global SYSTEM_SWITCH_STATUS
    SYSTEM_SWITCH_STATUS = status


def set_system_switch():
    """
    设置系统总开关状态
    body参数: {"status": 0或1}
    返回: {"code": 0/1, "message": "...", "status": 0/1}
    """
    data = request.get_json(force=True)
    status = data.get("Status")
    if status not in [0, 1]:
        return jsonify({"code": 1, "message": "Setting failed"}), 400

    if status == 0:
        # 关闭所有风扇和水泵
        err_fan = set_all_fan_statuses([False] * 16)
        err_fan_dc = set_all_fan_duty_cycles([0.0] * 16)
        err_pump = set_all_pump_statuses([False] * 3)
        err_pump_dc = set_all_pump_duty_cycles([0.0] * 3)
        errors = []
        if err_fan:
            errors.append(f"Fan status error: {err_fan}")
        if err_fan_dc:
            errors.append(f"Fan duty cycle error: {err_fan_dc}")
        if err_pump:
            errors.append(f"Pump status error: {err_pump}")
        if err_pump_dc:
            errors.append(f"Pump duty cycle error: {err_pump_dc}")
        if errors:
            return jsonify({"code": 1, "message": "; ".join(errors)}), 500

    try:
        set_switch_status(status)
        msg = f"System switch status is {status}"
        return jsonify({"code": 0, "message": msg, "status": status}), 200
    except Exception as e:
        logger.error(f"Set system switch failed: {e}")
        return jsonify({"code": 1, "message": "Setting failed"}), 500


def get_system_switch_status():
    """
    获取系统总开关状态
    返回: {"code": 0, "message": "...", "status": 0/1}
    """
    status = get_switch_status()
    msg = f"System switch status is {status}"
    return jsonify({"code": 0, "message": msg, "status": status}), 200


def check_system_switch():
    """
    控制前置条件检查，风扇/水泵控制接口需调用
    状态为0时返回提示JSON，否则返回None
    """
    status = get_switch_status()
    if status == 0:
        return jsonify({
            "Messages": [
                "The system switch status is off, unable to perform control operations"
            ]
        }), 403
    return None
