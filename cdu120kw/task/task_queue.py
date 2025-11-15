"""
任务队列管理模块，支持优先级插队、线程安全、优雅关闭等功能
"""

import logging
import threading
import time
from queue import PriorityQueue, Empty
from typing import Callable, Optional


class TaskItem:
    """
    任务队列中的任务项，包含优先级、任务函数及参数
    """

    def __init__(
        self,
        priority: int,
        func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        task_id: Optional[str] = None,
    ):
        self.priority = priority
        self.func = func
        self.args = args
        self.kwargs = kwargs if kwargs else {}
        self.task_id = task_id
        self.timestamp = time.time()  # 用于同优先级时按加入顺序调度

    def __lt__(self, other):
        # 优先级高的先执行，优先级相同按时间先后
        return (self.priority, self.timestamp) < (other.priority, other.timestamp)


class TaskQueueManager:
    """
    任务队列管理类，支持优先级插队、线程安全、优雅关闭
    """

    def __init__(self, maxsize: int = 0):
        self.queue = PriorityQueue(maxsize)
        self.shutdown_flag = threading.Event()
        self.lock = threading.Lock()
        self.not_empty = threading.Condition(self.lock)
        self.active_tasks = set()
        self._task_counter = 0  # 生成唯一任务ID

    def put_task(
        self, func: Callable, args: tuple = (), kwargs: dict = None, priority: int = 10
    ):
        """
        添加任务到队列，支持多生产者线程安全
        priority值越小优先级越高
        """
        with self.lock:
            self._task_counter += 1
            task_id = f"task_{self._task_counter}"
            item = TaskItem(priority, func, args, kwargs, task_id)
            self.queue.put(item)
            self.not_empty.notify()
            return task_id

    def get_task(self, timeout: Optional[float] = None) -> Optional[TaskItem]:
        """
        获取下一个任务，支持多消费者线程安全
        队列为空时阻塞，支持优雅关闭
        """
        while not self.shutdown_flag.is_set():
            try:
                item = self.queue.get(timeout=timeout)
                with self.lock:
                    self.active_tasks.add(item.task_id)
                return item
            except Empty:
                continue
        return None

    def task_done(self, task_id: str):
        """
        标记任务完成
        """
        with self.lock:
            self.active_tasks.discard(task_id)
            self.queue.task_done()

    def remove_tasks_by_name(self, task_name: str):
        """
        移除队列中所有指定name的任务（假定args[0]有name属性）
        """
        with self.lock:
            items = []
            while not self.queue.empty():
                item = self.queue.get_nowait()
                if not (
                    hasattr(item.args[0], "name") and item.args[0].name == task_name
                ):
                    items.append(item)
            for item in items:
                self.queue.put(item)

    def shutdown(self, wait: bool = True):
        """
        优雅关闭队列，唤醒所有阻塞的消费者
        """
        self.shutdown_flag.set()
        with self.not_empty:
            self.not_empty.notify_all()
        if wait:
            while not self.queue.empty():
                time.sleep(0.1)

    def get_active_task_count(self) -> int:
        """
        获取当前活跃任务数
        """
        with self.lock:
            return len(self.active_tasks)

    def get_queue_size(self) -> int:
        """
        获取队列长度
        """
        return self.queue.qsize()

    def adjust_task_priority(self, task_id: str, new_priority: int):
        """
        动态调整指定任务的优先级（需实现队列重排）
        """
        pass

    def get_status(self) -> dict:
        return {
            "active_tasks": self.get_active_task_count(),
            "queue_size": self.get_queue_size(),
            "shutdown": self.shutdown_flag.is_set(),
        }


class BasePollingTaskManager:
    """
    任务调度基类，支持自动暂停/恢复、失败重试、阻止任务空跑等通用机制
    子类需实现 load_tasks 和 execute_task
    """

    def __init__(self, pool_workers=2):
        self.logger = logging.getLogger(__name__)
        self.task_queue = TaskQueueManager()
        self.shutdown_event = threading.Event()
        self.thread_pool = []
        self.pool_workers = pool_workers
        self.paused = False  # 全局暂停标志
        self.pause_cond = threading.Condition()
        self._has_logged_polling_paused = False  # 只输出一次暂停日志

    def load_tasks(self, config_path):
        """
        加载任务配置，子类实现
        """
        raise NotImplementedError

    def execute_task(self, comm_task):
        """
        执行单个任务，子类实现
        """
        raise NotImplementedError

    def pause(self):
        """
        暂停任务调度，所有任务线程阻塞等待
        """
        with self.pause_cond:
            self.paused = True

    def resume(self):
        """
        恢复任务调度，唤醒所有等待线程
        """
        with self.pause_cond:
            self.paused = False
            self.pause_cond.notify_all()
            self._has_logged_polling_paused = False  # 恢复后允许下次再输出暂停日志

    def wait_if_paused(self):
        """
        如果处于暂停状态，则阻塞等待恢复
        """
        with self.pause_cond:
            while self.paused:
                if not self._has_logged_polling_paused:
                    self.logger.info(
                        "Polling paused, waiting for connection recovery..."
                    )
                    self._has_logged_polling_paused = True
                self.pause_cond.wait(timeout=1)

    def start(self):
        """
        启动任务调度主循环
        """

        def worker():
            has_logged_task_retry = False
            while not self.shutdown_event.is_set():
                task_item = self.task_queue.get_task(timeout=0.5)
                if task_item is None:
                    continue
                try:
                    self.wait_if_paused()
                    while not self.shutdown_event.is_set():
                        try:
                            result = task_item.func(*task_item.args, **task_item.kwargs)
                            # 如果任务返回True表示成功，False/None表示失败需重试
                            if result is not False:
                                has_logged_task_retry = False  # 成功后重置
                                break
                            else:
                                if not has_logged_task_retry:
                                    self.logger.info(
                                        "Task execution failed, will retry after connection recovery..."
                                    )
                                    has_logged_task_retry = True
                                self.wait_if_paused()
                                time.sleep(1)
                        except Exception as e:
                            self.logger.error(f"Task execution exception: {e}")
                            self.wait_if_paused()
                            time.sleep(1)
                finally:
                    self.task_queue.task_done(task_item.task_id)

        for _ in range(self.pool_workers):
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            self.thread_pool.append(t)

    def shutdown(self):
        """
        优雅关闭所有线程和队列
        """
        self.shutdown_event.set()
        self.task_queue.shutdown(wait=True)
        for t in self.thread_pool:
            t.join(timeout=1)
