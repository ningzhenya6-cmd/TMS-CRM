"""
数据库模块 — sqlite3 封装
使用 WAL 模式、外键约束、行工厂返回 dict
"""
import sqlite3
import os
import threading

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "tms.db")

_local = threading.local()


def get_conn() -> sqlite3.Connection:
    """每个线程一个连接（线程本地）"""
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(DB_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        _local.conn = conn
    return _local.conn


def query(sql: str, params: tuple = ()) -> list[dict]:
    """查询返回 dict 列表"""
    conn = get_conn()
    cur = conn.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def query_one(sql: str, params: tuple = ()):
    """查询单条，返回 dict 或 None"""
    conn = get_conn()
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


def execute(sql: str, params: tuple = ()) -> int:
    """执行写入，返回影响行数"""
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.rowcount


def execute_lastrowid(sql: str, params: tuple = ()) -> int:
    """执行写入，返回最后插入的 rowid"""
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid


def init_db():
    """初始化数据库表结构"""
    conn = get_conn()
    conn.executescript("""
    -- 用户表
    CREATE TABLE IF NOT EXISTS users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        username    TEXT NOT NULL UNIQUE,
        password    TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        role        TEXT NOT NULL DEFAULT 'cs',
        phone       TEXT DEFAULT '',
        active      INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    -- 线索表
    CREATE TABLE IF NOT EXISTS leads (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        phone           TEXT DEFAULT '',
        wechat          TEXT DEFAULT '',
        source          TEXT DEFAULT '其他',
        country         TEXT DEFAULT '',
        grade           TEXT DEFAULT '',
        status          TEXT NOT NULL DEFAULT 'pending',
        assignee_id     INTEGER REFERENCES users(id),
        creator_id      INTEGER NOT NULL REFERENCES users(id),
        remark          TEXT DEFAULT '',
        last_followup_at TEXT,
        next_followup_at TEXT,
        created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
    CREATE INDEX IF NOT EXISTS idx_leads_assignee ON leads(assignee_id);

    -- 跟进记录表
    CREATE TABLE IF NOT EXISTS followups (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id     INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        content     TEXT NOT NULL DEFAULT '',
        next_action TEXT DEFAULT '',
        next_date   TEXT DEFAULT '',
        created_by  INTEGER NOT NULL REFERENCES users(id),
        created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_followups_lead ON followups(lead_id);

    -- 合同表
    CREATE TABLE IF NOT EXISTS contracts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id     INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        contract_no TEXT DEFAULT '',
        total_amount REAL DEFAULT 0,
        status      TEXT NOT NULL DEFAULT 'active',
        signed_at   TEXT DEFAULT '',
        remark      TEXT DEFAULT '',
        created_by  INTEGER NOT NULL REFERENCES users(id),
        created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    -- 课时包表
    CREATE TABLE IF NOT EXISTS packages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_id     INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
        name            TEXT DEFAULT '',
        total_hours     REAL DEFAULT 0,
        used_hours      REAL DEFAULT 0,
        price_per_hour  REAL DEFAULT 0,
        status          TEXT NOT NULL DEFAULT 'active',
        remark          TEXT DEFAULT '',
        created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    -- 排课表
    CREATE TABLE IF NOT EXISTS schedules (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id         INTEGER NOT NULL REFERENCES leads(id),
        tutor_id        INTEGER REFERENCES users(id),
        subject         TEXT DEFAULT '',
        start_time      TEXT NOT NULL,
        end_time        TEXT NOT NULL,
        duration_minutes INTEGER DEFAULT 0,
        status          TEXT NOT NULL DEFAULT 'pending',
        remark          TEXT DEFAULT '',
        created_by      INTEGER NOT NULL REFERENCES users(id),
        created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );

    -- 操作日志表
    CREATE TABLE IF NOT EXISTS operation_logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER REFERENCES users(id),
        username    TEXT DEFAULT '',
        action      TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id   INTEGER,
        summary     TEXT DEFAULT '',
        detail      TEXT DEFAULT '',
        created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_oplog_created ON operation_logs(created_at);
    """)
    conn.commit()
