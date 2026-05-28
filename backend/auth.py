"""认证 API — 登录、获取当前用户、初始化用户"""
from router import get, post
from utils import json_response, error_response, parse_body, ok_response, hash_password, verify_password, create_token, add_oplog
from db import query_one, execute, query


@post("/api/auth/login", auth=False)
def login(handler, token_payload, qs, body):
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    if not username or not password:
        error_response(handler, "用户名和密码不能为空")
        return

    user = query_one("SELECT * FROM users WHERE username=? AND active=1", (username,))
    if not user or not verify_password(password, user["password"]):
        error_response(handler, "用户名或密码错误", 401)
        return

    token = create_token(user["id"], user["role"], user["display_name"])
    ok_response(handler, {
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
            "phone": user.get("phone", ""),
        },
    })


@get("/api/auth/me")
def get_me(handler, token_payload, qs, body):
    user_id = token_payload["sub"]
    user = query_one("SELECT id, username, display_name, role, phone FROM users WHERE id=? AND active=1", (user_id,))
    if not user:
        error_response(handler, "用户不存在", 401)
        return
    ok_response(handler, user)


@get("/api/auth/users")
def list_users(handler, token_payload, qs, body):
    """获取所有用户（供分配等操作使用）"""
    users = query("SELECT id, username, display_name, role, phone FROM users WHERE active=1 ORDER BY id")
    ok_response(handler, users)


@post("/api/auth/setup", auth=False)
def setup(handler, token_payload, qs, body):
    """初始化默认用户（仅当用户表为空时）"""
    existing = query_one("SELECT COUNT(*) as cnt FROM users")
    if existing and existing["cnt"] > 0:
        ok_response(handler, {"message": f"已有 {existing['cnt']} 个用户，跳过"})
        return

    default_users = [
        ("admin", hash_password("admin123"), "管理员", "admin"),
        ("coor01", hash_password("123456"), "李主任", "coordinator"),
        ("cs01", hash_password("123456"), "张顾问", "cs"),
        ("consultant01", hash_password("123456"), "刘顾问", "consultant"),
        ("tut01", hash_password("123456"), "王老师", "tutor"),
        ("academic01", hash_password("123456"), "陈学管", "academic"),
        ("宁老师", hash_password("123456"), "宁老师", "consultant"),
        ("G1文静", hash_password("123456"), "G1文静", "cs"),
        ("G2雨轩", hash_password("123456"), "G2雨轩", "cs"),
        ("K1馨竹", hash_password("123456"), "K1馨竹", "consultant"),
        ("K2天晴", hash_password("123456"), "K2天晴", "consultant"),
    ]
    for username, pw, display, role in default_users:
        execute(
            "INSERT INTO users (username, password, display_name, role) VALUES (?,?,?,?)",
            (username, pw, display, role),
        )
    ok_response(handler, {"message": f"已创建 {len(default_users)} 个初始用户"})
