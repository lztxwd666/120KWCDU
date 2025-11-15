"""
批量获取所有风扇水泵状态的路由，返回标准JSON格式
直接从本地寄存器映射获取数据，无需实时读取PCBA
"""

import json
import logging
import time
from collections import OrderedDict

from flask import Response

logger = logging.getLogger(__name__)

# 用于记录风扇损坏状态的持续时间
fan_fault_time: list[float] = [0.0] * 16
# 用于记录水泵损坏状态的持续时间
pump_fault_time: list[float] = [0.0] * 3


def get_register_value(registers, address, default=0):
    """安全获取寄存器值，未读到则返回默认值"""
    return registers.get(address, default)


def get_coil_value(coils, address, default=False):
    """安全获取线圈值，未读到则返回默认值"""
    return coils.get(address, default)


def get_all_fans(mapping_task_manager):
    """
    批量获取所有风扇的状态，返回标准JSON格式
    直接从本地寄存器映射获取数据
    """
    try:
        # 获取本地寄存器和线圈映射
        reg_map = mapping_task_manager.get_register_map()
        registers = reg_map.registers
        coils = reg_map.coils

        data = []
        code = 0
        message = ""

        now = time.time()

        # 读取风扇开关状态（线圈地址41200~41207和41712~41719分别对应16个风扇）
        statuses = []
        for addr in range(41200, 41208):
            bit = get_coil_value(coils, addr)
            statuses.append("On" if bit else "Off")
        for addr in range(41712, 41720):
            bit = get_coil_value(coils, addr)
            statuses.append("On" if bit else "Off")

        # 读取风扇占空比（寄存器地址2576~2583和2608~2615分别对应16个风扇）
        duty_cycles = []
        for addr in range(2576, 2584):
            val = get_register_value(registers, addr)
            duty_cycles.append(round(val / 100.0, 2))
        for addr in range(2608, 2616):
            val = get_register_value(registers, addr)
            duty_cycles.append(round(val / 100.0, 2))

        # 读取风扇转速（寄存器地址2064,2066,...,2078和2096,2098,...,2110分别对应16个风扇）
        speeds = []
        for i in range(8):
            addr = 2064 + i * 2
            val = get_register_value(registers, addr)
            speeds.append(val)
        for i in range(8):
            addr = 2096 + i * 2
            val = get_register_value(registers, addr)
            speeds.append(val)

        # 读取风扇电流（寄存器地址2065,2067,...,2079和2097,2099,...,2111分别对应16个风扇）
        currents = []
        for i in range(8):
            addr = 2065 + i * 2
            val = get_register_value(registers, addr)
            currents.append(round(val / 1000.0, 3))
        for i in range(8):
            addr = 2097 + i * 2
            val = get_register_value(registers, addr)
            currents.append(round(val / 1000.0, 3))

        # 状态判定与数据组装
        for i in range(16):
            status = statuses[i]  # "On" 或 "Off"
            current = currents[i]
            speed = speeds[i]
            duty_cycle = duty_cycles[i]

            # Status参数：0关，1开
            status_val = 1 if status == "On" else 0

            # 默认状态
            state = 0  # 未运行

            # 判断风扇状态
            if status_val == 1:  # 开关为开
                # 正常运行：转速>500且电流>0.1A
                if (
                    isinstance(speed, (int, float))
                    and speed > 500
                    and isinstance(current, (int, float))
                    and current > 0.1
                ):
                    state = 1  # 正常运行
                    fan_fault_time[i] = 0  # 清除故障计时
                # 损坏条件：占空比>5，转速<500，电流<0.1A，持续8秒
                elif (
                    isinstance(duty_cycle, (int, float))
                    and duty_cycle > 5
                    and isinstance(speed, (int, float))
                    and speed < 500
                    and isinstance(current, (int, float))
                    and current < 0.1
                ):
                    if fan_fault_time[i] == 0:
                        fan_fault_time[i] = now
                    elif now - fan_fault_time[i] >= 8:
                        state = 4  # 损坏
                    else:
                        state = 0  # 未运行（未达到8秒）
            else:
                state = 0  # 未运行
                fan_fault_time[i] = 0  # 清除故障计时

            # 构造风扇数据，字段顺序严格固定
            fan_data = OrderedDict(
                [
                    ("Id", str(i + 1)),
                    ("Name", f"Fan {i + 1}"),
                    (
                        "DutyCycle",
                        duty_cycle if isinstance(duty_cycle, (int, float)) else 0.0,
                    ),
                    ("Current", current if isinstance(current, (int, float)) else 0.0),
                    ("Speed", speed if isinstance(speed, (int, float)) else 0.0),
                    ("State", state),  # 状态（0未运行，1运行，4损坏）
                    ("Status", status_val),  # 开关状态（0关，1开）
                ]
            )
            data.append(fan_data)

        # 构造最终返回结果，外层用OrderedDict保证顺序
        result = OrderedDict([("code", code), ("message", message), ("data", data)])
        # 用Response和json.dumps保证顺序不丢失
        return Response(
            json.dumps(result, ensure_ascii=False), mimetype="application/json"
        )

    except Exception as e:
        logger.critical(f"Failed to get all fans: {str(e)}")
        result = OrderedDict(
            [("code", 1), ("message", f"InternalError: {str(e)}"), ("data", [])]
        )
        return (
            Response(
                json.dumps(result, ensure_ascii=False), mimetype="application/json"
            ),
            500,
        )


