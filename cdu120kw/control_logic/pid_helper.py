"""
PID算法实现与配置加载模块
"""

import json
import os
from typing import Dict, Any

# 配置文件默认相对路径(相对当前文件上一层目录)
_PID_SETTINGS_PATH = "config/settings.json"


def _load_pid_config(config_path: str = _PID_SETTINGS_PATH) -> Dict[str, Any]:
    """
    读取 PID 配置文件:
    1. 通过 __file__ 获取当前文件绝对路径。
    2. 拼接到目标配置路径(向上一层再进入 config)。
    3. 使用 utf-8-sig 兼容可能带 BOM 的 JSON。
    返回: 解析后的字典, 不做键名校验。
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    abs_path = os.path.normpath(os.path.join(base_dir, "..", config_path))
    with open(abs_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


# 模块导入即读取配置, 形成一次性缓存; 若文件不存在会直接抛出异常
PID_CONFIG_CACHE: Dict[str, Any] = _load_pid_config()


def reload_pid_config(config_path: str = _PID_SETTINGS_PATH) -> None:
    """
    热更新配置:
    - 当外部修改 settings.json 后调用此函数使后续 create_from_cache 生效。
    - 不对旧实例参数进行自动同步(需自行重新实例化或调用 set_pid_var)。
    """
    global PID_CONFIG_CACHE
    PID_CONFIG_CACHE = _load_pid_config(config_path)


class PidHelper:
    """
    PID 控制器:
    属性:
        kp/ki/kd: 比例/积分/微分系数
        dt: 离散时间步长 (采样周期)
        output_min/output_max: 输出限幅上下界
        previous_error: 上一次误差, 用于计算微分
        integral: 积分累积项
        previous_measured_value: 预留字段
    使用:
        1. pid = PidHelper.create_from_cache()
        2. output = pid.calculate(target_value, measured_value)
        3. 根据需要调用 set_pid_var 动态调参
    """
    def __init__(
        self,
        kp=None,
        ki=None,
        kd=None,
        output_min=None,
        output_max=None,
        dt: float = 1.0
    ):
        self.kp = 0.0
        self.ki = 0.0
        self.kd = 0.0

        # 运行状态变量
        self.previous_error = 0.0     # 上一周期误差
        self.integral = 0.0           # 积分累积
        self.previous_measured_value = 0.0

        # 输出限幅
        self.output_min = 0.0
        self.output_max = 0.0

        # 采样周期 dt (秒)
        self.dt = 1.0

        # 传入参数赋值
        if kp is not None:
            self.kp = float(kp)
        if ki is not None:
            self.ki = float(ki)
        if kd is not None:
            self.kd = float(kd)
        if output_min is not None:
            self.output_min = float(output_min)
        if output_max is not None:
            self.output_max = float(output_max)
        if dt is not None:
            self.dt = float(dt)

        # 再次复位状态(保证初始误差与积分为 0)
        self.previous_error = 0.0
        self.integral = 0.0

    @classmethod
    def create_from_cache(cls, pid_type="pid"):
        """
        使用缓存配置创建实例:
        期望 JSON 结构:
        {
          "pid": {
            "Kp": 1.0,
            "Ki": 0.0,
            "Kd": 0.0,
            "Dt": 1.0,
            "outputmin": 0.0,
            "outputmax": 100.0
          }
        }
        若键缺失则使用默认值 0.0 / 1.0 (dt)
        """
        pid_cfg = PID_CONFIG_CACHE.get(pid_type, {})
        kp = pid_cfg.get("Kp", 0.0)
        ki = pid_cfg.get("Ki", 0.0)
        kd = pid_cfg.get("Kd", 0.0)
        dt = pid_cfg.get("Dt", 1.0)
        out_min = pid_cfg.get("outputmin", 0.0)
        out_max = pid_cfg.get("outputmax", 0.0)
        return cls(kp=kp, ki=ki, kd=kd, output_min=out_min, output_max=out_max, dt=dt)

    def set_pid_var(self, kp, ki, kd, *args):
        """
        动态更新 PID 参数
        """
        if self.kp != kp:
            self.kp = kp
        if self.ki != kp:
            self.ki = ki
        if self.kd != kp:
            self.kd = kd

        # 附加更新(三个值都提供才处理)
        if len(args) == 3:
            output_min, output_max, dt = args
            if self.output_min != output_min:
                self.output_min = output_min
            if self.output_max != output_max:
                self.output_max = output_max
            if self.dt != dt:
                self.dt = dt

    def calculate(
        self,
        target_value,
        measured_value,
        last_set_var: float = 0.0,
        is_add: bool = True
    ):
        """
        计算一次 PID 输出:
        参数:
            target_value: 目标值
            measured_value: 当前测量值
            last_set_var: 前馈或外加偏置(默认 0.0)
            is_add: True -> 误差 = 目标 - 测量; False -> 误差 = 测量 - 目标 (反向控制时使用)
        步骤:
            1. 误差计算
            2. 积分项累积 (未做限幅或抗积分饱和处理)
            3. 微分项 = 当前误差 - 上一误差 / dt (未滤波, 噪声较大会放大)
            4. PID 合成 + 外加偏置
            5. 限幅输出到 [output_min, output_max]
            6. 记录当前误差供下次微分使用
        返回:
            限幅后的控制输出值
        """
        # 1. 误差
        error = target_value - measured_value if is_add else measured_value - target_value

        # 2. 比例项
        proportional = self.kp * error

        # 3. 积分项累加(若长时间偏差大可能导致积分飘逸)
        self.integral += error * self.dt
        integral_term = self.ki * self.integral

        # 4. 微分项(基于误差变化率)
        derivative = (error - self.previous_error) / self.dt
        derivative_term = self.kd * derivative

        # 5. PID 合成 + 外部偏置量
        output = proportional + integral_term + derivative_term + last_set_var

        # 6. 限幅处理(防止输出超出执行器能力范围)
        output = max(self.output_min, min(self.output_max, output))

        # 7. 存储误差用于下一周期微分计算
        self.previous_error = error
        # print(f"[PidHelper] DEBUG: P={proportional:.3f}, I={integral_term:.3f}, D={derivative_term:.3f}, Output={output:.3f}, Target={target_value}, Measured={measured_value}")
        return output

    def reset(self):
        """
        重置控制器状态:
        - 清空积分与历史误差
        - 不修改 kp/ki/kd/限幅/dt
        在需要重新开始控制(如突然更换 目标值 或长时间失控后)调用。
        """
        self.previous_error = 0.0
        self.integral = 0.0