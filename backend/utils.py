"""
工具模块 — JWT、密码加Hash、JSON 响应、操作日志
纯 Python stdlib，无外部依赖
"""
import hashlib
import hmac
import json
import base64
import time
import os
from http.server import BaseHTTPRequestHandler

# ── 配置 ──
SECRET_KEY = os.environ.get("TMS_SECRET", "tms-secret-key-2026")
JWT_EXPIRE = 480 * 60  # 8 小时（秒）


# ── JSON 响应 ──

def json_response(handler: BaseHTTPRequestHandler, data, status=200):
    """发送 JSON 响应"""
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def error_response(handler: BaseHTTPRequestHandler, msg: str, status=400):
    json_response(handler, {"error": msg}, status)


def ok_response(handler: BaseHTTPRequestHandler, data=None, status=200):
    json_response(handler, {"data": data}, status)


def parse_body(handler: BaseHTTPRequestHandler) -> dict:
    """读取并解析请求体 JSON"""
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


# ── JWT ──

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def create_token(user_id: int, role: str, username: str) -> str:
    """生成 JWT token"""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "sub": user_id,
        "role": role,
        "name": username,
        "exp": int(time.time()) + JWT_EXPIRE,
    }).encode())
    sig = _b64url(hmac.new(SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def decode_token(token: str):
    """解析 JWT，返回 payload 或 None"""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header_str, payload_str, sig_str = parts
    # 验签
    expected = _b64url(hmac.new(SECRET_KEY.encode(), f"{header_str}.{payload_str}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig_str, expected):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_str))
    except Exception:
        return None
    # 检查过期
    if payload.get("exp", 0) < time.time():
        return None
    return payload


# ── 密码 ──

def hash_password(password: str) -> str:
    """使用 sha256 加盐哈希密码（新格式：固定盐值）"""
    salt = "tms_salt_2026"
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def verify_password(password: str, stored: str) -> bool:
    """兼容新旧两种密码哈希格式"""
    if "$" in stored:
        # 旧格式: salt$sha256(salt+password)
        try:
            salt, h = stored.split("$", 1)
            return hashlib.sha256((salt + password).encode()).hexdigest() == h
        except (ValueError, AttributeError):
            return False
    # 新格式: sha256("tms_salt_2026:password")
    return hash_password(password) == stored


# ── 操作日志 ──

def add_oplog(user_id: int, username: str, action: str, target_type: str,
              target_id: int = None, summary: str = "", detail: str = ""):
    """记录操作日志"""
    from db import execute
    execute(
        "INSERT INTO operation_logs (user_id, username, action, target_type, target_id, summary, detail) "
        "VALUES (?,?,?,?,?,?,?)",
        (user_id, username, action, target_type, target_id, summary, detail),
    )


# ── 权限检查 ──

# ── CSV 导出 ──

def csv_response(handler, rows, columns, filename="export.csv"):
    """将 rows（dict 列表）导出为 CSV 响应

    参数:
        handler: BaseHTTPRequestHandler
        rows: dict 列表
        columns: [(字段名, 列标题), ...] 列表，控制列顺序和映射
        filename: 下载文件名（仅用于 Content-Disposition 提示）
    """
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([col[1] for col in columns])  # 表头
    for row in rows:
        writer.writerow([str(row.get(col[0], "") or "") for col in columns])

    body = output.getvalue().encode("utf-8-sig")  # BOM 让 Excel 正确识别中文
    handler.send_response(200)
    handler.send_header("Content-Type", "text/csv; charset=utf-8")
    # 使用 ASCII 安全文件名；前端 downloadCSV 会覆盖实际下载名
    safe_name = "export.csv"
    handler.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def require_role(token_payload: dict, allowed_roles: list[str]) -> bool:
    """检查角色是否在允许列表中"""
    if not token_payload:
        return False
    role = token_payload.get("role", "")
    if "*" in allowed_roles:
        return True
    return role in allowed_roles
