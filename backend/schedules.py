"""排课管理 API — CRUD + 日期筛选 + 教师筛选"""
from router import get, post, put, delete
from utils import ok_response, error_response, add_oplog, require_role
from db import query, query_one, execute, execute_lastrowid


@get("/api/schedules")
def list_schedules(handler, token_payload, qs, body):
    page = int(qs.get("page", [1])[0])
    page_size = int(qs.get("page_size", [50])[0])
    date_from = qs.get("date_from", [None])[0]
    date_to = qs.get("date_to", [None])[0]
    tutor_id = qs.get("tutor_id", [None])[0]
    status = qs.get("status", [None])[0]
    lead_id = qs.get("lead_id", [None])[0]

    role = token_payload["role"]
    user_id = token_payload["sub"]

    where = ["1=1"]
    params = []

    if role == "tutor":
        where.append("s.tutor_id=?")
        params.append(user_id)
    elif role == "coordinator":
        pass  # 教班主任看所有
    elif role in ("admin", "supervisor"):
        pass

    if date_from:
        where.append("s.start_time >= ?")
        params.append(date_from)
    if date_to:
        where.append("s.start_time <= ?")
        params.append(date_to)
    if tutor_id:
        where.append("s.tutor_id=?")
        params.append(int(tutor_id))
    if status:
        where.append("s.status=?")
        params.append(status)
    if lead_id:
        where.append("s.lead_id=?")
        params.append(int(lead_id))

    where_sql = " AND ".join(where)

    total = query_one(
        f"SELECT COUNT(*) as cnt FROM schedules s WHERE {where_sql}",
        tuple(params),
    )["cnt"]

    offset = (page - 1) * page_size
    rows = query(
        f"""SELECT s.*, l.name as lead_name, u.display_name as tutor_name,
                   cr.display_name as creator_name
            FROM schedules s
            LEFT JOIN leads l ON s.lead_id = l.id
            LEFT JOIN users u ON s.tutor_id = u.id
            LEFT JOIN users cr ON s.created_by = cr.id
            WHERE {where_sql}
            ORDER BY s.start_time ASC
            LIMIT ? OFFSET ?""",
        tuple(params) + (page_size, offset),
    )

    ok_response(handler, {"total": total, "page": page, "page_size": page_size, "items": rows})


@get("/api/schedules/{schedule_id}")
def get_schedule(handler, token_payload, qs, body, schedule_id=None):
    s = query_one(
        """SELECT s.*, l.name as lead_name, u.display_name as tutor_name,
                  cr.display_name as creator_name
           FROM schedules s
           LEFT JOIN leads l ON s.lead_id = l.id
           LEFT JOIN users u ON s.tutor_id = u.id
           LEFT JOIN users cr ON s.created_by = cr.id
           WHERE s.id=?""",
        (int(schedule_id),),
    )
    if not s:
        error_response(handler, "排课不存在", 404)
        return
    ok_response(handler, s)


@post("/api/schedules")
def create_schedule(handler, token_payload, qs, body):
    lead_id = body.get("lead_id")
    start_time = body.get("start_time")
    end_time = body.get("end_time")

    if not lead_id or not start_time or not end_time:
        error_response(handler, "缺少必填参数 (lead_id, start_time, end_time)")
        return

    # 计算时长（分钟）
    duration = 0
    try:
        from datetime import datetime
        fmt = "%Y-%m-%d %H:%M"
        st = datetime.strptime(start_time[:16], fmt)
        et = datetime.strptime(end_time[:16], fmt)
        duration = int((et - st).total_seconds() // 60)
    except (ValueError, IndexError):
        pass

    sid = execute_lastrowid(
        """INSERT INTO schedules (lead_id, tutor_id, subject, start_time, end_time,
           duration_minutes, status, remark, created_by)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            int(lead_id),
            int(body["tutor_id"]) if body.get("tutor_id") else None,
            body.get("subject", ""),
            start_time,
            end_time,
            duration,
            body.get("status", "pending"),
            body.get("remark", ""),
            token_payload["sub"],
        ),
    )

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "create", "schedule", sid, f"创建排课")

    s = query_one("SELECT * FROM schedules WHERE id=?", (sid,))
    ok_response(handler, s, 201)


@put("/api/schedules/{schedule_id}")
def update_schedule(handler, token_payload, qs, body, schedule_id=None):
    sid = int(schedule_id)
    existing = query_one("SELECT * FROM schedules WHERE id=?", (sid,))
    if not existing:
        error_response(handler, "排课不存在", 404)
        return

    allowed = ["tutor_id", "subject", "start_time", "end_time", "status", "remark", "lead_id"]
    updates = []
    params = []
    for field in allowed:
        if field in body:
            updates.append(f"{field}=?")
            params.append(body[field])

    if not updates:
        error_response(handler, "没有需要更新的字段")
        return

    # 重新计算时长
    if "start_time" in body and "end_time" in body:
        try:
            from datetime import datetime
            fmt = "%Y-%m-%d %H:%M"
            st = datetime.strptime(body["start_time"][:16], fmt)
            et = datetime.strptime(body["end_time"][:16], fmt)
            updates.append("duration_minutes=?")
            params.append(int((et - st).total_seconds() // 60))
        except (ValueError, IndexError):
            pass

    params.append(sid)
    execute(f"UPDATE schedules SET {','.join(updates)} WHERE id=?", tuple(params))

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "update", "schedule", sid, f"更新排课")

    updated = query_one(
        """SELECT s.*, l.name as lead_name, u.display_name as tutor_name
           FROM schedules s
           LEFT JOIN leads l ON s.lead_id = l.id
           LEFT JOIN users u ON s.tutor_id = u.id
           WHERE s.id=?""",
        (sid,),
    )
    ok_response(handler, updated)


@delete("/api/schedules/{schedule_id}")
def delete_schedule(handler, token_payload, qs, body, schedule_id=None):
    if not require_role(token_payload, ["admin", "supervisor", "coordinator"]):
        error_response(handler, "无权删除", 403)
        return
    sid = int(schedule_id)
    s = query_one("SELECT id FROM schedules WHERE id=?", (sid,))
    if not s:
        error_response(handler, "排课不存在", 404)
        return
    execute("DELETE FROM schedules WHERE id=?", (sid,))
    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "delete", "schedule", sid, "删除排课")
    ok_response(handler, {"message": "已删除"})
