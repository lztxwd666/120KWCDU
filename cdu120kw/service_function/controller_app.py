"""
程序主控制器，负责Modbus连接管理、Flask服务启动与停止等
"""

import logging
import threading

from waitress import serve

from cdu120kw.config.config_manager import get_config
from cdu120kw.control_logic import device_data_manipulation
from cdu120kw.modbus_manager.auto_reconnect import (
    TcpAutoReconnectManager,
    RtuAutoReconnectManager,
)
from cdu120kw.modbus_manager.modbusrtu_manager import modbusrtu_manager
from cdu120kw.modbus_manager.modbustcp_manager import modbustcp_manager
from cdu120kw.server.app import create_app
from cdu120kw.server.modbus_hmi.hmi_control_device_data import start_modbus_hmi_server
from cdu120kw.task.component_operation_task import ComponentOperationTaskManager
from cdu120kw.task.low_frequency_task import LowFrequencyTaskManager
from cdu120kw.task.mapping_polling_task import MappingPollingTaskManager
from cdu120kw.task.task_thread_pool import ThreadPoolManager


class AppController:
    """
    后端服务控制器，负责Modbus连接管理、Flask服务启动与停止等
    单例模式实现，确保全局唯一
    """
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        # 单例保护，防止多线程下多次实例化
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, ip: str = None, port: int = None):
        """
        初始化控制器，只做配置和依赖初始化
        """
        if getattr(self, "_initialized", False):
            return  # 防止重复初始化
        self._initialized = True
        self.config = get_config()
        self.server_thread = None
        self.flask_server = None
        self.shutdown_event = threading.Event()
        self.service_stopped = True
        self.thread_pool = ThreadPoolManager(max_workers=5)  # 创建线程池

        self.logger = logging.getLogger(__name__)

        # 读取分组配置，设置TCP和RTU参数
        tcp_cfg = self.config.modbus_tcp
        rtu_cfg = self.config.modbus_rtu

        self.ip = ip or tcp_cfg["ip"]
        self.port = port or tcp_cfg["port"]
        modbusrtu_manager.configure(
            port=rtu_cfg["port"],
            baudrate=rtu_cfg["baud_rate"],
            bytesize=rtu_cfg["byte_size"],
            parity=rtu_cfg["parity"],
            stopbits=rtu_cfg["stop_bits"],
            timeout=rtu_cfg["timeout"],
        )

        # 计算包内绝对配置路径：<包根>/config/*.json
        import os
        pkg_root = os.path.dirname(os.path.dirname(__file__))  # .../cdu120kw
        cfg_dir = os.path.join(pkg_root, "config")
        comm_cfg_path = os.path.join(cfg_dir, "communication_task.json")
        low_cfg_path = os.path.join(cfg_dir, "low_frequency_task.json")
        comp_cfg_path = os.path.join(cfg_dir, "cdu_120kw_component.json")

        # 高频轮询任务管理器
        self.mapping_task_manager = MappingPollingTaskManager(
            tcp_manager=modbustcp_manager,
            rtu_manager=modbusrtu_manager,
            config_path=comm_cfg_path,
        )

        # 低频任务管理器
        self.low_freq_task_manager = LowFrequencyTaskManager(
            tcp_manager=modbustcp_manager,
            rtu_manager=modbusrtu_manager,
            config_path=low_cfg_path,
            pool_workers=1,
        )

        # 组件操作任务管理器
        self.component_task_manager = ComponentOperationTaskManager(
            tcp_manager=modbustcp_manager,
            rtu_manager=modbusrtu_manager,
            config_path=comp_cfg_path,
            mapping_task_manager=self.mapping_task_manager,  # 仅用于读接口兼容
        )

        # 自动重连管理器
        self.tcp_reconnect_manager = TcpAutoReconnectManager(
            modbustcp_manager,
            reconnect_callback=self.mapping_task_manager.resume,
            thread_pool=self.thread_pool,
        )

        device_data_manipulation.start_processed_register_sync(
            get_register_map_func=self.mapping_task_manager.get_register_map,
            interval=0.05
        )

        def _on_rtu_reconnected():
            """
            RTU重连成功回调，恢复任务
            """
            self.mapping_task_manager.update_mode()  # 恢复高频任务
            self.low_freq_task_manager.on_rtu_reconnected()  # 恢复低频任务
            self.component_task_manager.update_mode()  # 恢复组件任务

        self.rtu_reconnect_manager = RtuAutoReconnectManager(
            modbusrtu_manager,
            reconnect_callback=_on_rtu_reconnected,
            thread_pool=self.thread_pool,  # 传入线程池
        )

        self.mapping_task_manager.tcp_reconnect_mgr = self.tcp_reconnect_manager
        self.mapping_task_manager.rtu_reconnect_mgr = self.rtu_reconnect_manager
        self.low_freq_task_manager.rtu_reconnect_mgr = self.rtu_reconnect_manager
        self.component_task_manager.tcp_reconnect_mgr = self.tcp_reconnect_manager
        self.component_task_manager.rtu_reconnect_mgr = self.rtu_reconnect_manager

    def start_service(self):
        """
        启动Modbus服务、Flask服务和轮询任务
        无论初始连接是否成功，都要启动自动重连和任务队列，保证后续设备上电后能自动重连
        """
        try:
            tcp_connected = modbustcp_manager.start_tcpconnect(self.ip, self.port)
            rtu_connected = modbusrtu_manager.start_rtuconnect()
            # 无论连接是否成功，都要启动自动重连和任务队列
            self.mapping_task_manager.start()
            self.low_freq_task_manager.start()
            self.component_task_manager.start()
            self.tcp_reconnect_manager.start()
            self.rtu_reconnect_manager.start()
            start_modbus_hmi_server()
            self.start_flask_server()
            self.service_stopped = False
        except Exception as e:
            self.logger.error(f"Service startup error: {e}", exc_info=True)

    def stop_service(self):
        """
        停止服务和自动重连
        """
        try:
            self.logger.info("Service termination")
            self.mapping_task_manager.shutdown()
            self.low_freq_task_manager.shutdown()
            self.component_task_manager.shutdown()
            self.tcp_reconnect_manager.stop()
            self.rtu_reconnect_manager.stop()
            modbustcp_manager.disconnect()
            modbusrtu_manager.disconnect()
            self.service_stopped = True
        except Exception as e:
            self.logger.error(f"Stop service error: {e}", exc_info=True)

    def start_flask_server(self):
        """
        启动Flask后端服务（后台线程）
        """
        if self.server_thread and self.server_thread.is_alive():
            self.logger.warning("Flask service thread is still running, stop for now")
            self.stop_flask_server()

        try:
            self.server_thread = threading.Thread(
                target=self.run_flask_server, daemon=True
            )
            self.server_thread.start()
            self.logger.info("Flask service thread started")
        except Exception as e:
            self.logger.error(
                f"Failed to start Flask service thread: {e}", exc_info=True
            )

    def stop_flask_server(self):
        """
        停止Flask后端服务
        """
        if self.flask_server:
            try:
                self.flask_server.shutdown()
                self.logger.info("Flask service has requested shutdown")
            except Exception as e:
                self.logger.warning(f"Flask shutdown exception: {e}")
            finally:
                self.flask_server = None
        # self.logger.info(
        #     "Forcefully exit the process to shut down the waitress service"
        # )
        # os._exit(0)

    def run_flask_server(self):
        """
        启动waitress服务器，运行Flask应用
        """
        try:
            app = create_app(controller=self)

            flask_cfg = self.config.flask
            serve(
                app,
                host=flask_cfg["host"],
                port=flask_cfg["port"],
                threads=flask_cfg.get("threads", 4),
            )
        except Exception as e:
            self.logger.error(f"Flask server exception: {e}", exc_info=True)

    def cleanup(self):
        self.logger.info("Clean up resources")
        self.stop_service()
        self.stop_flask_server()

app_controller = AppController()