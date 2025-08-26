import logging
import os
import threading
from typing import Optional

from config import get_config
from modbustcp_manager.auto_reconnect import AutoReconnectManager
from modbustcp_manager.modbustcp_manager import modbus_manager
from server.app import create_app
from utilities.loop_writer_function import loop_writer_manager


class AppController:
    def __init__(self, ip: str = None, port: int = None):
        self.config = get_config()
        self.server_thread: Optional[threading.Thread] = None
        self.flask_server = None
        self.shutdown_event = threading.Event()
        self.service_stopped = False

        self.logger = logging.getLogger(__name__)
        self.logger.info("Initialization of backend service controller")

        self.ip = ip or self.config.MODBUS_DEFAULT_HOST
        self.port = port or self.config.MODBUS_DEFAULT_PORT

        self.reconnect_manager = AutoReconnectManager(modbus_manager)
        self.start_flask_server()
        self.logger.info("Backend service controller initialization completed")

    def start_service(self):
        """启动Modbus服务和自动重连"""
        try:
            self.logger.info(f"Attempt to connect to Modbus: {self.ip}:{self.port}")
            if modbus_manager.connect(self.ip, self.port):
                from server.controllers.keep_connect import keepconnnect_controller
                app = create_app(controller=self)
                keepconnnect_controller.start_keepalive_timer(app)
                keepconnnect_controller.update_last_request_time()
                loop_writer_manager.start_writing()
                loop_writer_manager.set_value_144(1)
                loop_writer_manager.set_value_1538(1)
                self.reconnect_manager.start()
                self.logger.info("Modbus connection successful, service started")
                self.service_stopped = False
            else:
                self.logger.error("Modbus connection failed")
                loop_writer_manager.start_writing()
        except Exception as e:
            self.logger.error(f"Error starting service: {e}", exc_info=True)

    def stop_service(self):
        """停止服务和自动重连"""
        try:
            self.logger.info("Service terminated")
            self.reconnect_manager.stop()
            loop_writer_manager.set_value_144(0)
            loop_writer_manager.set_value_1538(0)
            modbus_manager.disconnect()
            from server.controllers.keep_connect import keepconnnect_controller
            keepconnnect_controller.stop_keepalive_timer()
            self.service_stopped = True
        except Exception as e:
            self.logger.error(f"Error stopping service: {e}", exc_info=True)

    def start_flask_server(self):
        """启动Flask后端服务（后台线程）"""
        if self.server_thread and self.server_thread.is_alive():
            self.logger.warning("Flask server thread is still running, stop for now")
            self.stop_flask_server()

        try:
            self.logger.info("Start Flask server thread ..")
            self.server_thread = threading.Thread(
                target=self.run_flask_server,
                daemon=True
            )
            self.server_thread.start()
            self.logger.info("Flask server thread startup")
        except Exception as e:
            self.logger.error(f"Failed to start Flask server thread: {e}", exc_info=True)

    def stop_flask_server(self):
        if self.flask_server:
            self.logger.info("Request to close Flask server")
            try:
                self.flask_server.shutdown()
                self.logger.info("Flask server has requested shutdown")
            except Exception as e:
                self.logger.warning(f"Flask shutdown exception: {e}")
            finally:
                self.flask_server = None
        self.logger.info("Forcefully exit the process to shut down the waitress server")
        os._exit(0)

    def run_flask_server(self):
        try:
            self.logger.info("Start Flask server (waitress)...")
            app = create_app(controller=self)
            from waitress import serve
            serve(
                app,
                host=self.config.FLASK_HOST,
                port=self.config.FLASK_PORT,
                threads=4
            )
        except Exception as e:
            self.logger.error(f"Flask server error: {e}", exc_info=True)

    def cleanup(self):
        self.logger.info("clean up resources")
        self.stop_service()
        loop_writer_manager.stop_all()
        self.stop_flask_server()
