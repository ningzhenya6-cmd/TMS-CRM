"""Query logging and hot questions ranking - track what users ask."""
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
        CREATE TABLE IF NOT EXISTS query_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            kb_count INTEGER NOT NULL DEFAULT 0,
            web_search INTEGER NOT NULL DEFAULT 0,
            user_token TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_query_log_created
        ON query_log (created_at)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_query_log_question
        ON query_log (question)
    """)
    db.commit()


def log_query(question, kb_count=0, web_search=False, user_token=''):
    """Log a user query for analytics.

    Args:
        question: The user's question text
        kb_count: Number of knowledge base results found
        web_search: Whether web search was triggered
        user_token: User identifier token
    """
    _init_db()
    db = _get_db()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO query_log (question, kb_count, web_search, user_token, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (question.strip()[:500], kb_count, 1 if web_search else 0, user_token, now),
    )
    db.commit()


def get_hot_queries(limit=20, days=7):
    """Get most frequently asked questions in recent N days.

    Returns list of {question, count, last_asked, avg_kb_count}
    """
    _init_db()
    db = _get_db()
    cutoff = time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.localtime(time.time() - days * 86400)
    )
    rows = db.execute("""
        SELECT question, COUNT(*) as cnt,
               MAX(created_at) as last_asked,
               ROUND(AVG(kb_count), 1) as avg_kb_count,
               SUM(web_search) as web_count
        FROM query_log
        WHERE created_at >= ?
        GROUP BY question
        ORDER BY cnt DESC
        LIMIT ?
    """, (cutoff, limit)).fetchall()
    return [{
        "question": r["question"],
        "count": r["cnt"],
        "last_asked": r["last_asked"],
        "avg_kb_count": r["avg_kb_count"],
        "web_count": r["web_count"],
    } for r in rows]


def get_query_stats(days=7):
    """Get aggregate query statistics for recent N days."""
    _init_db()
    db = _get_db()
    cutoff = time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.localtime(time.time() - days * 86400)
    )
    total = db.execute(
        "SELECT COUNT(*) as cnt FROM query_log WHERE created_at >= ?",
        (cutoff,)
    ).fetchone()["cnt"]

    unique_users = db.execute(
        "SELECT COUNT(DISTINCT user_token) as cnt FROM query_log "
        "WHERE created_at >= ? AND user_token != ''",
        (cutoff,)
    ).fetchone()["cnt"]

    zero_kb = db.execute(
        "SELECT COUNT(*) as cnt FROM query_log "
        "WHERE created_at >= ? AND kb_count = 0",
        (cutoff,)
    ).fetchone()["cnt"]

    web_search = db.execute(
        "SELECT COUNT(*) as cnt FROM query_log "
        "WHERE created_at >= ? AND web_search = 1",
        (cutoff,)
    ).fetchone()["cnt"]

    return {
        "total_queries": total,
        "unique_users": unique_users,
        "zero_kb_queries": zero_kb,
        "web_search_count": web_search,
        "zero_kb_rate": round(zero_kb / total, 3) if total else 0,
    }


def get_zero_kb_queries(limit=50):
    """Get queries that found no KB results (knowledge gaps)."""
    _init_db()
    db = _get_db()
    rows = db.execute("""
        SELECT question, COUNT(*) as cnt,
               MAX(created_at) as last_asked,
               MIN(created_at) as first_asked
        FROM query_log
        WHERE kb_count = 0
        GROUP BY question
        ORDER BY cnt DESC, MAX(created_at) DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [{
        "question": r["question"],
        "count": r["cnt"],
        "last_asked": r["last_asked"],
        "first_asked": r["first_asked"],
    } for r in rows]
