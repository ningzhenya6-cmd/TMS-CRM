"""聊天问答待审核模块 - 用户 Q&A 自动保存为待审核，管理员审核后入库"""
import json
import os
import sqlite3
import threading
import time
from collections import Counter

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
DB_PATH = os.path.join(DATA_DIR, "knowledge.db")
PENDING_FILE = os.path.join(DATA_DIR, "pending_qa.json")  # kept for migration

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
        CREATE TABLE IF NOT EXISTS pending_qa (
            id TEXT PRIMARY KEY,
            question TEXT NOT NULL DEFAULT '',
            answer TEXT NOT NULL DEFAULT '',
            sources TEXT NOT NULL DEFAULT '[]',
            auto_title TEXT NOT NULL DEFAULT '',
            auto_category TEXT NOT NULL DEFAULT 'user-qa',
            auto_tags TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT ''
        )
    """)
    db.commit()


def _migrate_from_json():
    """Migrate from pending_qa.json to SQLite if data exists."""
    if not os.path.exists(PENDING_FILE):
        return
    db = _get_db()
    count = db.execute("SELECT COUNT(*) FROM pending_qa").fetchone()[0]
    if count > 0:
        return
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, IOError):
        return
    if not entries:
        return
    for e in entries:
        db.execute(
            "INSERT OR REPLACE INTO pending_qa VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                e.get("id", ""),
                e.get("question", ""),
                e.get("answer", ""),
                json.dumps(e.get("sources", []), ensure_ascii=False),
                e.get("auto_title", ""),
                e.get("auto_category", "user-qa"),
                json.dumps(e.get("auto_tags", []), ensure_ascii=False),
                e.get("status", "pending"),
                e.get("created_at", ""),
            ),
        )
    db.commit()
    print(f"[pending_qa] 已从 pending_qa.json 迁移 {len(entries)} 条到 SQLite")


def _load():
    """读取 pending_qa 表，返回列表。表不存在时返回空列表。"""
    _init_db()
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM pending_qa ORDER BY created_at"
        ).fetchall()
        result = []
        for r in rows:
            result.append(
                {
                    "id": r["id"],
                    "question": r["question"],
                    "answer": r["answer"],
                    "sources": json.loads(r["sources"]),
                    "auto_title": r["auto_title"],
                    "auto_category": r["auto_category"],
                    "auto_tags": json.loads(r["auto_tags"]),
                    "status": r["status"],
                    "created_at": r["created_at"],
                }
            )
        return result
    except Exception:
        return []


def auto_categorize(question, sources):
    """从 sources 中自动推断 category 和 tags。
    返回 dict: {auto_title, auto_category, auto_tags}
    """
    title = (question or "").strip()[:80]
    if len(question or "") > 80:
        title += "..."

    categories = []
    tags = []
    for s in sources or []:
        if s.get("type") == "kb":
            cat = s.get("category", "")
            if cat:
                categories.append(cat)
            for t in s.get("tags") or []:
                if t:
                    tags.append(t)

    if categories:
        auto_category = Counter(categories).most_common(1)[0][0]
    else:
        auto_category = "user-qa"

    # Deduplicate tags while preserving order
    seen = set()
    auto_tags = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            auto_tags.append(t)

    return {
        "auto_title": title,
        "auto_category": auto_category,
        "auto_tags": auto_tags,
    }


def _auto_approve_check(entry):
    """自动审核条件：达标则直接入库，无需人工审核。"""
    answer = entry.get("answer", "")
    sources = entry.get("sources", [])

    # 1. 回答要有实质内容（至少50字）
    if len(answer) < 50:
        return False, "回答过短"

    # 2. 必须有知识库来源（纯网络搜索的不自动入库）
    kb_count = sum(1 for s in sources if s.get("type") == "kb")
    if kb_count == 0:
        return False, "无知识库来源"

    # 3. 回答开头不能有报错/拒绝关键词
    head = answer[:100]
    error_indicators = ["error", "失败", "无法回答", "抱歉，我无法"]
    for kw in error_indicators:
        if kw in head:
            return False, f"含拒绝关键词: {kw}"

    return True, ""


def add_pending(question, answer, sources, auto_approve=True):
    """聊天完成后保存问答对。
    如果 auto_approve=True 且条件达标，直接入库。
    返回 (entry_id, status)，status='approved' 或 'pending'。
    """
    if not question or not answer:
        return None, "skipped"

    meta = auto_categorize(question, sources)
    _init_db()

    entry_id = "pqa-{}-{}".format(int(time.time()), int(time.time() * 1000) % 10000)

    entry = {
        "id": entry_id,
        "question": question,
        "answer": answer,
        "sources": sources or [],
        "auto_title": meta["auto_title"],
        "auto_category": meta["auto_category"],
        "auto_tags": meta["auto_tags"],
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
        "status": "pending",
    }

    # 自动审核逻辑
    if auto_approve:
        ok, reason = _auto_approve_check(entry)
        if ok:
            from knowledge.store import get_store

            store = get_store()
            store.add_entry(
                {
                    "title": meta["auto_title"],
                    "content": answer,
                    "category": meta["auto_category"],
                    "tags": meta["auto_tags"],
                    "related_questions": [question],
                }
            )
            store.save()
            return entry_id, "approved"
        # 不达标则进入人工审核（fall through 到下面的保存）

    # Write to SQLite
    db = _get_db()
    try:
        existing = db.execute("SELECT COUNT(*) FROM pending_qa").fetchone()[0]
        entry["id"] = "pqa-{}-{}".format(int(time.time()), existing)
        db.execute(
            "INSERT INTO pending_qa VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry["id"],
                entry["question"],
                entry["answer"],
                json.dumps(entry["sources"], ensure_ascii=False),
                entry["auto_title"],
                entry["auto_category"],
                json.dumps(entry["auto_tags"], ensure_ascii=False),
                entry["status"],
                entry["created_at"],
            ),
        )
        db.commit()
    except Exception:
        db.rollback()
        return None, "error"
    return entry["id"], "pending"


def list_pending():
    """返回所有待审核条目（status == 'pending'）。"""
    _init_db()
    all_items = _load()
    return [e for e in all_items if e.get("status") == "pending"]


def get_pending(pqa_id):
    """按 id 查询单个待审核条目。"""
    _init_db()
    for e in _load():
        if e["id"] == pqa_id:
            return e
    return None


def approve_pending(pqa_id, edits):
    """批准待审核条目，加入知识库。
    edits: {title, category, tags, content}
    返回 True 成功，False 未找到。
    """
    _init_db()
    db = _get_db()
    row = db.execute(
        "SELECT * FROM pending_qa WHERE id = ?", (pqa_id,)
    ).fetchone()
    if not row:
        return False

    found = {
        "id": row["id"],
        "question": row["question"],
        "answer": row["answer"],
        "sources": json.loads(row["sources"]),
        "auto_title": row["auto_title"],
        "auto_category": row["auto_category"],
        "auto_tags": json.loads(row["auto_tags"]),
    }

    # Build KB entry
    from knowledge.store import get_store

    store = get_store()
    store.add_entry(
        {
            "title": edits.get("title", found.get("auto_title", "")),
            "content": edits.get("content", found.get("answer", "")),
            "category": edits.get("category", found.get("auto_category", "user-qa")),
            "tags": edits.get("tags", found.get("auto_tags", [])),
            "related_questions": [found.get("question", "")],
        }
    )
    store.save()

    # Remove from pending
    db.execute("DELETE FROM pending_qa WHERE id = ?", (pqa_id,))
    db.commit()
    return True


def reject_pending(pqa_id):
    """拒绝待审核条目，永久删除。"""
    _init_db()
    db = _get_db()
    cursor = db.execute("DELETE FROM pending_qa WHERE id = ?", (pqa_id,))
    db.commit()
    return cursor.rowcount > 0
