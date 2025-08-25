import concurrent.futures
import functools

from flask import jsonify, copy_current_request_context


def timeout_decorator(timeout=3):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 用 Flask 提供的装饰器复制上下文
            @copy_current_request_context
            def call_with_context(*a, **kw):
                return func(*a, **kw)

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(call_with_context, *args, **kwargs)
                try:
                    return future.result(timeout=timeout)
                except concurrent.futures.TimeoutError:
                    return jsonify({"error": "Request timeout"}), 504

        return wrapper

    return decorator
