"""
定义所有的路由（API 路由和 Web 路由），并将它们注册到 Flask 应用中 - 修复版
修复打包后的静态资源路径问题（规范化版本）
"""

import os
import sys

from flask import Flask, current_app, send_from_directory, request

from cdu120kw.server.redfish_api.redfish_gain_fan_pump_state import get_redfish_all_fans, get_redfish_all_pumps


def get_resource_path(relative_path):
    """
    获取资源的绝对路径，兼容开发环境和打包环境
    使用规范的方法检测打包环境
    """
    # 检测是否在打包环境中运行
    is_frozen = getattr(sys, 'frozen', False)

    if is_frozen:
        # 打包环境：PyInstaller 创建临时文件夹
        # 使用规范的方法获取基础路径
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS  # PyInstaller 临时目录
        else:
            base_path = os.path.dirname(sys.executable)  # 可执行文件目录
    else:
        # 开发环境：从当前文件所在目录开始查找
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    path = os.path.join(base_path, relative_path)

    # 如果路径不存在，尝试从当前工作目录查找
    if not os.path.exists(path):
        work_path = os.path.join(os.getcwd(), relative_path)
        if os.path.exists(work_path):
            path = work_path

    return path


def configure_api_routes(app: Flask):
    """
    注册所有 API 路由
    """

    # 获取所有风扇信息
    @app.route("/redfish/v1/Chassis/1/Thermal/Fans", methods=["GET"])
    def fans_api():
        controller = current_app.config.get("CONTROLLER")
        if controller is None:
            return {"code": 1, "message": "Controller not initialized", "data": []}, 500
        return get_redfish_all_fans(controller.mapping_task_manager)

    # 获取所有水泵信息
    @app.route("/redfish/v1/Chassis/1/Thermal/Pumps", methods=["GET"])
    def pumps_api():
        controller = current_app.config.get("CONTROLLER")
        if controller is None:
            return {"code": 1, "message": "Controller not initialized", "data": []}, 500
        return get_redfish_all_pumps(controller.mapping_task_manager)


def find_static_directory():
    """
    查找静态资源目录，返回找到的路径或 None
    """
    # 尝试多个可能的路径
    possible_paths = [
        get_resource_path("cdu120kw/static_resources"),
        os.path.join(os.getcwd(), "cdu120kw", "static_resources"),
        os.path.join(os.getcwd(), "static_resources"),
    ]

    # 如果是打包环境，也尝试可执行文件目录
    if getattr(sys, 'frozen', False):
        possible_paths.append(
            os.path.join(os.path.dirname(sys.executable), "cdu120kw", "static_resources")
        )

    for path in possible_paths:
        if os.path.exists(path) and os.path.isdir(path):
            return path

    return None


def configure_web_routes(app: Flask):
    """
    注册 Web 路由，支持开发环境和打包环境 - 规范化版本
    """

    # 查找静态资源目录
    static_dir = find_static_directory()

    if static_dir is None:
        app.logger.error("Static resource directory not found in any location")
        app.logger.error("Web interface will not be available")
        # 不抛出异常，让程序继续运行（API 可能仍然可用）
        return

    # app.logger.info(f"Using static resource directory: {static_dir}")

    # 提供静态资源文件 (如JS、CSS、图片等)
    @app.route("/assets/<path:filename>")
    def serve_assets(filename):
        """
        提供 assets 目录下的静态资源文件
        """
        assets_dir = os.path.join(static_dir, "assets")

        # 安全检查：防止目录遍历攻击
        if '..' in filename or filename.startswith('/'):
            app.logger.warning(f"Potential directory traversal attempt: {filename}")
            return "Invalid filename", 400

        file_path = os.path.join(assets_dir, filename)
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            app.logger.warning(f"Asset not found: {filename}")
            return "Asset not found", 404

        return send_from_directory(assets_dir, filename)

    # 提供SPA入口，处理所有非API的GET请求
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>", methods=["GET"])
    def serve_spa(path):
        """
        对所有非API的GET请求，返回前端入口页面 index.html
        """
        if request.method != "GET":
            app.logger.warning(f"Method not allowed: {request.method} {request.path}")
            return "Method Not Allowed", 405

        # 检查 index.html 是否存在
        index_path = os.path.join(static_dir, "index.html")
        if not os.path.exists(index_path):
            app.logger.error(f"index.html not found in static resource directory: {static_dir}")

            # 返回一个简单的错误页面，而不是 500 错误
            return """
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>4RU 120KW CDU</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
                    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                    .warning { color: #856404; background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 4px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>4RU 120KW CDU Application</h1>
                    <div class="warning">
                        <strong>Web Interface Unavailable</strong>
                        <p>The web interface is currently unavailable. Please check the application logs for details.</p>
                        <p>API endpoints may still be accessible at <code>/redfish/v1/</code> endpoints.</p>
                    </div>
                </div>
            </body>
            </html>
            """, 200

        return send_from_directory(static_dir, "index.html")

    # 404错误处理，区分API和前端路由
    @app.errorhandler(404)
    def handle_404(e):
        """
        处理404错误：
        - 如果是API路由，返回JSON错误信息
        - 其他路由返回SPA入口页面
        """
        if request.path.startswith("/api/") or request.path.startswith("/redfish/"):
            app.logger.warning(f"API resource not found: {request.path}")
            return {
                "error": "Not found",
                "code": 404,
                "message": "The requested resource does not exist",
            }, 404

        app.logger.info(f"Route not found, serving SPA entry: {request.path}")

        # 检查 index.html 是否存在
        index_path = os.path.join(static_dir, "index.html")
        if not os.path.exists(index_path):
            app.logger.error(f"index.html not found in static resource directory: {static_dir}")
            return "Web interface not available", 500

        return send_from_directory(static_dir, "index.html")
