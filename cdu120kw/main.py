"""
主程序入口
负责初始化日志系统，确保单实例运行,启动应用控制器
"""

"""
主程序入口 - 修复版
修复多次Ctrl+C中断导致的异常问题
"""

import atexit
import logging
import os
import signal
import sys
import tempfile
import time
from logging.handlers import TimedRotatingFileHandler
from typing import Optional, TextIO

import portalocker


def get_resource_path(relative_path):
    """获取资源的绝对路径，兼容开发环境和打包环境"""
    try:
        # 检查是否存在 _MEIPASS 属性
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(".")
    except AttributeError as e:
        logging.error(f"Cannot access _MEIPASS Attribute: {e}")
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

from cdu120kw.service_function.controller_app import AppController

lock_file_handle: Optional[TextIO] = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)
# 在设置日志之前，确保log文件夹存在
log_dir = "log"
os.makedirs(log_dir, exist_ok=True)

file_handler = TimedRotatingFileHandler(
    filename=os.path.join(log_dir, "app.log"),
    when="midnight",
    interval=1,
    backupCount=7,
    encoding="utf-8",
)
console_handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(console_handler)


class Ignore3rdPartyErrorFilter(logging.Filter):
    """
    过滤掉第三方库产生的已知无害错误日志
    例如requests库的连接超时错误
    这些错误不影响程序运行，且会频繁出现
    只保留其他重要日志
    过滤规则可根据需要调整
    """

    def filter(self, record):
        msg = record.getMessage()
        if "Connection to (" in msg and "failed: timed out" in msg:
            return False
        if "could not open port" in msg:
            return False
        return True


for handler in logger.handlers:
    handler.addFilter(Ignore3rdPartyErrorFilter())


def is_already_running_with_lock():
    """
    使用文件锁确保单实例运行
    如果已经有实例在运行，返回True，否则返回False
    通过在临时目录创建一个锁文件，并尝试获取独占锁
    如果获取锁失败，说明已有实例在运行
    失败时不抛出异常，直接返回True
    这样可以避免程序崩溃
    只要程序正常退出，锁文件会被正确释放
    这样下次启动时可以重新获取锁
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
    在程序退出时调用，确保锁文件被正确释放
    这样下次启动时可以重新获取锁
    """
    global lock_file_handle
    if lock_file_handle is not None:
        try:
            portalocker.unlock(lock_file_handle)
            lock_file_handle.close()
            logging.info("The lock file has been released")
        except Exception as cleanup_error:
            logging.warning(f"Failed to release lock file: {cleanup_error}")


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
            logger.info("Force program exit...")
            sys.exit(1)
        else:
            logger.info(f"Cleaning is in progress, please wait... (enter {3 - interrupt_count} 次 Ctrl+C 强制退出)")
            return

    is_cleaning_up = True
    logger.info("Received interrupt signal, start cleaning resources...")
    logger.info("Please wait for the cleaning to complete and do not press again Ctrl+C")


if __name__ == "__main__":
    controller = None

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)

    if is_already_running_with_lock():
        print("The program is already running and cannot open multiple instances。")
        sys.exit(1)

    atexit.register(cleanup_lock_file)
    logger.info("Application startup in progress...")

    try:
        controller = AppController()
        controller.start_service()

        # 主循环
        while True:
            time.sleep(0.1)  # 更短的睡眠时间，以便更快响应信号

    except KeyboardInterrupt:
        # 这里应该不会被执行，因为信号处理器已经接管了中断
        logger.info("Received interrupt signal, clear resources...")
        if controller:
            controller.cleanup()
        sys.exit(0)

    except Exception as startup_error:
        logger.exception(f"Application startup failed: {str(startup_error)}")
        if controller:
            controller.cleanup()
        sys.exit(1)

    finally:
        # 确保资源被清理
        if controller and not is_cleaning_up:
            logger.info("Perform final cleaning...")
            controller.cleanup()

