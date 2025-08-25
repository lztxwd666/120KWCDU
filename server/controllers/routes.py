from flask import Flask

from .chassis.chassis_controller import get_redfish_root, get_chassis, get_chassis_1
from .fan_controllers.allfans_control import control_all_fans
from .fan_controllers.fan_control import fan_control as fan_control_func
from .fan_states.allfans_state import get_all_fans
from .keep_connect.keepconnnect_controller import keep_connect
from .pressure_states.allpressure_state import get_all_pressure_flow
from .pump_conrollers.pump_control import pump_control as pump_control_func
from .pump_states.allpump_state import get_all_pumps
from .temp_states.alltemperature_state import get_all_temperatures
from .temp_states.temperature_state import get_temperature
from .thermal.thermal_controller import get_thermal


def configure_routes(app: Flask):
    # # 为所有需要认证的 Redfish 路由添加保护
    # protected_routes = [
    #     '/redfish/v1/Chassis',
    #     '/redfish/v1/Chassis/1',
    #     '/redfish/v1/Chassis/1/Thermal',
    #     '/redfish/v1/Chassis/1/Thermal/Fans',
    #     '/redfish/v1/Chassis/1/Thermal/Fans/All'
    #     '/redfish/v1/Chassis/1/Thermal/Pump',
    #     '/redfish/v1/Chassis/1/Thermal/Fans/<int:fan_id>',
    #     '/redfish/v1/Chassis/1/Thermal/Pump/<int:pump_id>',
    #     '/redfish/v1/Chassis/1/Thermal/Temperature',
    #     '/redfish/v1/Chassis/1/Thermal/Temperature/<string:temperature_type>',
    #     '/redfish/v1/Chassis/1/Thermal/Pressure-Flow',
    # ]
    #
    # for path in protected_routes:
    #     app.view_functions[path] = jwt_required()(app.view_functions[path])

    """Chassis/Thermal"""
    # redfish root路径
    app.add_url_rule(
        '/redfish/v1',
        view_func=get_redfish_root,
        methods=['GET']
    )

    # chassis 根路径
    app.add_url_rule(
        '/redfish/v1/Chassis',
        view_func=get_chassis,
        methods=['GET']
    )

    # 添加keep_connect接口
    app.add_url_rule(
        '/redfish/v1/keep-connect',
        view_func=keep_connect,
        methods=['GET']
    )

    # chassis_1 根路径
    app.add_url_rule(
        '/redfish/v1/Chassis/1',
        view_func=get_chassis_1,
        methods=['GET']
    )

    # thermal 根路径
    app.add_url_rule(
        '/redfish/v1/Chassis/1/Thermal',
        view_func=get_thermal,
        methods=['GET']
    )

    """风扇模块"""
    # 获取所有风扇信息
    app.add_url_rule(
        '/redfish/v1/Chassis/1/Thermal/Fans',
        view_func=get_all_fans,
        methods=['GET']
    )

    # 获取单个风扇信息/控制单个风扇
    app.add_url_rule(
        '/redfish/v1/Chassis/1/Thermal/Fans/<int:fan_id>',
        view_func=fan_control_func,  # 使用别名避免冲突
        methods=['GET', 'PATCH']
    )

    # 批量控制风扇
    app.add_url_rule(
        '/redfish/v1/Chassis/1/Thermal/Fans/All',
        view_func=control_all_fans,
        methods=['PATCH']
    )

    """水泵模块"""
    # 获取所有水泵信息
    app.add_url_rule(
        '/redfish/v1/Chassis/1/Thermal/Pump',
        view_func=get_all_pumps,
        methods=['GET']
    )

    # 获取单个水泵信息/控制单个水泵
    app.add_url_rule(
        '/redfish/v1/Chassis/1/Thermal/Pump/<int:pump_id>',
        view_func=pump_control_func,  # 使用别名避免冲突
        methods=['GET', 'PATCH']
    )

    """温度模块"""
    # 获取所有温度信息
    app.add_url_rule(
        '/redfish/v1/Chassis/1/Thermal/Temperature',
        view_func=get_all_temperatures,
        methods=['GET']
    )

    # 获取某个指定的温度值
    app.add_url_rule(
        '/redfish/v1/Chassis/1/Thermal/Temperature/<string:temperature_type>',
        view_func=get_temperature,
        methods=['GET']
    )

    """压力/流量模块"""
    # 获取所有压力/流量信息
    app.add_url_rule(
        '/redfish/v1/Chassis/1/Thermal/Pressure-Flow',
        view_func=get_all_pressure_flow,
        methods=['GET']
    )
