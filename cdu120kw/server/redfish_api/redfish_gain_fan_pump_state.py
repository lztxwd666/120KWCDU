import json
import logging
from collections import OrderedDict

from flask import Response

from cdu120kw.control_logic.device_data_manipulation import get_all_fan_states, get_all_pump_states

logger = logging.getLogger(__name__)

def get_redfish_all_fans(mapping_task_manager, component_config_path="config/cdu_120kw_component.json"):
    """
    Redfish风扇路由，DutyCycle上下限根据配置文件动态输出
    """
    try:
        reg_map = mapping_task_manager.get_register_map()
        # 获取处理后的风扇数据
        fans_data = get_all_fan_states(reg_map, component_config_path)

        # 加载配置文件，获取min_duty/max_duty
        with open(component_config_path, "r", encoding="utf-8-sig") as f:
            config = json.load(f)
        fans_cfg = config.get("fans", [])

        fans_list = []
        for i, fan in enumerate(fans_data):
            # 获取min_duty/max_duty，若无则为0
            min_duty = 0
            max_duty = 0
            if i < len(fans_cfg):
                cfg = fans_cfg[i].get("config", {})
                min_duty = cfg.get("min_duty", 0)
                max_duty = cfg.get("max_duty", 0)

            # 状态映射
            state_val = fan.get("state", 0)
            if state_val == 1:
                state_str = "Enabled"
                health_str = "OK"
            elif state_val == 2:
                state_str = "Enabled"
                health_str = "Critical"
            else:
                state_str = "Disabled"
                health_str = "OK"

            fan_item = OrderedDict([
                ("@odata.id", f"/redfish/v1/Chassis/1/Thermal/Fans/{i+1}"),
                ("@odata.type", "#Thermal.v1_7_0.Thermal"),
                ("Id", str(i+1)),
                ("Name", fan.get("name", f"Fan {i+1}")),
                ("Status", {
                    "State": state_str,
                    "Health": health_str
                }),
                ("DutyCycle", {
                    "Reading": fan.get("duty_cycle", 0),
                    "Min": min_duty,
                    "Max": max_duty,
                    "Units": "%"
                }),
                ("Speed", {
                    "Reading": fan.get("speed", 0),
                    "Desired": 0,
                    "Min": 0,
                    "Max": 0,
                    "Units": "RPM"
                }),
                ("ElectricalCurrent", {
                    "Reading": fan.get("current", 0),
                    "Min": 0,
                    "Max": 6,
                    "Units": "A"
                }),
                ("Actions", {
                    "#Fan.ResetMetrics": {
                        "target": f"/redfish/v1/Chassis/1/Thermal/Fans/{i+1}/Actions/Fan.ResetMetrics",
                        "title": "Reset Fan Metrics"
                    },
                    "#Cdu.FanControl": {
                        "target": f"/redfish/v1/Chassis/1/Thermal/Fans/{i+1}/Actions/Cdu.FanControl",
                        "title": "Control Fan Operation",
                        "PowerControl@Redfish.AllowableValues": ["On", "Off"],
                        "DutyCycleControl@Redfish.AllowableRange": {
                            "From": min_duty,
                            "To": max_duty
                        }
                    }
                })
            ])
            fans_list.append(fan_item)

        result = OrderedDict([
            ("@odata.context", "/redfish/v1/$metadata#Thermal.v1_7_0.Thermal"),
            ("@odata.id", "/redfish/v1/Chassis/1/Thermal/Fans"),
            ("@odata.type", "#Thermal.v1_7_0.Thermal"),
            ("Id", "Fans"),
            ("Name", "Fans"),
            ("Fans", fans_list)
        ])
        return Response(json.dumps(result, ensure_ascii=False), mimetype="application/json")

    except Exception as e:
        logger.critical(f"Failed to get redfish fans: {str(e)}")
        result = OrderedDict([
            ("code", 1),
            ("message", f"InternalError: {str(e)}"),
            ("data", [])
        ])
        return Response(json.dumps(result, ensure_ascii=False), mimetype="application/json"), 500

