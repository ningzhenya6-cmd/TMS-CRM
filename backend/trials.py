"""
试听管理 API — 排试听 → ClassIn 链接 → 试听反馈 → 转化追踪
完全独立模块，不影响现有 schedules/leads 逻辑
"""
from router import get, post, put
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid
from statemachine import transition_lead
from permissions import can

# ── 安全迁移：给 schedules 表追加试听相关字段 ──
_added_columns = False


def _ensure_columns():
    global _added_columns
    if _added_columns:
        return
    for col, ddl in [
        ("schedule_type", "ALTER TABLE schedules ADD COLUMN schedule_type TEXT DEFAULT 'regular'"),
        ("classin_link", "ALTER TABLE schedules ADD COLUMN classin_link TEXT DEFAULT ''"),
        ("trial_feedback", "ALTER TABLE schedules ADD COLUMN trial_feedback TEXT DEFAULT ''"),
        ("trial_feedback_at", "ALTER TABLE schedules ADD COLUMN trial_feedback_at TEXT DEFAULT ''"),
        ("trial_followup_action", "ALTER TABLE schedules ADD COLUMN trial_followup_action TEXT DEFAULT ''"),
    ]:
        try:
            execute(ddl)
        except Exception:
            pass  # 字段已存在
    _added_columns = True


# ── 查试听列表 ──

@get("/api/trials")
def list_trials(handler, token_payload, qs, body):
    _ensure_columns()
    page = int(qs.get("page", [1])[0])
    page_size = int(qs.get("page_size", [50])[0])
    status = qs.get("status", [None])[0]     # 排课状态
    fb_status = qs.get("fb", [None])[0]       # feedback: pending/done
    date_from = qs.get("date_from", [None])[0]
    date_to = qs.get("date_to", [None])[0]
    tutor_id = qs.get("tutor_id", [None])[0]
    lead_id = qs.get("lead_id", [None])[0]

    role = token_payload["role"]
    user_id = token_payload["sub"]

    where = ["s.schedule_type='trial'"]
    params = []

    if role == "tutor":
        where.append("s.tutor_id=?")
        params.append(user_id)
    elif role in ("cs", "consultant"):
        # 顾问看到自己线索的试听
        where.append("l.assignee_id=?")
        params.append(user_id)

    if status:
        where.append("s.status=?")
        params.append(status)
    if fb_status == "pending":
        where.append("(s.trial_feedback IS NULL OR s.trial_feedback = '')")
    elif fb_status == "done":
        where.append("(s.trial_feedback IS NOT NULL AND s.trial_feedback != '')")
    if date_from:
        where.append("s.start_time >= ?")
        params.append(date_from)
    if date_to:
        where.append("s.start_time <= ?")
        params.append(date_to)
    if tutor_id:
        where.append("s.tutor_id=?")
        params.append(int(tutor_id))
    if lead_id:
        where.append("s.lead_id=?")
        params.append(int(lead_id))

    where_sql = " AND ".join(where)

    total = query_one(
        f"SELECT COUNT(*) as cnt FROM schedules s LEFT JOIN leads l ON s.lead_id=l.id WHERE {where_sql}",
        tuple(params),
    )["cnt"]

    offset = (page - 1) * page_size
    rows = query(
        f"""SELECT s.*, l.name as lead_name, l.phone as lead_phone, l.status as lead_status,
                   l.assignee_id, u_a.display_name as assignee_name,
                   u.display_name as tutor_name
            FROM schedules s
            LEFT JOIN leads l ON s.lead_id = l.id
            LEFT JOIN users u ON s.tutor_id = u.id
            LEFT JOIN users u_a ON l.assignee_id = u_a.id
            WHERE {where_sql}
            ORDER BY s.start_time DESC
            LIMIT ? OFFSET ?""",
        tuple(params) + (page_size, offset),
    )

    ok_response(handler, {"total": total, "items": rows, "page": page, "page_size": page_size})


# ── 安排试听（班主任创建 type='trial' 的排课）──

