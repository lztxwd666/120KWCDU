"""
主程序入口
负责初始化日志系统，确保单实例运行,启动应用控制器
"""

import atexit
import os
import signal
import sys
import tempfile
import time
import logging
from typing import Optional, TextIO

import portalocker

# 配置日志系统，忽略pymodbus库中的特定噪音日志，以减少日志污染
class IgnorePymodbusNoise(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if "failed: timed out" in msg:
            return False
        if "could not open port" in msg:
            return False
        return True

logging.getLogger("pymodbus").addFilter(IgnorePymodbusNoise())
logging.getLogger("pymodbus.logging").addFilter(IgnorePymodbusNoise())

def get_resource_path(relative_path):
    """获取资源的绝对路径，兼容开发环境和打包环境"""
    try:
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(".")
    except AttributeError as e:
        print(f"[Main] ERROR: Cannot access _MEIPASS Attribute: {e}")
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

from cdu120kw.service_function.controller_app import AppController

lock_file_handle: Optional[TextIO] = None

def is_already_running_with_lock():
    """
    使用文件锁确保单实例运行
    如果已经有实例在运行，返回True，否则返回False
    """
    global lock_file_handle
    lock_filename = os.path.join(tempfile.gettempdir(), "redfish_v1.lock")
    try:
        lock_file_handle = open(lock_filename, "w")
        portalocker.lock(lock_file_handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        return False
    except portalocker.exceptions.LockException:
        return True

def cleanup_lock_file():
    """
    清理锁文件，释放文件锁
    """
    global lock_file_handle
    if lock_file_handle is not None:
        try:
            portalocker.unlock(lock_file_handle)
            lock_file_handle.close()
            print("[Main] INFO: The lock file has been released")
        except Exception as cleanup_error:
            print(f"[Main] WARNING: Failed to release lock file: {cleanup_error}")

# 全局变量，用于跟踪清理状态
is_cleaning_up = False
interrupt_count = 0

def signal_handler(sig, frame):
    """
    信号处理函数，优雅地处理中断信号
    """
    global is_cleaning_up, interrupt_count

    interrupt_count += 1

    if is_cleaning_up:
        if interrupt_count >= 3:
            print("[Main] INFO: Force program exit...")
            sys.exit(1)
        else:
            print(f"[Main] INFO: Cleaning is in progress, please wait... (enter {3 - interrupt_count} 次 Ctrl+C 强制退出)")
            return

    is_cleaning_up = True
    print("[Main] INFO: Received interrupt signal, start cleaning resources...")
    print("[Main] INFO: Please wait for the cleaning to complete and do not press again Ctrl+C")

if __name__ == "__main__":
    controller = None

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)

    if is_already_running_with_lock():
        print("[Main] ERROR: The program is already running and cannot open multiple instances。")
        sys.exit(1)

    atexit.register(cleanup_lock_file)
    print("[Main] INFO: Application startup in progress...")

    try:
        controller = AppController()
        controller.start_service()

        # 主循环
        while True:
            time.sleep(0.1)  # 更短的睡眠时间，以便更快响应信号

    except KeyboardInterrupt:
        # 这里应该不会被执行，因为信号处理器已经接管了中断
        print("[Main] INFO: Received interrupt signal, clear resources...")
        if controller:
            controller.cleanup()
        sys.exit(0)

    except Exception as startup_error:
        print(f"[Main] ERROR: Application startup failed: {str(startup_error)}")
        if controller:
            controller.cleanup()
        sys.exit(1)

    finally:
        # 确保资源被清理
        if controller and not is_cleaning_up:
            print("[Main] INFO: Perform final cleaning...")
            controller.cleanup()