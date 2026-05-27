"""用户管理模块 - 用户注册/登录/角色/限额管理"""
import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
DB_PATH = os.path.join(DATA_DIR, "knowledge.db")

os.makedirs(DATA_DIR, exist_ok=True)

_local = threading.local()


def _get_db():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


def _hash_password(password):
    """SHA256 哈希密码（stdlib only，后续可升级为 bcrypt）"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _init_db():
    db = _get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            password TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'student',
            status TEXT NOT NULL DEFAULT 'active',
            daily_limit INTEGER NOT NULL DEFAULT 50,
            source TEXT NOT NULL DEFAULT 'web',
            created_at TEXT NOT NULL DEFAULT '',
            last_active TEXT NOT NULL DEFAULT '',
            total_questions INTEGER NOT NULL DEFAULT 0,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
    """)
    # 兼容旧表（没有 password/status/daily_limit 字段的加回去）
    try:
        db.execute("ALTER TABLE users ADD COLUMN password TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    except Exception:
        pass
    try:
        db.execute("ALTER TABLE users ADD COLUMN daily_limit INTEGER NOT NULL DEFAULT 50")
    except Exception:
        pass
    db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT '',
            expires_at TEXT NOT NULL DEFAULT ''
        )
    """)
    # 每日使用量统计
    db.execute("""
        CREATE TABLE IF NOT EXISTS daily_usage (
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )
    """)
    db.commit()


def create_user(name="", role="student", source="web"):
    """创建一个新用户。返回 user dict。"""
    _init_db()
    db = _get_db()
    user_id = "u-{}".format(uuid.uuid4().hex[:12])
    now = time.strftime("%Y-%m-%d %H:%M")
    db.execute(
        "INSERT INTO users (id, name, role, source, created_at, last_active, total_questions, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, 0, '{}')",
        (user_id, name, role, source, now, now),
    )
    db.commit()
    return {"id": user_id, "name": name, "role": role, "source": source, "created_at": now}


def get_user(user_id):
    """按 user_id 查询用户。"""
    _init_db()
    db = _get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return None
    return dict(row)


def update_user(user_id, updates):
    """更新用户信息（name, role 等）。"""
    _init_db()
    db = _get_db()
    allowed = {"name", "role", "metadata"}
    for key, value in updates.items():
        if key in allowed:
            db.execute("UPDATE users SET {} = ? WHERE id = ?".format(key), (value, user_id))
    db.execute(
        "UPDATE users SET last_active = ? WHERE id = ?",
        (time.strftime("%Y-%m-%d %H:%M"), user_id),
    )
    db.commit()
    return get_user(user_id)


def increment_questions(user_id):
    """用户提问数 +1。"""
    _init_db()
    db = _get_db()
    db.execute(
        "UPDATE users SET total_questions = total_questions + 1, last_active = ? WHERE id = ?",
        (time.strftime("%Y-%m-%d %H:%M"), user_id),
    )
    db.commit()


def create_session(user_id):
    """创建会话令牌。返回 token。"""
    _init_db()
    db = _get_db()
    token = "sess-{}".format(uuid.uuid4().hex[:24])
    now = time.strftime("%Y-%m-%d %H:%M")
    # Session expires in 30 days
    db.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now, now),
    )
    db.commit()
    return token


def get_session(token):
    """按 token 查找会话。返回 user dict 或 None。"""
    _init_db()
    db = _get_db()
    row = db.execute(
        "SELECT user_id FROM sessions WHERE token = ?", (token,)
    ).fetchone()
    if not row:
        return None
    return get_user(row["user_id"])


def get_or_create_user(token=None):
    """获取已有用户或创建新用户。
    如果提供有效的 token，返回对应用户。
    否则创建新用户和新 token。
    返回 (user, token)。
    """
    if token:
        user = get_session(token)
        if user:
            return user, token
    # Create new user + session
    user = create_user()
    new_token = create_session(user["id"])
    return user, new_token


# ===== 注册 / 登录 =====

def register_user(name, password, source="web"):
    """注册新用户。name 唯一。返回 {user, token} 或 {error}。"""
    _init_db()
    db = _get_db()
    # 检查重名
    existing = db.execute("SELECT id FROM users WHERE name = ?", (name,)).fetchone()
    if existing:
        return {"error": "该用户名已被注册"}
    user_id = "u-{}".format(uuid.uuid4().hex[:12])
    now = time.strftime("%Y-%m-%d %H:%M")
    pwd_hash = _hash_password(password)
    db.execute(
        "INSERT INTO users (id, name, password, role, status, daily_limit, source, created_at, last_active, total_questions, metadata) "
        "VALUES (?, ?, ?, 'student', 'pending', 10, ?, ?, ?, 0, '{}')",
        (user_id, name, pwd_hash, source, now, now),
    )
    db.commit()
    token = create_session(user_id)
    return {"user": {"id": user_id, "name": name, "role": "student", "status": "pending"}, "token": token}


def login_user(name, password):
    """用户名+密码登录。返回 {user, token} 或 {error}。"""
    _init_db()
    db = _get_db()
    pwd_hash = _hash_password(password)
    row = db.execute(
        "SELECT id, name, role, status, daily_limit, total_questions, created_at FROM users WHERE name = ? AND password = ?",
        (name, pwd_hash),
    ).fetchone()
    if not row:
        return {"error": "用户名或密码错误"}
    user = dict(row)
    # 更新活跃时间
    now = time.strftime("%Y-%m-%d %H:%M")
    db.execute("UPDATE users SET last_active = ? WHERE id = ?", (now, user["id"]))
    db.commit()
    token = create_session(user["id"])
    return {"user": user, "token": token}


def get_user_by_name(name):
    """按用户名查用户。"""
    _init_db()
    db = _get_db()
    row = db.execute(
        "SELECT id, name, role, status, daily_limit, total_questions, created_at FROM users WHERE name = ?",
        (name,),
    ).fetchone()
    return dict(row) if row else None


def approve_user(user_id, daily_limit=50):
    """管理员审核通过用户。"""
    _init_db()
    db = _get_db()
    db.execute(
        "UPDATE users SET status = 'active', daily_limit = ? WHERE id = ?",
        (daily_limit, user_id),
    )
    db.commit()


def set_user_status(user_id, status, daily_limit=None):
    """设置用户状态: active / disabled / pending"""
    _init_db()
    db = _get_db()
    if daily_limit is not None:
        db.execute("UPDATE users SET status = ?, daily_limit = ? WHERE id = ?", (status, daily_limit, user_id))
    else:
        db.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
    db.commit()


# ===== 每日限额 =====

def check_daily_limit(user_id):
    """检查用户今天是否已达上限。返回 {allowed, used, limit}。"""
    _init_db()
    db = _get_db()
    today = time.strftime("%Y-%m-%d")
    row = db.execute(
        "SELECT count FROM daily_usage WHERE user_id = ? AND date = ?",
        (user_id, today),
    ).fetchone()
    used = row["count"] if row else 0
    # 查询用户限额
    user = get_user(user_id)
    limit = user.get("daily_limit", 50) if user else 50
    return {"allowed": used < limit, "used": used, "limit": limit}


def increment_daily_usage(user_id):
    """用户提问数+1（每日计数）。"""
    _init_db()
    db = _get_db()
    today = time.strftime("%Y-%m-%d")
    db.execute("""
        INSERT INTO daily_usage (user_id, date, count) VALUES (?, ?, 1)
        ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1
    """, (user_id, today))
    db.commit()


def get_all_users():
    _init_db()
    db = _get_db()
    rows = db.execute("SELECT * FROM users ORDER BY last_active DESC").fetchall()
    return [dict(r) for r in rows]


def get_pending_users():
    """获取待审核用户列表。"""
    _init_db()
    db = _get_db()
    rows = db.execute("SELECT id, name, role, status, created_at FROM users WHERE status = 'pending' ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_stats():
    _init_db()
    db = _get_db()
    total = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    by_role = {}
    for row in db.execute("SELECT role, COUNT(*) as cnt FROM users GROUP BY role"):
        by_role[row["role"]] = row["cnt"]
    by_status = {}
    for row in db.execute("SELECT status, COUNT(*) as cnt FROM users GROUP BY status"):
        by_status[row["status"]] = row["cnt"]
    return {
        "total_users": total,
        "by_role": by_role,
        "by_status": by_status,
    }