@post("/api/trials")
def create_trial(handler, token_payload, qs, body):
    _ensure_columns()
    if not can(token_payload["role"], "trial:manage"):
        error_response(handler, "无权安排试听", 403)
        return
    lead_id = body.get("lead_id")
    tutor_id = body.get("tutor_id")
    start_time = body.get("start_time")
    end_time = body.get("end_time")
    subject = body.get("subject", "试听课")

    if not lead_id or not tutor_id or not start_time or not end_time:
        error_response(handler, "缺少必填参数 (lead_id, tutor_id, start_time, end_time)")
        return

    # 检查线索是否存在且状态允许安排试听
    lead = query_one("SELECT id, name, status FROM leads WHERE id=?", (int(lead_id),))
    if not lead:
        error_response(handler, "线索不存在", 404)
        return

    # 计算时长
    duration = 0
    from datetime import datetime
    fmt = "%Y-%m-%d %H:%M"
    try:
        st = datetime.strptime(start_time[:16], fmt)
        et = datetime.strptime(end_time[:16], fmt)
        duration = int((et - st).total_seconds() // 60)
    except (ValueError, IndexError):
        pass

    classin_link = body.get("classin_link", "")

    sid = execute_lastrowid(
        """INSERT INTO schedules
           (lead_id, tutor_id, subject, start_time, end_time, duration_minutes,
            status, remark, created_by, schedule_type, classin_link)
           VALUES (?,?,?,?,?,?,?,?,?,'trial',?)""",
        (
            int(lead_id), int(tutor_id), subject,
            start_time, end_time, duration,
            body.get("status", "pending"),
            body.get("remark", ""),
            token_payload["sub"],
            classin_link,
        ),
    )

    # 通过状态机推进线索状态到"试听中"
    if lead["status"] in ("following", "assigned"):
        try:
            transition_lead(int(lead_id), "trial")
        except Exception:
            pass

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "create", "trial", sid, f"安排试听: {lead['name']}")

    s = query_one("SELECT * FROM schedules WHERE id=?", (sid,))
    ok_response(handler, s, 201)


# ── 更新试听（时间、链接、老师等）──

@put("/api/trials/{trial_id}")
def update_trial(handler, token_payload, qs, body, trial_id=None):
    _ensure_columns()
    if not can(token_payload["role"], "trial:manage"):
        error_response(handler, "无权操作", 403)
        return
    tid = int(trial_id)
    s = query_one("SELECT * FROM schedules WHERE id=? AND schedule_type='trial'", (tid,))
    if not s:
        error_response(handler, "试听不存在", 404)
        return

    allowed = ["tutor_id", "subject", "start_time", "end_time", "status",
               "remark", "classin_link"]
    updates = []
    params = []
    for field in allowed:
        if field in body:
            updates.append(f"{field}=?")
            params.append(body[field])

    # 重新计算时长
    if "start_time" in body and "end_time" in body:
        from datetime import datetime
        try:
            st = datetime.strptime(body["start_time"][:16], "%Y-%m-%d %H:%M")
            et = datetime.strptime(body["end_time"][:16], "%Y-%m-%d %H:%M")
            updates.append("duration_minutes=?")
            params.append(int((et - st).total_seconds() // 60))
        except (ValueError, IndexError):
            pass

    if not updates:
        error_response(handler, "没有需要更新的字段")
        return

    params.append(tid)
    execute(f"UPDATE schedules SET {','.join(updates)} WHERE id=?", tuple(params))

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "update", "trial", tid, "更新试听安排")

    updated = query_one("SELECT * FROM schedules WHERE id=?", (tid,))
    ok_response(handler, updated)


# ── 提交试听反馈（顾问填写）──

@post("/api/trials/{trial_id}/feedback")
def submit_feedback(handler, token_payload, qs, body, trial_id=None):
    _ensure_columns()
    if not can(token_payload["role"], "trial:feedback"):
        error_response(handler, "无权提交反馈", 403)
        return
    tid = int(trial_id)
    s = query_one(
        """SELECT s.*, l.name as lead_name, l.assignee_id
           FROM schedules s LEFT JOIN leads l ON s.lead_id=l.id
           WHERE s.id=? AND s.schedule_type='trial'""",
        (tid,),
    )
    if not s:
        error_response(handler, "试听不存在", 404)
        return

    feedback = (body.get("feedback") or "").strip()
    if not feedback:
        error_response(handler, "请填写试听反馈")
        return

    lead_status = body.get("lead_status", "following")  # enrolled / following / lost
    if lead_status not in ("enrolled", "following", "lost", "trial"):
        lead_status = "following"

    # 如果标记为流失，要求填写原因
    if lead_status == "lost":
        lost_reason = body.get("lost_reason", "")
        if not lost_reason:
            error_response(handler, "标记流失时请填写流失原因", 400)
            return
        execute("UPDATE leads SET lost_reason=? WHERE id=?", (lost_reason, s["lead_id"]))

    execute(
        """UPDATE schedules SET trial_feedback=?, trial_feedback_at=datetime('now','localtime'),
           trial_followup_action=?, status='completed' WHERE id=?""",
        (feedback, body.get("next_action", ""), tid),
    )

    # 通过状态机更新线索状态
    try:
        transition_lead(s["lead_id"], lead_status)
    except Exception:
        # 如果状态机拒绝，fallback 到直接更新（兼容旧数据）
        execute("UPDATE leads SET status=? WHERE id=?", (lead_status, s["lead_id"]))

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "feedback", "trial", tid,
              f"试听反馈: {s['lead_name']} → {lead_status}")

    ok_response(handler, {"message": "反馈已保存", "lead_status": lead_status})


