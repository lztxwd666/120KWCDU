import threading
import time

from flask import current_app, jsonify

from modbustcp_manager.modbustcp_manager import modbus_manager
from utilities.timeout import timeout_decorator

last_request_time: float = time.time()
timer_started: bool = False
timeout_timer: threading.Timer = None  # type: ignore


def update_last_request_time():
    global last_request_time
    last_request_time = time.time()


@timeout_decorator(timeout=2)
def keep_connect():
    global timer_started
    update_last_request_time()

    controller = current_app.config.get('CONTROLLER')
    if controller:
        # 如果未连接且未重连，首次请求时连接
        is_connected = modbus_manager.is_connected()
        is_reconnecting = controller.reconnect_manager.is_reconnecting

        if not is_connected and not is_reconnecting:
            controller.start_service()

        # 启动定时器
        if not timer_started:
            start_keepalive_timer()
            timer_started = True

    return jsonify({
        "timestamp": int(time.time())
    })


def check_timeout(app):
    global last_request_time, timeout_timer

    current_time = time.time()
    with app.app_context():
        time_diff = current_time - last_request_time
        app.logger.debug(f"Timeout detection: time difference={time_diff:.1f}s")

        if time_diff > 60:
            controller = app.config.get('CONTROLLER')
            if controller and modbus_manager.is_connected():
                app.logger.info(f"Timeout detected ({time_diff:.1f}s > 60s)，Service terminated")
                controller.stop_service()

    timeout_timer = threading.Timer(5.0, check_timeout, args=(app,))
    timeout_timer.daemon = True
    timeout_timer.start()


def start_keepalive_timer(app=None):
    global timeout_timer
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()
    app.logger.info("Start the Keepalive timer")
    if timeout_timer and timeout_timer.is_alive():
        timeout_timer.cancel()
    timeout_timer = threading.Timer(5.0, check_timeout, args=(app,))
    timeout_timer.daemon = True
    timeout_timer.start()


def stop_keepalive_timer():
    """停止定时器"""
    global timer_started, timeout_timer
    timer_started = False

    if timeout_timer:
        timeout_timer.cancel()
        timeout_timer = None
