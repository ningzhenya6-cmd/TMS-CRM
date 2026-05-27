"""用户反馈模块 - AI 回答点赞/点踩，管理员查看低分回答。"""
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


def _init_db():
    db = _get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            question TEXT NOT NULL,
            answer_preview TEXT NOT NULL DEFAULT '',
            vote TEXT NOT NULL,
            user_token TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT ''
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_message_id ON feedback(message_id)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_vote ON feedback(vote)
    """)
    db.commit()


def submit_vote(message_id, question, answer_preview, vote, user_token=""):
    """Submit or toggle a vote.

    If message_id already exists with the same vote, delete it (toggle off).
    If message_id already exists with a different vote, update it (switch).
    Otherwise, insert a new vote.
    """
    _init_db()
    db = _get_db()

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    existing = db.execute(
        "SELECT id, vote FROM feedback WHERE message_id = ?", (message_id,)
    ).fetchone()

    if existing:
        if existing["vote"] == vote:
            # Same vote → toggle off (delete)
            db.execute("DELETE FROM feedback WHERE id = ?", (existing["id"],))
            db.commit()
            return {"action": "removed", "previous_vote": vote}
        else:
            # Different vote → switch
            db.execute(
                "UPDATE feedback SET vote = ?, created_at = ? WHERE id = ?",
                (vote, now, existing["id"]),
            )
            db.commit()
            return {"action": "switched", "previous_vote": existing["vote"], "new_vote": vote}

    # New vote
    fid = uuid.uuid4().hex[:16]
    db.execute(
        "INSERT INTO feedback (id, message_id, question, answer_preview, vote, user_token, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (fid, message_id, question, answer_preview[:500], vote, user_token, now),
    )
    db.commit()
    return {"action": "submitted", "vote": vote}


TOPIC_KEYWORDS = {
    "签证": ["签证", "visa", "f-1", "tier", "study permit", "学签"],
    "选课": ["选课", "课", "课程", "major", "专业选择"],
    "GPA/学术": ["gpa", "成绩", "挂科", "学术", "考试", "论文"],
    "升学/申请": ["申请", "申", "admission", "录取", "offer", "升学"],
    "费用/奖学金": ["学费", "tuition", "奖学金", "钱", "费用", "budget"],
    "实习/工作": ["实习", "工作", "job", "intern", "opt", "cpt", "h1b"],
    "海外生活": ["生活", "住", "租", "医保", "保险", "银行卡"],
    "语言考试": ["托福", "雅思", "toefl", "ielts", "gre", "gmat", "语言"],
}


def _extract_topic(question):
    """Extract topic from question text using keyword matching."""
    q = question.lower()
    for topic, kws in TOPIC_KEYWORDS.items():
        for kw in kws:
            if kw in q:
                return topic
    return "其他"


def list_feedback(only_downvoted=False):
    """List feedback entries, newest first."""
    _init_db()
    db = _get_db()
    if only_downvoted:
        rows = db.execute(
            "SELECT * FROM feedback WHERE vote = 'down' ORDER BY created_at DESC"
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM feedback ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats():
    """Return feedback statistics."""
    _init_db()
    db = _get_db()
    total = db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    up_count = db.execute("SELECT COUNT(*) FROM feedback WHERE vote = 'up'").fetchone()[0]
    down_count = db.execute("SELECT COUNT(*) FROM feedback WHERE vote = 'down'").fetchone()[0]
    down_ratio = round(down_count / total, 3) if total > 0 else 0.0
    return {
        "total": total,
        "up_count": up_count,
        "down_count": down_count,
        "down_ratio": down_ratio,
    }


def get_quality_analysis():
    """Return quality analysis grouped by topic for admin dashboard."""
    _init_db()
    db = _get_db()
    from collections import Counter

    # Get all feedback entries
    all_rows = db.execute(
        "SELECT question, vote FROM feedback ORDER BY created_at DESC"
    ).fetchall()

    # Topic breakdown
    topic_up = Counter()
    topic_down = Counter()
    topic_total = Counter()

    for r in all_rows:
        topic = _extract_topic(r["question"])
        topic_total[topic] += 1
        if r["vote"] == "up":
            topic_up[topic] += 1
        else:
            topic_down[topic] += 1

    by_topic = []
    for topic in sorted(topic_total.keys()):
        total = topic_total[topic]
        down = topic_down[topic]
        by_topic.append({
            "topic": topic,
            "total": total,
            "downvotes": down,
            "down_rate": round(down / total, 2) if total > 0 else 0,
        })
    by_topic.sort(key=lambda x: -x["down_rate"])

    # Last 20 downvoted entries
    recent_bad = db.execute(
        "SELECT id, question, answer_preview, created_at FROM feedback "
        "WHERE vote = 'down' ORDER BY created_at DESC LIMIT 20"
    ).fetchall()

    recent_downvoted = [
        {
            "id": r["id"],
            "question": r["question"][:120],
            "answer_preview": r["answer_preview"][:300],
            "created_at": r["created_at"],
        }
        for r in recent_bad
    ]

    total = len(all_rows)
    down_count = sum(topic_down.values())
    return {
        "summary": {
            "total_feedback": total,
            "total_downvoted": down_count,
            "downvote_rate": round(down_count / total, 3) if total > 0 else 0,
        },
        "by_topic": by_topic,
        "recent_downvoted": recent_downvoted,
    }
