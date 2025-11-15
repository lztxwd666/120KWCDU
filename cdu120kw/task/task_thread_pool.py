"""
线程池任务管理模块
提供线程池任务封装类和线程池管理类，支持任务的自动分配
"""

import queue
import threading
import time
from typing import Callable, Any, Optional


class ThreadPoolTask:
    """
    线程池任务封装类
    """

    def __init__(self, func: Callable, args: tuple = (), kwargs: dict = None, timeout: Optional[float] = None):
        self.func = func
        self.args = args
        self.kwargs = kwargs if kwargs else {}
        self.timeout = timeout
        self.result = None
        self.exception = None
        self.finished_event = threading.Event()

    def run(self):
        """
        执行任务，捕获异常
        """
        try:
            self.result = self.func(*self.args, **self.kwargs)
        except Exception as e:
            self.exception = e
        finally:
            self.finished_event.set()

    def wait(self, timeout: Optional[float] = None) -> Any:
        """
        等待任务完成，可设置超时时间
        """
        finished = self.finished_event.wait(timeout)
        if not finished:
            raise TimeoutError("Task execution timeout")
        if self.exception:
            raise self.exception
        return self.result


class ThreadPoolManager:
    """
    线程池管理类，负责自动分配、管理线程及任务队列
    """

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.task_queue = queue.Queue()
        self.threads = []
        self.shutdown_flag = threading.Event()
        self.active_tasks = set()
        self.lock = threading.Lock()
        self._init_threads()

    def _init_threads(self):
        """
        初始化线程池，创建并启动工作线程
        """
        for _ in range(self.max_workers):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self.threads.append(t)

    def _worker(self):
        """
        工作线程主循环，自动分配任务
        """
        while not self.shutdown_flag.is_set():
            try:
                task: ThreadPoolTask = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            with self.lock:
                self.active_tasks.add(task)
            try:
                if task.timeout:
                    # 支持任务超时
                    timer = threading.Timer(task.timeout, lambda: task.finished_event.set())
                    timer.start()
                    task.run()
                    timer.cancel()
                else:
                    task.run()
            finally:
                with self.lock:
                    self.active_tasks.discard(task)
                self.task_queue.task_done()

    def submit(self, func: Callable, args: tuple = (), kwargs: dict = None,
               timeout: Optional[float] = None) -> ThreadPoolTask:
        """
        提交任务到线程池，返回任务对象用于结果获取
        """
        task = ThreadPoolTask(func, args, kwargs, timeout)
        self.task_queue.put(task)
        return task

    def wait_all(self, timeout: Optional[float] = None):
        """
        等待所有任务完成，可设置超时时间
        """
        start_time = time.time()
        while True:
            with self.lock:
                if not self.active_tasks and self.task_queue.empty():
                    break
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError("Waiting for all tasks to timeout")
            time.sleep(0.1)

    def shutdown(self, wait: bool = True):
        """
        关闭线程池，支持等待所有任务完成
        """
        self.shutdown_flag.set()
        if wait:
            for t in self.threads:
                t.join()

    # 可重载此方法实现自定义任务调度策略
    def before_task(self, task: ThreadPoolTask):
        """
        任务执行前的钩子
        """
        pass

    def after_task(self, task: ThreadPoolTask):
        """
        任务执行后的钩子
        """
        pass

    # 获取当前活跃任务数
    def get_active_task_count(self) -> int:
        with self.lock:
            return len(self.active_tasks)

    # 获取线程池状态
    def get_status(self) -> dict:
        return {
            "max_workers": self.max_workers,
            "active_tasks": self.get_active_task_count(),
            "queued_tasks": self.task_queue.qsize(),
            "shutdown": self.shutdown_flag.is_set()
        }
