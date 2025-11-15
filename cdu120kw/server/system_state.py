"""
系统状态相关接口
获取所有压力（P1~P4）及压差
获取所有温度（T1~T5）及温差
获取流量（F1）s
获取制冷量
"""

import json
import logging
from collections import OrderedDict

from flask import Response

logger = logging.getLogger(__name__)


def get_register_value(registers, address, default=0):
    """安全获取寄存器值，未读到则返回默认值"""
    return registers.get(address, default)


def get_all_system_states(mapping_task_manager):
    """
    获取所有系统状态参数，包括压力、温度、流量和制冷量
    直接从本地寄存器映射获取数据，进行必要的计算和转换
    """
    try:
        # 获取本地寄存器映射
        reg_map = mapping_task_manager.get_register_map()
        registers = reg_map.registers

        data = []  # 所有参数数据列表
        errors = []  # 错误信息列表
        code = 0  # 返回码，0为正常，1为有错误
        message = ""  # 错误信息

        #  压力参数处理
        pressure_addrs = [3304, 3405, 3406, 3407]
        pressure_names = ["P1", "P2", "P3", "P4"]
        pressure_labels = ["", "", "", ""]
        pressures = []
        for i, addr in enumerate(pressure_addrs):
            raw_value = registers.get(addr, 0)
            try:
                # ADC原始值转mA，再转百分比
                if not isinstance(raw_value, int):
                    raise ValueError(f"Non integer ADC value({pressure_names[i]})")
                current_ma = raw_value / 1000.0
                clamped_ma = max(current_ma, 4.0)
                pressure_percent = 100.0 * (clamped_ma - 4.0) / 16.0
                pressure = round(pressure_percent, 2)
            except Exception as e:
                pressure = f"Error: {str(e)} ({pressure_names[i]})"
            pressures.append(pressure)

        for i, value in enumerate(pressures):
            item = OrderedDict(
                [
                    ("name", pressure_names[i]),
                    ("label", pressure_labels[i] if i < len(pressure_labels) else ""),
                    ("value", 0.0),
                    ("unit", "Psi"),
                    ("type", "pressure"),
                    ("is_original", 1),
                    ("state", 1),
                ]
            )
            if isinstance(value, str) and "Error" in value:
                code = 1
                errors.append(f"{pressure_names[i]}: {value}")
            else:
                item["value"] = value
            data.append(item)

        # 压差P4-P1
        if any(isinstance(p, str) and "Error" in p for p in pressures):
            diff = f"Error: Dependent pressure read failed (P1: {pressures[0]}, P4: {pressures[3]})"
        elif not (
            isinstance(pressures[0], (int, float))
            and isinstance(pressures[3], (int, float))
        ):
            diff = f"Error: Invalid data type (P1: {type(pressures[0])}, P4: {type(pressures[3])})"
        else:
            diff = round(pressures[3] - pressures[0], 2)
        diff_item = OrderedDict(
            [
                ("name", "P4-P1"),
                ("label", "Differential Pressure"),
                ("value", 0.0),
                ("unit", "Psi"),
                ("type", "pressure"),
                ("is_original", 0),
                ("state", 1),
            ]
        )
        if isinstance(diff, str) and "Error" in diff:
            code = 1
            errors.append(f"P4-P1: {diff}")
        else:
            diff_item["value"] = diff
        data.append(diff_item)

        #  温度参数处理
        temp_addrs = [3328, 3329, 3330, 3360, 3361]
        temp_names = ["T1", "T2", "T3", "T4", "T5"]
        temp_labels = ["", "", "", "", ""]
        temps = []
        for i, addr in enumerate(temp_addrs):
            raw_value = registers.get(addr, 0)
            try:
                # 原始值/10 得到温度
                if not isinstance(raw_value, int):
                    raise ValueError(f"Non integer ADC value({temp_names[i]})")
                temp = round(raw_value / 10.0, 1)
            except Exception as e:
                temp = f"Error: {str(e)} ({temp_names[i]})"
            temps.append(temp)

        for i, value in enumerate(temps):
            item = OrderedDict(
                [
                    ("name", temp_names[i]),
                    ("label", temp_labels[i] if i < len(temp_labels) else ""),
                    ("value", 0.0),
                    ("unit", "°C"),
                    ("type", "temperature"),
                    ("is_original", 1),
                    ("state", 1),
                ]
            )
            if isinstance(value, str) and "Error" in value:
                code = 1
                errors.append(f"{temp_names[i]}: {value}")
            else:
                item["value"] = value
            data.append(item)

        # 温差T3-T4
        if any(isinstance(t, str) and "Error" in t for t in [temps[2], temps[3]]):
            delta = f"Error: Dependent temperature read failed (T3: {temps[2]}, T4: {temps[3]})"
        elif not (
            isinstance(temps[2], (int, float)) and isinstance(temps[3], (int, float))
        ):
            delta = (
                f"Error: Invalid data type (T3: {type(temps[2])}, T4: {type(temps[3])})"
            )
        else:
            delta = round(temps[2] - temps[3], 1)
        delta_item = OrderedDict(
            [
                ("name", "T3-T4"),
                ("label", "Approach Temperature"),
                ("value", 0.0),
                ("unit", "°C"),
                ("type", "temperature"),
                ("is_original", 0),
                ("state", 1),
            ]
        )
        if isinstance(delta, str) and "Error" in delta:
            code = 1
            errors.append(f"T3-T4: {delta}")
        else:
            delta_item["value"] = delta
        data.append(delta_item)

        #  流量参数处理
        raw_flow = registers.get(3395, 0)
        try:
            # 流量公式：5.313 * (mA - 4.0)
            if not isinstance(raw_flow, int):
                raise ValueError("Non integer ADC value(F1)")
            current_ma = raw_flow / 1000.0
            clamped_ma = max(current_ma, 4.0)
            flow_value = 5.313 * (clamped_ma - 4.0)
            flow_value = min(flow_value, 5.313 * 16)
            flow = round(flow_value, 2)
        except Exception as e:
            flow = f"Error: {str(e)} (F1)"
        flow_item = OrderedDict(
            [
                ("name", "F1"),
                ("label", "Total Flow"),
                ("value", 0.0),
                ("unit", "L/Min"),
                ("type", "flow"),
                ("is_original", 1),
                ("state", 1),
            ]
        )
        if isinstance(flow, str) and "Error" in flow:
            code = 1
            errors.append(f"F1: {flow}")
        else:
            flow_item["value"] = flow
        data.append(flow_item)

        #  制冷量参数处理
        # 读取温度T1和T3（用于制冷量计算）
        raw_t1 = registers.get(3328, 0)
        raw_t3 = registers.get(3330, 0)
        try:
            if not isinstance(raw_t1, int):
                raise ValueError("Non integer ADC value(T1)")
            if not isinstance(raw_t3, int):
                raise ValueError("Non integer ADC value(T3)")
            t1 = round(raw_t1 / 10.0, 1)
            t3 = round(raw_t3 / 10.0, 1)
        except Exception as e:
            t1 = f"Error: {str(e)} (T1)"
            t3 = f"Error: {str(e)} (T3)"

        # 制冷量计算公式
        if isinstance(flow, str) and "Error" in flow:
            cooling_capacity = f"Error: Flow rate read failed - {flow}"
        elif (
            isinstance(t1, str)
            and "Error" in t1
            or isinstance(t3, str)
            and "Error" in t3
        ):
            cooling_capacity = f"Error: Temperature read failed (T1: {t1}, T3: {t3})"
        elif not (
            isinstance(flow, (int, float))
            and isinstance(t1, (int, float))
            and isinstance(t3, (int, float))
        ):
            cooling_capacity = (
                "Error: Invalid data type for cooling capacity calculation"
            )
        else:
            cap = ((flow / 60) * 1.01163) * 3.972 * (t1 - t3)
            cooling_capacity = round(max(cap, 0.0), 2)
        cap_item = OrderedDict(
            [
                ("name", "Cooling Capacity"),
                ("label", ""),
                ("value", 0.0),
                ("unit", "kW"),
                ("type", "capacity"),
                ("is_original", 0),
                ("state", 1),
            ]
        )
        if isinstance(cooling_capacity, str) and "Error" in cooling_capacity:
            code = 1
            errors.append(f"CoolingCapacity: {cooling_capacity}")
        else:
            cap_item["value"] = cooling_capacity
        data.append(cap_item)

        #  错误信息和返回结构
        if errors:
            message = "; ".join(errors)

        result = OrderedDict([("code", code), ("message", message), ("data", data)])
        return Response(
            json.dumps(result, ensure_ascii=False), mimetype="application/json"
        )

    except Exception as e:
        logger.critical(f"Failed to get all system states: {str(e)}")
        result = OrderedDict(
            [("code", 1), ("message", f"InternalError: {str(e)}"), ("data", [])]
        )
        return (
            Response(
                json.dumps(result, ensure_ascii=False), mimetype="application/json"
            ),
            500,
        )
