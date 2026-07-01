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

    CREATE INDEX IF NOT EXISTS idx_leads_coordinator ON leads(coordinator_id);

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
        teacher_id      INTEGER REFERENCES teachers(id),
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

    -- 师资表（独立于用户账号，由教务维护）
    CREATE TABLE IF NOT EXISTS teachers (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        name                TEXT NOT NULL,
        academic_background TEXT DEFAULT '',
        highest_degree      TEXT DEFAULT '',
        subjects            TEXT DEFAULT '',
        teaching_direction  TEXT DEFAULT '',
        tools               TEXT DEFAULT '',
        teaching_style      TEXT DEFAULT '',
        level               TEXT DEFAULT '',
        pay_rate            TEXT DEFAULT '',
        payment_method      TEXT DEFAULT '',
        notes               TEXT DEFAULT '',
        phone               TEXT DEFAULT '',
        active              INTEGER NOT NULL DEFAULT 1,
        created_at          TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at          TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_teachers_name ON teachers(name);
    CREATE INDEX IF NOT EXISTS idx_teachers_direction ON teachers(teaching_direction);
    CREATE INDEX IF NOT EXISTS idx_teachers_level ON teachers(level);

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

    # 安全追加列（已有表不会丢失数据，重复执行忽略错误）
    for ddl in [
        "ALTER TABLE leads ADD COLUMN coordinator_id INTEGER REFERENCES users(id)",
        "ALTER TABLE leads ADD COLUMN coordinator_at TEXT",
        "ALTER TABLE leads ADD COLUMN lost_reason TEXT DEFAULT ''",
        "ALTER TABLE leads ADD COLUMN lead_rank TEXT DEFAULT ''",
        "ALTER TABLE leads ADD COLUMN contact_status TEXT DEFAULT ''",
        "ALTER TABLE contracts ADD COLUMN sign_type TEXT NOT NULL DEFAULT 'new'",
        "ALTER TABLE schedules ADD COLUMN teacher_id INTEGER REFERENCES teachers(id)",
        "ALTER TABLE schedules ADD COLUMN tutoring_form TEXT DEFAULT ''",
        "ALTER TABLE schedules ADD COLUMN actual_duration_minutes INTEGER",
        "ALTER TABLE schedules ADD COLUMN teacher_name TEXT DEFAULT ''",
        "ALTER TABLE followups ADD COLUMN followup_type TEXT DEFAULT ''",
        "ALTER TABLE followups ADD COLUMN followup_rank TEXT DEFAULT ''",
        "ALTER TABLE payment_records ADD COLUMN payment_date TEXT DEFAULT ''",
        "ALTER TABLE contracts ADD COLUMN paid_amount REAL DEFAULT 0",
        "ALTER TABLE consulting_reports ADD COLUMN report_type TEXT NOT NULL DEFAULT 'risk'",
        "ALTER TABLE consulting_reports ADD COLUMN program_url TEXT DEFAULT ''",
        "ALTER TABLE consulting_reports ADD COLUMN program_courses TEXT DEFAULT ''",
        "ALTER TABLE consulting_reports ADD COLUMN target_level TEXT DEFAULT ''",
        "ALTER TABLE payment_records ADD COLUMN hours REAL DEFAULT 0",
        "ALTER TABLE payment_records ADD COLUMN sign_type TEXT NOT NULL DEFAULT 'new'",
        "ALTER TABLE followups ADD COLUMN urgency_label TEXT DEFAULT ''",
        "ALTER TABLE followups ADD COLUMN enrollment_timeline TEXT DEFAULT ''",
        "ALTER TABLE followups ADD COLUMN application_stage TEXT DEFAULT ''",
        "ALTER TABLE leads ADD COLUMN followup_paused INTEGER DEFAULT 0",
        "ALTER TABLE leads ADD COLUMN paused_reason TEXT DEFAULT ''",
        "ALTER TABLE leads ADD COLUMN overdue_count INTEGER DEFAULT 0",
        "ALTER TABLE leads ADD COLUMN last_overdue_at TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN dingtalk_id TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(ddl)
        except Exception:
            pass

    # 付款流水表（收款/退款记录）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payment_records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL REFERENCES contracts(id),
            amount      REAL NOT NULL,
            type        TEXT NOT NULL DEFAULT 'payment',
            method      TEXT DEFAULT '',
            note        TEXT DEFAULT '',
            operator_id INTEGER NOT NULL REFERENCES users(id),
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── 课后反馈表 ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lesson_feedback (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id     INTEGER NOT NULL UNIQUE REFERENCES schedules(id),
            lead_id         INTEGER NOT NULL REFERENCES leads(id),
            classin_link    TEXT DEFAULT '',
            content_covered TEXT DEFAULT '',
            student_performance TEXT DEFAULT '',
            difficulties    TEXT DEFAULT '',
            homework_completion TEXT DEFAULT '',
            teacher_notes   TEXT DEFAULT '',
            next_focus      TEXT DEFAULT '',
            ai_generated    INTEGER DEFAULT 0,
            created_by      INTEGER NOT NULL REFERENCES users(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── 考试成绩表 ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS exam_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id     INTEGER NOT NULL REFERENCES leads(id),
            exam_date   TEXT NOT NULL,
            exam_type   TEXT NOT NULL,
            subject     TEXT DEFAULT '',
            score       REAL,
            total_score REAL,
            notes       TEXT DEFAULT '',
            created_by  INTEGER NOT NULL REFERENCES users(id),
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    # ── 录取结果表 ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admission_results (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id          INTEGER NOT NULL REFERENCES leads(id),
            target_school    TEXT DEFAULT '',
            target_major     TEXT DEFAULT '',
            application_date TEXT DEFAULT '',
            admission_status TEXT DEFAULT 'pending',
            admitted_school  TEXT DEFAULT '',
            admitted_major   TEXT DEFAULT '',
            final_score      TEXT DEFAULT '',
            decision_date    TEXT DEFAULT '',
            notes            TEXT DEFAULT '',
            created_by       INTEGER NOT NULL REFERENCES users(id),
            created_at       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    # -- 学业风险分析报告 --
    conn.execute("""
        CREATE TABLE IF NOT EXISTS consulting_reports (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id         INTEGER NOT NULL REFERENCES leads(id),
            target_country  TEXT NOT NULL DEFAULT '',
            target_school   TEXT NOT NULL DEFAULT '',
            target_major    TEXT NOT NULL DEFAULT '',
            current_school  TEXT DEFAULT '',
            current_grade   TEXT DEFAULT '',
            gpa             TEXT DEFAULT '',
            language_scores TEXT DEFAULT '',
            prerequisite_courses TEXT DEFAULT '',
            additional_info TEXT DEFAULT '',
            report_json     TEXT DEFAULT '',
            risk_level      TEXT DEFAULT 'medium',
            summary         TEXT DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'draft',
            progress        INTEGER DEFAULT 0,
            error_message   TEXT DEFAULT '',
            created_by      INTEGER NOT NULL REFERENCES users(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    # -- 作业上传 --
    conn.execute("""
        CREATE TABLE IF NOT EXISTS homework_uploads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id     INTEGER NOT NULL REFERENCES leads(id),
            file_name   TEXT NOT NULL,
            file_size   INTEGER DEFAULT 0,
            file_path   TEXT NOT NULL,
            uploaded_by INTEGER NOT NULL REFERENCES users(id),
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    # -- 课程数据缓存表（行前准备规划用） --
    conn.execute("""
        CREATE TABLE IF NOT EXISTS curriculum_cache (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            school          TEXT NOT NULL,
            major           TEXT NOT NULL,
            courses_json    TEXT NOT NULL DEFAULT '',
            source_url      TEXT DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_curriculum_cache_school_major
        ON curriculum_cache(school, major)
    """)

    # 额外索引加速常见查询
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_leads_next_followup ON leads(next_followup_at)",
        "CREATE INDEX IF NOT EXISTS idx_schedules_lead_id ON schedules(lead_id)",
        "CREATE INDEX IF NOT EXISTS idx_schedules_teacher_id ON schedules(teacher_id)",
        "CREATE INDEX IF NOT EXISTS idx_schedules_start_time ON schedules(start_time)",
        "CREATE INDEX IF NOT EXISTS idx_contracts_lead_id ON contracts(lead_id)",
        "CREATE INDEX IF NOT EXISTS idx_packages_contract_id ON packages(contract_id)",
        "CREATE INDEX IF NOT EXISTS idx_payment_records_contract ON payment_records(contract_id)",
        "CREATE INDEX IF NOT EXISTS idx_lesson_feedback_lead ON lesson_feedback(lead_id)",
        "CREATE INDEX IF NOT EXISTS idx_lesson_feedback_schedule ON lesson_feedback(schedule_id)",
        "CREATE INDEX IF NOT EXISTS idx_exam_results_lead ON exam_results(lead_id)",
        "CREATE INDEX IF NOT EXISTS idx_admission_results_lead ON admission_results(lead_id)",
        "CREATE INDEX IF NOT EXISTS idx_consulting_reports_lead ON consulting_reports(lead_id)",
    ]:
        try:
            conn.execute(idx)
        except Exception:
            pass

    conn.commit()
