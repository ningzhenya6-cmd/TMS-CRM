"""线索 API — CRUD + 分页 + 搜索 + 筛选 + 批量操作"""
from router import get, post, put, delete
from utils import json_response, error_response, parse_body, ok_response, add_oplog, require_role
from db import query, query_one, execute, execute_lastrowid


@get("/api/leads")
def list_leads(handler, token_payload, qs, body):
    page = int(qs.get("page", [1])[0])
    page_size = int(qs.get("page_size", [15])[0])
    status = qs.get("status", [None])[0]
    source = qs.get("source", [None])[0]
    search = qs.get("search", [None])[0]
    assignee_id = qs.get("assignee_id", [None])[0]

    role = token_payload["role"]
    user_id = token_payload["sub"]

    where = ["1=1"]
    params = []

    # 权限过滤
    if role in ("cs", "consultant"):
        where.append("l.assignee_id=?")
        params.append(user_id)
    elif role == "tutor":
        # tutor 看到与自己相关的排课线索
        where.append("1=0")  # 暂不实现
    elif role in ("coordinator",):
        # coordinator 能看到所有线索
        pass

    if status and status != "all":
        where.append("l.status=?")
        params.append(status)
    if source and source != "all":
        where.append("l.source=?")
        params.append(source)
    if assignee_id:
        where.append("l.assignee_id=?")
        params.append(int(assignee_id))
    if search:
        like = f"%{search}%"
        where.append("(l.name LIKE ? OR l.phone LIKE ? OR l.wechat LIKE ?)")
        params.extend([like, like, like])

    where_sql = " AND ".join(where)

    # 总数
    total = query_one(f"SELECT COUNT(*) as cnt FROM leads l WHERE {where_sql}", tuple(params))["cnt"]

    # 分页查询
    offset = (page - 1) * page_size
    rows = query(
        f"""SELECT l.*, u.display_name as assignee_name
            FROM leads l
            LEFT JOIN users u ON l.assignee_id = u.id
            WHERE {where_sql}
            ORDER BY l.created_at DESC
            LIMIT ? OFFSET ?""",
        tuple(params) + (page_size, offset),
    )

    ok_response(handler, {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": rows,
    })


@get("/api/leads/{lead_id}")
def get_lead(handler, token_payload, qs, body, lead_id=None):
    lead = query_one(
        """SELECT l.*, u.display_name as assignee_name
           FROM leads l LEFT JOIN users u ON l.assignee_id = u.id
           WHERE l.id=?""",
        (int(lead_id),),
    )
    if not lead:
        error_response(handler, "线索不存在", 404)
        return

    # 权限检查
    role = token_payload["role"]
    user_id = token_payload["sub"]
    if role in ("cs", "consultant") and lead["assignee_id"] != user_id:
        error_response(handler, "无权访问此线索", 403)
        return

    # 获取跟进记录
    followups = query(
        """SELECT f.*, u.display_name as creator_name
           FROM followups f LEFT JOIN users u ON f.created_by = u.id
           WHERE f.lead_id=? ORDER BY f.created_at DESC""",
        (int(lead_id),),
    )
    lead["followups"] = followups
    ok_response(handler, lead)


@post("/api/leads")
def create_lead(handler, token_payload, qs, body):
    name = (body.get("name") or "").strip()
    if not name:
        error_response(handler, "姓名不能为空")
        return

    lead_id = execute_lastrowid(
        """INSERT INTO leads (name, phone, wechat, source, country, grade, remark, creator_id, status)
           VALUES (?,?,?,?,?,?,?,?,'pending')""",
        (
            name,
            body.get("phone", ""),
            body.get("wechat", ""),
            body.get("source", "其他"),
            body.get("country", ""),
            body.get("grade", ""),
            body.get("remark", ""),
            token_payload["sub"],
        ),
    )
    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "create", "lead", lead_id, f"创建线索: {name}")
    lead = query_one("SELECT * FROM leads WHERE id=?", (lead_id,))
    ok_response(handler, lead, 201)


@put("/api/leads/{lead_id}")
def update_lead(handler, token_payload, qs, body, lead_id=None):
    lead_id = int(lead_id)
    lead = query_one("SELECT * FROM leads WHERE id=?", (lead_id,))
    if not lead:
        error_response(handler, "线索不存在", 404)
        return

    # 权限
    role = token_payload["role"]
    user_id = token_payload["sub"]
    if role in ("cs", "consultant") and lead["assignee_id"] != user_id:
        error_response(handler, "无权操作", 403)
        return

    allowed_fields = ["name", "phone", "wechat", "source", "country", "grade",
                      "status", "assignee_id", "remark"]
    updates = []
    params = []
    for field in allowed_fields:
        if field in body:
            updates.append(f"{field}=?")
            params.append(body[field])

    if not updates:
        error_response(handler, "没有需要更新的字段")
        return

    params.append(lead_id)
    execute(f"UPDATE leads SET {','.join(updates)} WHERE id=?", tuple(params))
    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "update", "lead", lead_id, f"更新线索: {lead['name']}")

    updated = query_one(
        "SELECT l.*, u.display_name as assignee_name FROM leads l LEFT JOIN users u ON l.assignee_id=u.id WHERE l.id=?",
        (lead_id,),
    )
    ok_response(handler, updated)


@delete("/api/leads/{lead_id}")
def delete_lead(handler, token_payload, qs, body, lead_id=None):
    if not require_role(token_payload, ["admin", "supervisor"]):
        error_response(handler, "无权删除", 403)
        return
    lead_id = int(lead_id)
    lead = query_one("SELECT name FROM leads WHERE id=?", (lead_id,))
    if not lead:
        error_response(handler, "线索不存在", 404)
        return
    execute("DELETE FROM leads WHERE id=?", (lead_id,))
    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "delete", "lead", lead_id, f"删除线索: {lead['name']}")
    ok_response(handler, {"message": "已删除"})


# ── 批量操作 ──

@post("/api/leads/batch/assign")
def batch_assign(handler, token_payload, qs, body):
    if not require_role(token_payload, ["admin", "supervisor"]):
        error_response(handler, "无权分配", 403)
        return
    lead_ids = body.get("lead_ids", [])
    assignee_id = body.get("assignee_id")
    if not lead_ids or not assignee_id:
        error_response(handler, "参数不完整")
        return
    count = 0
    for lid in lead_ids:
        execute("UPDATE leads SET assignee_id=?, status='assigned' WHERE id=?", (assignee_id, lid))
        count += 1
    ok_response(handler, {"updated": count})


@post("/api/leads/batch/status")
def batch_status(handler, token_payload, qs, body):
    lead_ids = body.get("lead_ids", [])
    status = body.get("status")
    if not lead_ids or not status:
        error_response(handler, "参数不完整")
        return
    count = 0
    for lid in lead_ids:
        execute("UPDATE leads SET status=? WHERE id=?", (status, lid))
        count += 1
    ok_response(handler, {"updated": count})
