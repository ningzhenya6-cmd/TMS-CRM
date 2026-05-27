"""Daily & Weekly Report Generation - auto-generated analytics for admin dashboard."""
import os
import sqlite3
import threading
import time

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
DB_PATH = os.path.join(DATA_DIR, "knowledge.db")

_local = threading.local()


def _get_db():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


def _today_start():
    """Return timestamp string for start of today."""
    return time.strftime("%Y-%m-%d 00:00:00")


def _n_days_ago(n):
    """Return timestamp string for N days ago."""
    return time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.localtime(time.time() - n * 86400)
    )


def get_daily_report():
    """Generate today's report with key metrics."""
    db = _get_db()
    today = _today_start()

    # Queries today
    queries_today = db.execute(
        "SELECT COUNT(*) as cnt FROM query_log WHERE created_at >= ?",
        (today,)
    ).fetchone()["cnt"]

    # Zero-KB queries today
    zero_kb_today = db.execute(
        "SELECT COUNT(*) as cnt FROM query_log WHERE created_at >= ? AND kb_count = 0",
        (today,)
    ).fetchone()["cnt"]

    # Web searches today
    web_today = db.execute(
        "SELECT COUNT(*) as cnt FROM query_log WHERE created_at >= ? AND web_search = 1",
        (today,)
    ).fetchone()["cnt"]

    # Feedback today (from feedback table)
    fb_today = db.execute(
        "SELECT COUNT(*) as cnt FROM feedback WHERE created_at >= ?",
        (today,)
    ).fetchone()["cnt"]

    fb_down_today = db.execute(
        "SELECT COUNT(*) as cnt FROM feedback WHERE created_at >= ? AND vote = 'down'",
        (today,)
    ).fetchone()["cnt"]

    # Consultations today
    has_consults = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='consultations'"
    ).fetchone()
    con_today = 0
    if has_consults:
        con_today = db.execute(
            "SELECT COUNT(*) as cnt FROM consultations WHERE created_at >= ?",
            (today,)
        ).fetchone()["cnt"]

    # New users today
    has_users = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    users_today = 0
    if has_users:
        users_today = db.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE created_at >= ?",
            (today,)
        ).fetchone()["cnt"]

    # New messages today
    has_msgs = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'"
    ).fetchone()
    msgs_today = 0
    if has_msgs:
        msgs_today = db.execute(
            "SELECT COUNT(*) as cnt FROM chat_messages WHERE created_at >= ?",
            (today,)
        ).fetchone()["cnt"]

    return {
        "date": time.strftime("%Y-%m-%d"),
        "queries": queries_today,
        "zero_kb_queries": zero_kb_today,
        "web_searches": web_today,
        "feedback_total": fb_today,
        "feedback_down": fb_down_today,
        "consultations": con_today,
        "new_users": users_today,
        "new_messages": msgs_today,
        "zero_kb_rate": round(zero_kb_today / queries_today, 3) if queries_today else 0,
    }


def get_weekly_report():
    """Generate 7-day report with daily breakdown and trends."""
    db = _get_db()
    week_ago = _n_days_ago(7)

    # Daily query counts for the last 7 days
    daily_queries = db.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as cnt
        FROM query_log
        WHERE created_at >= ?
        GROUP BY DATE(created_at)
        ORDER BY day
    """, (week_ago,)).fetchall()

    daily_breakdown = []
    for r in daily_queries:
        daily_breakdown.append({
            "date": r["day"],
            "queries": r["cnt"],
        })

    # Ensure all 7 days are present (fill gaps with 0)
    day_map = {d["date"]: d["queries"] for d in daily_breakdown}
    complete_breakdown = []
    for i in range(6, -1, -1):
        d = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
        complete_breakdown.append({
            "date": d,
            "queries": day_map.get(d, 0),
        })

    # Aggregate 7-day stats
    total_queries = sum(d["queries"] for d in complete_breakdown)
    total_zero_kb = db.execute(
        "SELECT COUNT(*) as cnt FROM query_log WHERE created_at >= ? AND kb_count = 0",
        (week_ago,)
    ).fetchone()["cnt"]

    total_feedback = db.execute(
        "SELECT COUNT(*) as cnt FROM feedback WHERE created_at >= ?",
        (week_ago,)
    ).fetchone()["cnt"]

    total_down = db.execute(
        "SELECT COUNT(*) as cnt FROM feedback WHERE created_at >= ? AND vote = 'down'",
        (week_ago,)
    ).fetchone()["cnt"]

    # Hot questions this week
    from knowledge.queries import get_hot_queries
    hot = get_hot_queries(10, 7)

    # Knowledge gaps this week
    from knowledge.queries import get_zero_kb_queries
    gaps = get_zero_kb_queries(20)

    # New users
    has_users = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    users_weekly = 0
    if has_users:
        users_weekly = db.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE created_at >= ?",
            (week_ago,)
        ).fetchone()["cnt"]

    return {
        "period": {
            "from": complete_breakdown[0]["date"],
            "to": complete_breakdown[-1]["date"],
            "days": 7,
        },
        "daily_trend": complete_breakdown,
        "total_queries": total_queries,
        "total_zero_kb": total_zero_kb,
        "total_feedback": total_feedback,
        "total_downvotes": total_down,
        "downvote_rate": round(total_down / total_feedback, 3) if total_feedback else 0,
        "zero_kb_rate": round(total_zero_kb / total_queries, 3) if total_queries else 0,
        "hot_questions": hot,
        "top_gaps": gaps[:5],
        "new_users": users_weekly,
    }
