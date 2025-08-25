from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token

# 使用相对导入服务
from ..services.user_service import UserService  # 使用两层相对导入

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    username = request.json.get("username", None)
    password = request.json.get("password", None)

    user = UserService.login(username, password)
    if not user:
        return jsonify({"code": 1, "message": "Login failed"}), 401

    access_token = create_access_token(identity=username)

    response = jsonify({"code": 0, "message": "Login successful"})
    response.headers["Authorization"] = f"Bearer {access_token}"
    response.headers["Access-Control-Expose-Headers"] = "Authorization"

    return response


@auth_bp.route("/logout", methods=["GET"])
def logout():
    return jsonify({"code": 0, "message": "Sign out successful"})
