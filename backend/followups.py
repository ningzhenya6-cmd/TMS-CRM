"""
跟进记录 API — 增强版：强制评级 + 自动排期 + 超期标记
"""
import datetime
from router import get, post, delete
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid
from statemachine import transition_lead
from permissions import can, scope_where


def _calc_next_deadline(rank, signed_at=None):
    """根据评级计算下次跟进截止时间（按工作日）
    A: 次工作日 18:00
    B: 3个工作日内 18:00
    C: 7个工作日内 18:00
    D: 30天后
    """
    base = datetime.datetime.now()
    if signed_at:
        try:
            base = datetime.datetime.strptime(signed_at[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            base = datetime.datetime.now()

    if rank == "A":
        deadline = base + datetime.timedelta(days=1)
        # 确保至少是次工作日
        while deadline.weekday() >= 5:  # 周六日
            deadline += datetime.timedelta(days=1)
    elif rank == "B":
        days_added = 0
        deadline = base
        while days_added < 3:
            deadline += datetime.timedelta(days=1)
            if deadline.weekday() < 5:
                days_added += 1
    elif rank == "C":
        days_added = 0
        deadline = base
        while days_added < 7:
            deadline += datetime.timedelta(days=1)
            if deadline.weekday() < 5:
                days_added += 1
    elif rank == "D":
        deadline = base + datetime.timedelta(days=30)
        while deadline.weekday() >= 5:
            deadline += datetime.timedelta(days=1)
    else:
        return ""

    return deadline.strftime("%Y-%m-%d 18:00")


def _get_next_weekday(base, offset_days):
    """获取 base + offset_days 后的最近工作日"""
    d = base + datetime.timedelta(days=offset_days)
    while d.weekday() >= 5:
        d += datetime.timedelta(days=1)
    return d


@get("/api/followups/plan")
def get_followup_plan(handler, token_payload, qs, body):
    """跟进计划 API — 按角色隔离+排序+分页
    tab=overdue|today|upcoming
    """
    page = int(qs.get("page", [1])[0])
    page_size = int(qs.get("page_size", [20])[0])
    tab = qs.get("tab", ["overdue"])[0]

    role = token_payload["role"]
    user_id = token_payload["sub"]

    scope_clause, scope_params = scope_where("lead", role, user_id, "l")
    today_str = datetime.datetime.now().strftime("%Y-%m-%d 18:00")

    where = [
        "l.next_followup_at IS NOT NULL",
        "l.next_followup_at != ''",
        "l.status NOT IN ('enrolled','closed','lost')",
        "COALESCE(l.followup_paused, 0)=0",
        scope_clause,
    ]
    params = list(scope_params)

    if tab == "overdue":
        where.append("l.next_followup_at < ?")
        params.append(today_str)
        order = "l.next_followup_at ASC"
    elif tab == "today":
        where.append("l.next_followup_at >= ? AND l.next_followup_at < ?")
        params.append(today_str[:10] + " 00:00")
        params.append(today_str[:10] + " 23:59")
        order = "l.next_followup_at ASC"
    elif tab == "upcoming":
        where.append("l.next_followup_at > ?")
        params.append(today_str)
        order = "l.next_followup_at ASC"
    else:
        order = "l.next_followup_at ASC"

    where_sql = " AND ".join(where)

    total = query_one(
        f"SELECT COUNT(*) as cnt FROM leads l WHERE {where_sql}", tuple(params)
    )["cnt"]

    offset = (page - 1) * page_size
    rows = query(
        f"""SELECT l.id, l.name, l.phone, l.lead_rank, l.status,
                   l.next_followup_at, l.last_followup_at,
                   l.assignee_id, l.overdue_count,
                   u.display_name as assignee_name,
                   (SELECT f.content FROM followups f WHERE f.lead_id=l.id ORDER BY f.created_at DESC LIMIT 1) as last_content
            FROM leads l
            LEFT JOIN users u ON l.assignee_id = u.id
            WHERE {where_sql}
            ORDER BY {order}
            LIMIT ? OFFSET ?""",
        tuple(params) + (page_size, offset),
    )

    # 计算 overdue_days
    now = datetime.datetime.now()
    for r in rows:
        if r["next_followup_at"]:
            try:
                nd = datetime.datetime.strptime(r["next_followup_at"][:19], "%Y-%m-%d %H:%M")
                diff = (now - nd).days
                r["overdue_days"] = diff if diff > 0 else 0
            except (ValueError, TypeError):
                r["overdue_days"] = 0
        else:
            r["overdue_days"] = 0

    ok_response(handler, {"total": total, "page": page, "page_size": page_size, "items": rows})


@get("/api/followups/{lead_id}")
def list_followups(handler, token_payload, qs, body, lead_id=None):
    rows = query(
        """SELECT f.*, u.display_name as creator_name
           FROM followups f LEFT JOIN users u ON f.created_by = u.id
           WHERE f.lead_id=? ORDER BY f.created_at DESC""",
        (int(lead_id),),
    )
    ok_response(handler, rows)


@post("/api/followups")
def create_followup(handler, token_payload, qs, body):
    if not can(token_payload["role"], "lead:edit"):
        error_response(handler, "无权操作", 403)
        return
    lead_id = body.get("lead_id")
    content = (body.get("content") or "").strip()
    if not lead_id or not content:
        error_response(handler, "参数不完整")
        return

    # 强制评级（P0 核心规则）
    followup_rank = body.get("followup_rank", "")
    if followup_rank not in ("A", "B", "C", "D"):
        error_response(handler, "请选择本次跟进评级（A/B/C/D）")
        return

    lead = query_one("SELECT * FROM leads WHERE id=?", (lead_id,))
    if not lead:
        error_response(handler, "线索不存在", 404)
        return

    followup_type = body.get("followup_type", "")
    if followup_type not in ("", "电话沟通", "微信沟通", "到访面谈", "试听反馈", "续费沟通", "其他"):
        followup_type = ""

    # 评级展开字段
    urgency_label = body.get("urgency_label", "") if followup_rank == "A" else ""
    enrollment_timeline = body.get("enrollment_timeline", "") if followup_rank == "B" else ""
    application_stage = body.get("application_stage", "") if followup_rank == "C" else ""

    fid = execute_lastrowid(
        """INSERT INTO followups (lead_id, content, next_action, next_date, created_by, followup_type, followup_rank,
                                  urgency_label, enrollment_timeline, application_stage)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            lead_id, content,
            body.get("next_action", ""),
            body.get("next_date", ""),
            token_payload["sub"],
            followup_type,
            followup_rank,
            urgency_label,
            enrollment_timeline,
            application_stage,
        ),
    )

    # ── 通过状态机推进线索状态 ──
    if lead["status"] in ("pending", "assigned"):
        try:
            transition_lead(lead_id, "following")
        except Exception:
            pass

    # ── 自动计算下次跟进截止时间（P0 核心规则） ──
    # 用户手动填了 next_date 就用它，否则按评级自动算
    next_date = body.get("next_date", "")
    if not next_date:
        next_date = _calc_next_deadline(followup_rank)

    # 更新 leads 的跟进信息
    execute(
        """UPDATE leads SET
           last_followup_at=datetime('now','localtime'),
           next_followup_at=?,
           contact_status=?,
           lead_rank=?
           WHERE id=?""",
        (next_date, body.get("contact_status", ""), followup_rank, lead_id),
    )

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "create", "followup", fid, f"跟进线索: {lead['name']} (评级:{followup_rank})")

    followup = query_one(
        "SELECT f.*, u.display_name as creator_name FROM followups f LEFT JOIN users u ON f.created_by=u.id WHERE f.id=?",
        (fid,),
    )
    ok_response(handler, followup, 201)


@delete("/api/followups/{followup_id}")
def delete_followup(handler, token_payload, qs, body, followup_id=None):
    if not can(token_payload["role"], "lead:edit"):
        error_response(handler, "无权操作", 403)
        return
    fid = int(followup_id)
    f = query_one("SELECT id FROM followups WHERE id=?", (fid,))
    if not f:
        error_response(handler, "跟进记录不存在", 404)
        return
    execute("DELETE FROM followups WHERE id=?", (fid,))
    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "delete", "followup", fid, "删除跟进记录")
    ok_response(handler, {"message": "已删除"})


@get("/api/overdue/stats")
def get_overdue_stats(handler, token_payload, qs, body):
    """超期统计 — 供管理看板使用"""
    overdue_count = query_one(
        """SELECT COUNT(*) as cnt FROM leads
           WHERE next_followup_at IS NOT NULL
             AND next_followup_at != ''
             AND next_followup_at < datetime('now','localtime')
             AND status NOT IN ('enrolled','closed','lost')
             AND COALESCE(followup_paused, 0)=0"""
    )["cnt"]

    by_consultant = query(
        """SELECT u.id, u.display_name,
                  COUNT(*) as overdue_cnt
           FROM leads l
           JOIN users u ON l.assignee_id = u.id
           WHERE l.next_followup_at IS NOT NULL
             AND l.next_followup_at != ''
             AND l.next_followup_at < datetime('now','localtime')
             AND l.status NOT IN ('enrolled','closed','lost')
             AND COALESCE(l.followup_paused, 0)=0
           GROUP BY u.id
           ORDER BY overdue_cnt DESC"""
    )

    ok_response(handler, {"total_overdue": overdue_count, "by_consultant": by_consultant})

