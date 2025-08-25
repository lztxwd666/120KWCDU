from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager

# 使用相对导入蓝图
from .controllers.auth import auth_bp
from .controllers.configuration import configuration_bp
from .controllers.dashboard import dashboard_bp
from .controllers.routes import configure_routes
from .controllers.system import system_bp
from .controllers.web_routes import configure_web_routes
from .utils import proxy_handler  # 使用相对导入


def create_app():
    inner_app = Flask(__name__)
    CORS(inner_app)

    # 设置 JWT 密钥
    inner_app.config["JWT_SECRET_KEY"] = "test-jwt"  # 密钥
    inner_app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 60 * 60  # 设置访问令牌过期时间（秒） 1小时
    inner_app.config["JWT_ALGORITHM"] = "HS256"  # 加密算法
    inner_app.config["JWT_COMPRESS"] = True

    # 初始化JWT，不使用变量接收
    JWTManager(inner_app)

    # 注册蓝图
    inner_app.register_blueprint(auth_bp, url_prefix="/api")
    inner_app.register_blueprint(system_bp, url_prefix="/api")
    inner_app.register_blueprint(configuration_bp, url_prefix="/api")
    inner_app.register_blueprint(dashboard_bp, url_prefix="/api")

    # 代理所有/api/redfish/开头的请求
    @inner_app.route("/api/redfish/<path:path>", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
    @jwt_required()
    @proxy_handler()
    def proxy(path):  # 这里使用了path参数
        pass

    # 配置API路由（Redfish路由）
    configure_routes(inner_app)

    # 配置前端路由
    configure_web_routes(inner_app)

    return inner_app


app = create_app()
