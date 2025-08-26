import atexit
import logging
import os
import sys
import tempfile
import time
from logging.handlers import TimedRotatingFileHandler
from typing import Optional, TextIO

import portalocker

from redfish_ui.controller_app import AppController

lock_file_handle: Optional[TextIO] = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)
file_handler = TimedRotatingFileHandler(
    filename="app.log", when="midnight", interval=1, backupCount=7, encoding="utf-8"
)
console_handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(console_handler)


def is_already_running_with_lock():
    global lock_file_handle
    lock_filename = os.path.join(tempfile.gettempdir(), "redfish_v1.lock")
    try:
        lock_file_handle = open(lock_filename, "w")
        portalocker.lock(lock_file_handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        return False
    except portalocker.exceptions.LockException:
        return True


def cleanup_lock_file():
    global lock_file_handle
    if lock_file_handle is not None:
        try:
            portalocker.unlock(lock_file_handle)
            lock_file_handle.close()
            logging.info("The lock file has been released")
        except Exception as cleanup_error:
            logging.warning(f"Failed to release lock file: {cleanup_error}")


if __name__ == "__main__":
    controller = None
    if is_already_running_with_lock():
        print("The program is already running. Cannot open multiple instances.")
        sys.exit(1)

    atexit.register(cleanup_lock_file)
    logger.info("Application startup in progress...")

    try:
        controller = AppController()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, clearing resources...")
        controller.cleanup()
        sys.exit(0)
    except Exception as startup_error:
        logger.exception(f"Application startup failed: {str(startup_error)}")
        sys.exit(1)
