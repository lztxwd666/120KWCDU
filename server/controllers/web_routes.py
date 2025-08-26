# # 所有文件夹全部打包版本代码

import os

from flask import Flask, send_from_directory, request


def configure_web_routes(app: Flask):
    """配置前端路由 (直接在传入的app上注册路由)"""
    # 获取静态资源目录的绝对路径
    # 计算路径：从当前文件(web_routes.py)开始回溯
    # web_routes.py 在 server/controllers/ 目录下
    # 需要回溯到项目根目录 (redfish-server/)
    current_dir = os.path.dirname(os.path.abspath(__file__))  # server/controllers
    base_dir = os.path.dirname(os.path.dirname(current_dir))  # server 的父目录 = 项目根目录
    static_dir = os.path.join(base_dir, 'static_resources')

    # 确保路径存在
    if not os.path.exists(static_dir):
        raise FileNotFoundError(f"The static resource directory does not exist: {static_dir}")

    # 提供静态资源
    @app.route("/assets/<path:filename>")
    def serve_assets(filename):
        """提供静态资源文件 (JS/CSS/图片等)"""
        assets_dir = os.path.join(static_dir, 'assets')
        return send_from_directory(assets_dir, filename)

    # 提供SPA入口 - 处理所有GET请求
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>', methods=['GET'])
    def serve_spa(path):
        """提供单页应用入口 (捕获所有GET请求)"""
        # 只处理GET请求，其他请求类型返回405
        if request.method != 'GET':
            return "Method Not Allowed", 405

        # 路径验证)
        print(f"Service SPA entrance: {static_dir}/index.html")
        return send_from_directory(static_dir, 'index.html')

    # 添加404错误处理 (确保API优先)
    @app.errorhandler(404)
    def handle_404(e):
        """处理未找到的路由"""
        # 如果是 API 请求，返回 JSON 格式的 404
        if request.path.startswith('/api/') or request.path.startswith('/redfish/'):
            return {
                'error': 'Not found',
                'code': 404,
                'message': 'The requested resource does not exist'
            }, 404

        # 否则返回前端 SPA 入口
        return send_from_directory(static_dir, 'index.html')

# 打包为.exe + /static_resources

# import os
# import sys
#
# from flask import Flask, send_from_directory, request
#
#
# def configure_web_routes(app: Flask):
#     """配置前端路由，支持开发环境和打包环境"""
#     # 判断是否在打包环境中运行
#     is_frozen = getattr(sys, 'frozen', False)
#
#     if is_frozen:
#         # 打包环境：EXE文件所在目录就是输出目录
#         base_dir = os.path.dirname(sys.executable)
#     else:
#         # 开发环境：项目根目录
#         current_dir = os.path.dirname(os.path.abspath(__file__))
#         base_dir = os.path.dirname(os.path.dirname(current_dir))
#
#     static_dir = os.path.join(base_dir, 'static_resources')
#
#     # 确保路径存在
#     if not os.path.exists(static_dir):
#         app.logger.error(f"The static resource directory does not exist: {static_dir}")
#         # 尝试使用备选路径
#         static_dir = os.path.join(os.getcwd(), 'static_resources')
#         if not os.path.exists(static_dir):
#             raise FileNotFoundError(f"The static resource directory does not exist: {static_dir}")
#
#     # 提供静态资源文件 (JS/CSS/图片等)
#     @app.route("/assets/<path:filename>")
#     def serve_assets(filename):
#         assets_dir = os.path.join(static_dir, 'assets')
#         return send_from_directory(assets_dir, filename)
#
#     # 提供SPA入口 - 处理所有GET请求
#     @app.route('/', defaults={'path': ''})
#     @app.route('/<path:path>', methods=['GET'])
#     def serve_spa(path):
#         if request.method != 'GET':
#             return "Method Not Allowed", 405
#         return send_from_directory(static_dir, 'index.html')
#
#     # 添加 404 错误处理
#     @app.errorhandler(404)
#     def handle_404(e):
#         if request.path.startswith('/api/') or request.path.startswith('/redfish/'):
#             return {
#                 'error': 'Not found',
#                 'code': 404,
#                 'message': 'The requested resource does not exist'
#             }, 404
#         return send_from_directory(static_dir, 'index.html')
