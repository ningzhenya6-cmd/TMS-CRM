"""用户管理 API"""
from router import get, post, put
from utils import ok_response, error_response, hash_password, require_role
from db import query, query_one, execute


@get("/api/users")
def list_users(handler, token_payload, qs, body):
    if not require_role(token_payload, ["admin", "supervisor"]):
        error_response(handler, "无权访问", 403)
        return
    users = query("SELECT id, username, display_name, role, phone, active, created_at FROM users ORDER BY id")
    ok_response(handler, users)


@post("/api/users")
def create_user(handler, token_payload, qs, body):
    if not require_role(token_payload, ["admin", "supervisor"]):
        error_response(handler, "无权操作", 403)
        return
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    display_name = (body.get("display_name") or "").strip()
    role = body.get("role", "cs")
    if not username or not password:
        error_response(handler, "用户名和密码不能为空")
        return
    existing = query_one("SELECT id FROM users WHERE username=?", (username,))
    if existing:
        error_response(handler, "用户名已存在")
        return
    execute(
        "INSERT INTO users (username, password, display_name, role, phone) VALUES (?,?,?,?,?)",
        (username, hash_password(password), display_name, role, body.get("phone", "")),
    )
    ok_response(handler, {"message": "创建成功"}, 201)


@put("/api/users/{user_id}")
def update_user(handler, token_payload, qs, body, user_id=None):
    if not require_role(token_payload, ["admin", "supervisor"]):
        error_response(handler, "无权操作", 403)
        return
    user_id = int(user_id)
    user = query_one("SELECT id FROM users WHERE id=?", (user_id,))
    if not user:
        error_response(handler, "用户不存在", 404)
        return
    updates = []
    params = []
    if "display_name" in body:
        updates.append("display_name=?")
        params.append(body["display_name"])
    if "role" in body:
        updates.append("role=?")
        params.append(body["role"])
    if "phone" in body:
        updates.append("phone=?")
        params.append(body["phone"])
    if "password" in body and body["password"]:
        updates.append("password=?")
        params.append(hash_password(body["password"]))
    if "active" in body:
        updates.append("active=?")
        params.append(1 if body["active"] else 0)
    if updates:
        params.append(user_id)
        execute(f"UPDATE users SET {','.join(updates)} WHERE id=?", tuple(params))
    ok_response(handler, {"message": "已更新"})
