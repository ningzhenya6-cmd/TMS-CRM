"""线索 API — CRUD + 分页 + 搜索 + 筛选 + 批量操作"""
from router import get, post, put, delete
from utils import json_response, error_response, parse_body, ok_response, add_oplog, csv_response
from db import query, query_one, execute, execute_lastrowid, get_conn
from statemachine import transition_lead, transition_lead_safe, InvalidTransition
from permissions import can, scope_where


@get("/api/leads")
def list_leads(handler, token_payload, qs, body):
    page = int(qs.get("page", [1])[0])
    page_size = int(qs.get("page_size", [15])[0])
    status = qs.get("status", [None])[0]
    source = qs.get("source", [None])[0]
    rank = qs.get("rank", [None])[0]
    search = qs.get("search", [None])[0]
    assignee_id = qs.get("assignee_id", [None])[0]
    date_from = qs.get("date_from", [None])[0]
    date_to = qs.get("date_to", [None])[0]

    role = token_payload["role"]
    user_id = token_payload["sub"]

    where = ["1=1"]
    params = []

    # 权限过滤（通过声明式 scope 控制数据范围）
    scope_clause, scope_params = scope_where("lead", role, user_id, "l")
    where.append(scope_clause)
    params.extend(scope_params)

    if status and status != "all":
        where.append("l.status=?")
        params.append(status)
    if source and source != "all":
        where.append("l.source=?")
        params.append(source)
    if rank and rank != "all":
        where.append("l.lead_rank=?")
        params.append(rank)
    if assignee_id:
        where.append("l.assignee_id=?")
        params.append(int(assignee_id))
    if search:
        like = f"%{search}%"
        where.append("(l.name LIKE ? OR l.phone LIKE ? OR l.wechat LIKE ?)")
        params.extend([like, like, like])
    if date_from:
        where.append("date(l.created_at) >= ?")
        params.append(date_from)
    if date_to:
        where.append("date(l.created_at) <= ?")
        params.append(date_to)

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

@get("/api/leads/sources")
def list_sources(handler, token_payload, qs, body):
    """返回来源及其数量，支持日期范围筛选，遵循角色权限"""
    date_from = qs.get("date_from", [None])[0]
    date_to = qs.get("date_to", [None])[0]

    role = token_payload["role"]
    user_id = token_payload["sub"]

    where = ["source != ''"]
    params = []

    scope_clause, scope_params = scope_where("lead", role, user_id, "l")
    where.append(scope_clause)
    params.extend(scope_params)

    if date_from:
        where.append("date(l.created_at) >= ?")
        params.append(date_from)
    if date_to:
        where.append("date(l.created_at) <= ?")
        params.append(date_to)

    where_sql = " AND ".join(where)
    rows = query(
        f"SELECT l.source, COUNT(*) as cnt FROM leads l WHERE {where_sql} GROUP BY l.source ORDER BY cnt DESC",
        tuple(params),
    )
    ok_response(handler, rows)


@get("/api/leads/export")
def export_leads(handler, token_payload, qs, body):
    """导出线索 CSV"""
    status = qs.get("status", [None])[0]
    source = qs.get("source", [None])[0]
    rank = qs.get("rank", [None])[0]
    search = qs.get("search", [None])[0]
    date_from = qs.get("date_from", [None])[0]
    date_to = qs.get("date_to", [None])[0]

    role = token_payload["role"]
    user_id = token_payload["sub"]

    where = ["1=1"]
    params = []
    scope_clause, scope_params = scope_where("lead", role, user_id, "l")
    where.append(scope_clause)
    params.extend(scope_params)

    if status and status != "all":
        where.append("l.status=?")
        params.append(status)
    if source and source != "all":
        where.append("l.source=?")
        params.append(source)
    if rank and rank != "all":
        where.append("l.lead_rank=?")
        params.append(rank)
    if search:
        like = f"%{search}%"
        where.append("(l.name LIKE ? OR l.phone LIKE ? OR l.wechat LIKE ?)")
        params.extend([like, like, like])
    if date_from:
        where.append("date(l.created_at) >= ?")
        params.append(date_from)
    if date_to:
        where.append("date(l.created_at) <= ?")
        params.append(date_to)

    rows = query(
        f"""SELECT l.id, l.name, l.phone, l.wechat, l.source, l.country, l.grade,
                   l.status, l.lost_reason,
                   u.display_name as assignee_name,
                   l.created_at, l.last_followup_at, l.next_followup_at
            FROM leads l
            LEFT JOIN users u ON l.assignee_id = u.id
            WHERE {' AND '.join(where)}
            ORDER BY l.created_at DESC""",
        tuple(params),
    )

    columns = [
        ("id", "ID"),
        ("name", "姓名"),
        ("phone", "手机"),
        ("wechat", "微信"),
        ("source", "来源"),
        ("country", "意向国家"),
        ("grade", "年级"),
        ("status", "状态"),
        ("lost_reason", "流失原因"),
        ("assignee_name", "跟进人"),
        ("created_at", "创建时间"),
        ("last_followup_at", "最近跟进"),
        ("next_followup_at", "下次跟进"),
    ]
    csv_response(handler, rows, columns, "线索导出.csv")