def get_all_pumps(mapping_task_manager):
    """
    批量获取所有水泵的状态，返回标准JSON格式
    直接从本地寄存器映射获取数据
    """
    try:
        # 获取本地寄存器和线圈映射
        reg_map = mapping_task_manager.get_register_map()
        registers = reg_map.registers
        coils = reg_map.coils

        data = []
        code = 0
        message = ""

        now = time.time()

        # 读取水泵开关状态（线圈地址784~786分别对应3个水泵）
        statuses = []
        for addr in range(784, 787):
            bit = get_coil_value(coils, addr)
            statuses.append("On" if bit else "Off")

        # 读取水泵占空比（寄存器地址2192~2194分别对应3个水泵）
        duty_cycles = []
        for addr in range(2192, 2195):
            val = get_register_value(registers, addr)
            duty_cycles.append(round(val / 100.0, 2))

        # 读取水泵转速（寄存器地址2080,2082,2084分别对应3个水泵）
        speeds = []
        for i in range(3):
            addr = 2080 + i * 2
            val = get_register_value(registers, addr)
            speeds.append(val)

        # 读取水泵电流（寄存器地址2081,2083,2085分别对应3个水泵）
        currents = []
        for i in range(3):
            addr = 2081 + i * 2
            val = get_register_value(registers, addr)
            currents.append(round(val / 1000.0, 3))

        # 状态判定与数据组装
        for i in range(3):
            status = statuses[i]  # "On" 或 "Off"
            current = currents[i]
            speed = speeds[i]
            duty_cycle = duty_cycles[i]

            # Status参数：0关，1开
            status_val = 1 if status == "On" else 0

            # 默认状态
            state = 0  # 未运行

            # 判断水泵状态
            if status_val == 1:  # 开关为开
                # 正常运行：转速>500且电流>0.1A
                if (
                    isinstance(speed, (int, float))
                    and speed > 500
                    and isinstance(current, (int, float))
                    and current > 0.1
                ):
                    state = 1  # 正常运行
                    pump_fault_time[i] = 0  # 清除故障计时
                # 损坏条件：占空比>5，转速<500，电流<0.1A，持续8秒
                elif (
                    isinstance(duty_cycle, (int, float))
                    and duty_cycle > 5
                    and isinstance(speed, (int, float))
                    and speed < 500
                    and isinstance(current, (int, float))
                    and current < 0.1
                ):
                    if pump_fault_time[i] == 0:
                        pump_fault_time[i] = now
                    elif now - pump_fault_time[i] >= 8:
                        state = 4  # 损坏
                    else:
                        state = 0  # 未运行（未达到8秒）
            else:
                state = 0  # 未运行
                pump_fault_time[i] = 0  # 清除故障计时

            # 构造水泵数据，字段顺序严格固定
            pump_data = OrderedDict(
                [
                    ("Id", str(i + 1)),
                    ("Name", f"Pump {i + 1}"),
                    (
                        "DutyCycle",
                        duty_cycle if isinstance(duty_cycle, (int, float)) else 0.0,
                    ),
                    ("Current", current if isinstance(current, (int, float)) else 0.0),
                    ("Speed", speed if isinstance(speed, (int, float)) else 0.0),
                    ("State", state),  # 状态（0未运行，1运行，4损坏）
                    ("Status", status_val),  # 开关状态（0关，1开）
                ]
            )
            data.append(pump_data)

        # 构造最终返回结果，外层用OrderedDict保证顺序
        result = OrderedDict([("code", code), ("message", message), ("data", data)])
        # 用Response和json.dumps保证顺序不丢失
        return Response(
            json.dumps(result, ensure_ascii=False), mimetype="application/json"
        )

    except Exception as e:
        logger.critical(f"Failed to get all pumps: {str(e)}")
        result = OrderedDict(
            [("code", 1), ("message", f"InternalError: {str(e)}"), ("data", [])]
        )
        return (
            Response(
                json.dumps(result, ensure_ascii=False), mimetype="application/json"
            ),
            500,
        )