def get_redfish_all_pumps(mapping_task_manager, component_config_path="config/cdu_120kw_component.json"):
    """
    Redfish水泵路由，DutyCycle上下限根据配置文件动态输出
    """
    try:
        reg_map = mapping_task_manager.get_register_map()
        # 获取处理后的水泵数据
        pumps_data = get_all_pump_states(reg_map, component_config_path)
        # 加载配置文件，获取min_duty/max_duty
        with open(component_config_path, "r", encoding="utf-8-sig") as f:
            config = json.load(f)
        pumps_cfg = config.get("pumps", [])

        pumps_list = []
        for i, pump in enumerate(pumps_data):
            # 获取min_duty/max_duty，若无则为0
            min_duty = 0
            max_duty = 0
            if i < len(pumps_cfg):
                cfg = pumps_cfg[i].get("config", {})
                min_duty = cfg.get("min_duty", 0)
                max_duty = cfg.get("max_duty", 0)
            # 状态映射
            state_val = pump.get("state", 0)
            if state_val == 1:
                state_str = "Enabled"
                health_str = "OK"
            elif state_val == 2:
                state_str = "Enabled"
                health_str = "Critical"
            else:
                state_str = "Disabled"
                health_str = "OK"
            pump_item = OrderedDict([
                ("@odata.id", f"/redfish/v1/Chassis/1/Thermal/Pumps/{i+1}"),
                ("@odata.type", "#Thermal.v1_7_0.Thermal"),
                ("Id", str(i+1)),
                ("Name", pump.get("name", f"Pump {i+1}")),
                ("Status", {
                    "State": state_str,
                    "Health": health_str
                }),
                ("DutyCycle", {
                    "Reading": pump.get("duty_cycle", 0),
                    "Min": min_duty,
                    "Max": max_duty,
                    "Units": "%"
                }),
                ("Speed", {
                    "Reading": pump.get("speed", 0),
                    "Desired": 0,
                    "Min": 0,
                    "Max": 0,
                    "Units": "RPM"
                }),
                ("ElectricalCurrent", {
                    "Reading": pump.get("current", 0),
                    "Min": 0,
                    "Max": 6,
                    "Units": "A"
                }),
                ("Actions", {
                    "#Pump.ResetMetrics": {
                        "target": f"/redfish/v1/Chassis/1/Thermal/Pumps/{i+1}/Actions/Pump.ResetMetrics",
                        "title": "Reset Pump Metrics"
                    },
                    "#Cdu.PumpControl": {
                        "target": f"/redfish/v1/Chassis/1/Thermal/Pumps/{i+1}/Actions/Cdu.PumpControl",
                        "title": "Control Pump Operation",
                        "PowerControl@Redfish.AllowableValues": ["On", "Off"],
                        "DutyCycleControl@Redfish.AllowableRange": {
                            "From": min_duty,
                            "To": max_duty
                        }
                    }
                })
            ])
            pumps_list.append(pump_item)

        result = OrderedDict([
            ("@odata.context", "/redfish/v1/$metadata#Thermal.v1_7_0.Thermal"),
            ("@odata.id", "/redfish/v1/Chassis/1/Thermal/Pumps"),
            ("@odata.type", "#Thermal.v1_7_0.Thermal"),
            ("Id", "Pumps"),
            ("Name", "Pumps"),
            ("Pumps", pumps_list)
        ])
        return Response(json.dumps(result, ensure_ascii=False), mimetype="application/json")

    except Exception as e:
        logger.critical(f"Failed to get redfish pumps: {str(e)}")
        result = OrderedDict([
            ("code", 1),
            ("message", f"InternalError: {str(e)}"),
            ("data", [])
        ])
        return Response(json.dumps(result, ensure_ascii=False), mimetype="application/json"), 500