@get("/api/leads/{lead_id}")
def get_lead(handler, token_payload, qs, body, lead_id=None):
    lead = query_one(
        """SELECT l.*, u.display_name as assignee_name, uc.display_name as coordinator_name
           FROM leads l
           LEFT JOIN users u ON l.assignee_id = u.id
           LEFT JOIN users uc ON l.coordinator_id = uc.id
           WHERE l.id=?""",
        (int(lead_id),),
    )
    if not lead:
        error_response(handler, "线索不存在", 404)
        return

    # 权限检查：只有 edit_any 角色可看所有，其余只能看自己 scope 内的
    role = token_payload["role"]
    user_id = token_payload["sub"]
    if not can(role, "lead:edit_any"):
        scope_clause, _ = scope_where("lead", role, user_id)
        # 从 scope 取字段名，校验当前线索是否归属该用户
        if "assignee_id" in scope_clause and lead.get("assignee_id") != user_id:
            error_response(handler, "无权访问此线索", 403)
            return
        if "coordinator_id" in scope_clause and lead.get("coordinator_id") != user_id:
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

    # 学业分析报告列表（不含完整 report_json，仅摘要）
    lead["consulting_reports"] = query(
        """SELECT cr.id, cr.target_country, cr.target_school, cr.target_major,
                  cr.risk_level, cr.summary, cr.status, cr.progress,
                  cr.report_type, cr.program_url,
                  cr.created_at, cr.updated_at
           FROM consulting_reports cr
           WHERE cr.lead_id=?
           ORDER BY cr.created_at DESC""",
        (int(lead_id),),
    )

    # 签约学生额外聚合合同、课时包、排课数据
    if lead["status"] == "enrolled":
        lead["contracts"] = query(
            """SELECT c.*,
                      (SELECT COALESCE(SUM(p.total_hours),0) FROM packages p WHERE p.contract_id=c.id) as total_hours,
                      (SELECT COALESCE(SUM(p.used_hours),0) FROM packages p WHERE p.contract_id=c.id) as used_hours
               FROM contracts c WHERE c.lead_id=?
               ORDER BY c.created_at DESC""",
            (lead["id"],),
        )
        for c in lead["contracts"]:
            c["remaining_hours"] = round(c["total_hours"] - c["used_hours"], 1)
            c["packages"] = query(
                "SELECT * FROM packages WHERE contract_id=? ORDER BY created_at ASC",
                (c["id"],),
            )

        lead["schedules"] = query(
            """SELECT s.*, u.display_name as tutor_name,
                      t.name as teacher_name,
                      t.academic_background as teacher_background,
                      t.subjects as teacher_subjects,
                      t.level as teacher_level
               FROM schedules s
               LEFT JOIN users u ON s.tutor_id = u.id
               LEFT JOIN teachers t ON s.teacher_id = t.id
               WHERE s.lead_id=?
               ORDER BY s.start_time DESC LIMIT 20""",
            (lead["id"],),
        )

    ok_response(handler, lead)


