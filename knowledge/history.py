"""对话历史持久化模块 - 按用户保存/加载聊天记录"""
import json
import os
import sqlite3
import threading
import time

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


def _init_db():
    db = _get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            message_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT ''
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_session
        ON chat_messages (session_id, created_at)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_user
        ON chat_sessions (user_id, updated_at)
    """)
    db.commit()


def create_session(user_id):
    """创建一个新的对话会话。返回 session_id。"""
    _init_db()
    db = _get_db()
    session_id = "s-{}-{}".format(user_id[-8:], int(time.time()))
    now = time.strftime("%Y-%m-%d %H:%M")
    db.execute(
        "INSERT INTO chat_sessions (id, user_id, title, message_count, created_at, updated_at) "
        "VALUES (?, ?, '', 0, ?, ?)",
        (session_id, user_id, now, now),
    )
    db.commit()
    return session_id


def add_message(session_id, role, content):
    """添加一条消息到会话。返回 message_id。"""
    _init_db()
    db = _get_db()
    import uuid
    msg_id = "m-{}".format(uuid.uuid4().hex[:16])
    now = time.strftime("%Y-%m-%d %H:%M")
    db.execute(
        "INSERT INTO chat_messages (id, session_id, role, content, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (msg_id, session_id, role, content, now),
    )
    db.execute(
        "UPDATE chat_sessions SET message_count = message_count + 1, updated_at = ? WHERE id = ?",
        (now, session_id),
    )
    db.commit()
    return msg_id


def get_messages(session_id, limit=100):
    """获取会话中的所有消息。"""
    _init_db()
    db = _get_db()
    rows = db.execute(
        "SELECT role, content, created_at FROM chat_messages "
        "WHERE session_id = ? ORDER BY created_at LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def get_sessions(user_id, limit=10):
    """获取用户最近的会话列表。"""
    _init_db()
    db = _get_db()
    rows = db.execute(
        "SELECT id, title, message_count, created_at, updated_at FROM chat_sessions "
        "WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_recent_messages(user_id, max_messages=50):
    """获取用户最近的消息（跨会话）。用于页面刷新后恢复上下文。"""
    _init_db()
    db = _get_db()
    rows = db.execute(
        "SELECT m.role, m.content, m.created_at FROM chat_messages m "
        "JOIN chat_sessions s ON m.session_id = s.id "
        "WHERE s.user_id = ? "
        "ORDER BY m.created_at DESC LIMIT ?",
        (user_id, max_messages),
    ).fetchall()
    # Return in chronological order
    messages = [{"role": r["role"], "content": r["content"]} for r in rows]
    messages.reverse()
    return messages


def get_or_create_current_session(user_id):
    """获取用户最新的会话，如果没有则创建。返回 session dict。"""
    _init_db()
    db = _get_db()
    row = db.execute(
        "SELECT id, message_count FROM chat_sessions "
        "WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if row and row["message_count"] < 200:
        return {"id": row["id"], "message_count": row["message_count"]}
    session_id = create_session(user_id)
    return {"id": session_id, "message_count": 0}


def save_conversation(user_id, messages):
    """保存完整对话（用于聊天完成后）。找最新会话或创建，追加新消息。

    Args:
        user_id: 用户 ID
        messages: [{role, content}, ...] - 当前会话中尚未持久化的消息
    """
    _init_db()
    session = get_or_create_current_session(user_id)
    db = _get_db()

    # Count messages already stored
    count = db.execute(
        "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?",
        (session["id"],),
    ).fetchone()[0]

    # Only store messages beyond what's already saved
    new_messages = messages[count:]
    for msg in new_messages:
        add_message(session["id"], msg.get("role", "user"), msg.get("content", ""))

    # Auto-generate title from first user message if empty
    if session["message_count"] == 0 and new_messages:
        first_user = None
        for m in new_messages:
            if m.get("role") == "user":
                first_user = m.get("content", "")[:30]
                break
        if first_user:
            db.execute(
                "UPDATE chat_sessions SET title = ? WHERE id = ?",
                (first_user, session["id"]),
            )
            db.commit()

    return session["id"]


def admin_get_all_sessions(limit=100, offset=0):
    """Get all chat sessions across all users, with user info."""
    _init_db()
    db = _get_db()
    rows = db.execute("""
        SELECT s.id, s.title, s.message_count, s.created_at, s.updated_at,
               u.name as user_name, u.id as user_id, u.role as user_role
        FROM chat_sessions s
        LEFT JOIN users u ON s.user_id = u.id
        ORDER BY s.updated_at DESC
        LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    return [dict(r) for r in rows]


def admin_get_session_count():
    """Get total number of chat sessions."""
    _init_db()
    db = _get_db()
    row = db.execute("SELECT COUNT(*) as cnt FROM chat_sessions").fetchone()
    return row["cnt"] if row else 0


def delete_session(session_id):
    """Delete a chat session and all its messages."""
    _init_db()
    db = _get_db()
    db.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    db.commit()
    return True
