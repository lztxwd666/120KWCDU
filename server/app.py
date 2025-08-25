from flask import Flask
from flask_cors import CORS

from .controllers.routes import configure_routes
from .controllers.web_routes import configure_web_routes


def create_app(controller=None):
    inner_app = Flask(__name__)
    CORS(inner_app)

    # 存储控制器实例以便路由访问
    inner_app.config['CONTROLLER'] = controller

    # 配置API路由
    configure_routes(inner_app)

    # 配置前端路由
    configure_web_routes(inner_app)

    return inner_app


app = create_app()