@post("/api/leads")
def create_lead(handler, token_payload, qs, body):
    if not can(token_payload["role"], "lead:create"):
        error_response(handler, "无权创建线索", 403)
        return
    name = (body.get("name") or "").strip()
    if not name:
        error_response(handler, "姓名不能为空")
        return

    created_at = body.get("created_at", "") or __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")

    lead_id = execute_lastrowid(
        """INSERT INTO leads (name, phone, wechat, source, country, grade, remark, creator_id, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,'pending',?)""",
        (
            name,
            body.get("phone", ""),
            body.get("wechat", ""),
            body.get("source", "其他"),
            body.get("country", ""),
            body.get("grade", ""),
            body.get("remark", ""),
            token_payload["sub"],
            created_at,
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
    if not can(role, "lead:edit"):
        error_response(handler, "无权操作", 403)
        return
    if not can(role, "lead:edit_any") and lead["assignee_id"] != user_id:
        error_response(handler, "无权操作", 403)
        return

    # ── 状态变更必须走状态机 ──
    new_status = body.get("status")
    if new_status and new_status != lead["status"]:
        try:
            transition_lead(lead_id, new_status)
        except InvalidTransition as e:
            error_response(handler, str(e), 400)
            return
        # 如果变为流失，记录流失原因
        if new_status == "lost":
            lost_reason = body.get("lost_reason", "")
            if not lost_reason:
                error_response(handler, "标记流失时请填写流失原因", 400)
                return
            execute("UPDATE leads SET lost_reason=? WHERE id=?", (lost_reason, lead_id))

    # ── 其他字段正常更新 ──
    allowed_fields = ["name", "phone", "wechat", "source", "country", "grade",
                      "assignee_id", "remark", "coordinator_id", "lost_reason",
                      "created_at", "lead_rank", "contact_status"]
    updates = []
    params = []
    for field in allowed_fields:
        if field in body:
            updates.append(f"{field}=?")
            params.append(body[field])

    if updates:
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
    if not can(token_payload["role"], "lead:delete"):
        error_response(handler, "无权删除", 403)
        return
    lead_id = int(lead_id)
    lead = query_one("SELECT id, name FROM leads WHERE id=?", (lead_id,))
    if not lead:
        error_response(handler, "线索不存在", 404)
        return

    conn = get_conn()
    try:
        conn.execute("BEGIN")
        # 先删各依赖子表（无 ON DELETE CASCADE 的表）
        execute("DELETE FROM schedules WHERE lead_id=?", (lead_id,))
        execute("DELETE FROM exam_results WHERE lead_id=?", (lead_id,))
        execute("DELETE FROM admission_results WHERE lead_id=?", (lead_id,))
        execute("DELETE FROM consulting_reports WHERE lead_id=?", (lead_id,))
        execute("DELETE FROM lesson_feedback WHERE lead_id=?", (lead_id,))
        # 有 CASCADE 的表（followups, contracts）也会自动删，但显式删以防外键未启用
        execute("DELETE FROM followups WHERE lead_id=?", (lead_id,))
        # 删合同前要先删 payment_records 和 packages（无 CASCADE）
        for r in query("SELECT id FROM contracts WHERE lead_id=?", (lead_id,)):
            cid = r["id"]
            execute("DELETE FROM payment_records WHERE contract_id=?", (cid,))
            execute("DELETE FROM packages WHERE contract_id=?", (cid,))
        execute("DELETE FROM contracts WHERE lead_id=?", (lead_id,))
        # 最后删线索
        execute("DELETE FROM leads WHERE id=?", (lead_id,))
        conn.commit()
    except Exception as e:
        conn.execute("ROLLBACK")
        error_response(handler, f"删除失败：{e}", 500)
        return

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "delete", "lead", lead_id, f"删除线索: {lead['name']}")
    ok_response(handler, {"message": "已删除"})


# ── 批量操作 ──

@post("/api/leads/batch/assign")
def batch_assign(handler, token_payload, qs, body):
    if not can(token_payload["role"], "lead:batch_assign"):
        error_response(handler, "无权分配", 403)
        return
    lead_ids = body.get("lead_ids", [])
    assignee_id = body.get("assignee_id")
    if not lead_ids or not assignee_id:
        error_response(handler, "参数不完整")
        return
    count = 0
    errors = []
    for lid in lead_ids:
        execute("UPDATE leads SET assignee_id=? WHERE id=?", (assignee_id, lid))
        # 如果当前是 pending，通过状态机推进到 assigned
        lead = query_one("SELECT status FROM leads WHERE id=?", (lid,))
        if lead and lead["status"] == "pending":
            try:
                transition_lead(lid, "assigned")
            except InvalidTransition:
                pass  # 静默跳过，不阻塞分配
        count += 1
    ok_response(handler, {"updated": count, "errors": errors if errors else None})


@post("/api/leads/batch/status")
def batch_status(handler, token_payload, qs, body):
    if not can(token_payload["role"], "lead:batch_op"):
        error_response(handler, "无权批量操作", 403)
        return
    lead_ids = body.get("lead_ids", [])
    status = body.get("status")
    if not lead_ids or not status:
        error_response(handler, "参数不完整")
        return
    lost_reason = body.get("lost_reason", "") if status == "lost" else ""
    if status == "lost" and not lost_reason:
        error_response(handler, "标记流失时请填写流失原因", 400)
        return
    count = 0
    errors = []
    for lid in lead_ids:
        ok, result = transition_lead_safe(lid, status)
        if ok:
            if lost_reason:
                execute("UPDATE leads SET lost_reason=? WHERE id=?", (lost_reason, lid))
            count += 1
        else:
            errors.append({"lead_id": lid, "error": result})
    ok_response(handler, {"updated": count, "errors": errors if errors else None})


@post("/api/leads/batch/assign_coordinator")
def batch_assign_coordinator(handler, token_payload, qs, body):
    """批量分配教务班主任"""
    if not can(token_payload["role"], "lead:adjust_coordinator"):
        error_response(handler, "无权分配班主任", 403)
        return
    lead_ids = body.get("lead_ids", [])
    coordinator_id = body.get("coordinator_id")
    if not lead_ids or not coordinator_id:
        error_response(handler, "参数不完整")
        return
    count = 0
    for lid in lead_ids:
        execute(
            "UPDATE leads SET coordinator_id=?, coordinator_at=datetime('now','localtime') WHERE id=?",
            (coordinator_id, lid),
        )
        add_oplog(token_payload["sub"], token_payload.get("name", ""),
                  "assign", "coordinator", lid,
                  f"分配教务班主任(ID:{coordinator_id})给线索(ID:{lid})")
        count += 1
    ok_response(handler, {"updated": count})