# ── 试听统计 ──

@get("/api/trials/stats")
def trial_stats(handler, token_payload, qs, body):
    _ensure_columns()
    role = token_payload["role"]
    user_id = token_payload["sub"]

    base_where = "s.schedule_type='trial'"
    params = []

    if role in ("cs", "consultant"):
        base_where += " AND l.assignee_id=?"
        params.append(user_id)

    total = query_one(
        f"SELECT COUNT(*) as cnt FROM schedules s LEFT JOIN leads l ON s.lead_id=l.id WHERE {base_where}",
        tuple(params),
    )["cnt"]

    pending = query_one(
        f"SELECT COUNT(*) as cnt FROM schedules s LEFT JOIN leads l ON s.lead_id=l.id WHERE {base_where} AND s.status='pending'",
        tuple(params),
    )["cnt"]

    completed = query_one(
        f"SELECT COUNT(*) as cnt FROM schedules s LEFT JOIN leads l ON s.lead_id=l.id WHERE {base_where} AND s.status='completed'",
        tuple(params),
    )["cnt"]

    has_feedback = query_one(
        f"SELECT COUNT(*) as cnt FROM schedules s LEFT JOIN leads l ON s.lead_id=l.id WHERE {base_where} AND (s.trial_feedback IS NOT NULL AND s.trial_feedback != '')",
        tuple(params),
    )["cnt"]

    # 试听转化数（feedback 后 lead 变成 enrolled）
    enrolled = query_one(
        f"""SELECT COUNT(*) as cnt FROM schedules s
            LEFT JOIN leads l ON s.lead_id=l.id
            WHERE {base_where} AND s.status='completed'
            AND (s.trial_feedback IS NOT NULL AND s.trial_feedback != '')
            AND l.status='enrolled'""",
        tuple(params),
    )["cnt"]

    this_month = query_one(
        f"""SELECT COUNT(*) as cnt FROM schedules s
            LEFT JOIN leads l ON s.lead_id=l.id
            WHERE {base_where}
            AND s.start_time >= datetime('now','localtime','start of month')""",
        tuple(params),
    )["cnt"]

    ok_response(handler, {
        "total": total,
        "pending": pending,
        "completed": completed,
        "has_feedback": has_feedback,
        "enrolled": enrolled,
        "this_month": this_month,
        "conversion_rate": round((enrolled / has_feedback * 100) if has_feedback > 0 else 0, 1),
    })
