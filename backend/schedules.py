"""排课管理 API — CRUD + 日期筛选 + 教师筛选 + 冲突检测"""
from router import get, post, put, delete
from utils import ok_response, error_response, add_oplog, csv_response
from db import query, query_one, execute, execute_lastrowid
from permissions import can, scope_where


# ── 教师排课冲突检测 ──

def _check_teacher_conflict(teacher_id, start_time, end_time, exclude_id=None):
    """检查教师是否有排课时间冲突。返回冲突排课列表（空列表=无冲突）"""
    if not teacher_id or not start_time or not end_time:
        return []
    params = [teacher_id, end_time, start_time]
    exclude_clause = ""
    if exclude_id:
        exclude_clause = " AND s.id != ?"
        params.append(exclude_id)
    rows = query(
        f"""SELECT s.id, s.start_time, s.end_time, l.name as lead_name, s.subject
            FROM schedules s
            LEFT JOIN leads l ON s.lead_id = l.id
            WHERE s.teacher_id = ?
              AND s.status NOT IN ('cancelled')
              AND s.start_time < ?   /* existing_start < new_end */
              AND s.end_time > ?     /* existing_end > new_start */
              {exclude_clause}
            ORDER BY s.start_time ASC""",
        tuple(params),
    )
    return rows


@get("/api/schedules")
def list_schedules(handler, token_payload, qs, body):
    page = int(qs.get("page", [1])[0])
    page_size = int(qs.get("page_size", [50])[0])
    date_from = qs.get("date_from", [None])[0]
    date_to = qs.get("date_to", [None])[0]
    tutor_id = qs.get("tutor_id", [None])[0]
    status = qs.get("status", [None])[0]
    lead_id = qs.get("lead_id", [None])[0]
    teacher_id = qs.get("teacher_id", [None])[0]
    search = qs.get("search", [None])[0]

    role = token_payload["role"]
    user_id = token_payload["sub"]

    where = ["1=1"]
    params = []

    scope_clause, scope_params = scope_where("schedule", role, user_id, "s")
    where.append(scope_clause)
    params.extend(scope_params)

    if date_from:
        where.append("s.start_time >= ?")
        params.append(date_from)
    if date_to:
        where.append("s.start_time <= ?")
        params.append(date_to)
    if tutor_id:
        where.append("s.tutor_id=?")
        params.append(int(tutor_id))
    if teacher_id:
        where.append("s.teacher_id=?")
        params.append(int(teacher_id))
    if status:
        where.append("s.status=?")
        params.append(status)
    if lead_id:
        where.append("s.lead_id=?")
        params.append(int(lead_id))
    if search:
        like = f"%{search}%"
        where.append("l.name LIKE ?")
        params.append(like)

    where_sql = " AND ".join(where)

    total = query_one(
        f"SELECT COUNT(*) as cnt FROM schedules s LEFT JOIN leads l ON s.lead_id = l.id WHERE {where_sql}",
        tuple(params),
    )["cnt"]

    offset = (page - 1) * page_size
    rows = query(
        f"""SELECT s.*, l.name as lead_name,
                   u.display_name as tutor_name,
                   t.name as teacher_name,
                   t.academic_background as teacher_background,
                   t.subjects as teacher_subjects,
                   t.level as teacher_level,
                   cr.display_name as creator_name,
                   (SELECT id FROM lesson_feedback WHERE schedule_id=s.id) as feedback_id
            FROM schedules s
            LEFT JOIN leads l ON s.lead_id = l.id
            LEFT JOIN users u ON s.tutor_id = u.id
            LEFT JOIN teachers t ON s.teacher_id = t.id
            LEFT JOIN users cr ON s.created_by = cr.id
            WHERE {where_sql}
            ORDER BY s.start_time ASC
            LIMIT ? OFFSET ?""",
        tuple(params) + (page_size, offset),
    )

    # 附加每个学生的剩余课时信息
    lead_ids = list(set(r["lead_id"] for r in rows if r.get("lead_id")))
    if lead_ids:
        placeholders = ",".join("?" for _ in lead_ids)
        hour_rows = query(
            f"""SELECT l.id as lead_id,
                       COALESCE(SUM(p.total_hours), 0) as total_hours,
                       COALESCE(SUM(p.used_hours), 0) as used_hours
                FROM leads l
                LEFT JOIN contracts c ON c.lead_id = l.id AND c.status='active'
                LEFT JOIN packages p ON p.contract_id = c.id
                WHERE l.id IN ({placeholders})
                GROUP BY l.id""",
            tuple(lead_ids),
        )
        hour_map = {h["lead_id"]: h for h in hour_rows}
        for r in rows:
            h = hour_map.get(r["lead_id"], {})
            r["total_hours"] = h.get("total_hours", 0)
            r["used_hours"] = h.get("used_hours", 0)
            r["remaining_hours"] = round(float(h.get("total_hours") or 0) - float(h.get("used_hours") or 0), 1)

    ok_response(handler, {"total": total, "page": page, "page_size": page_size, "items": rows})


@get("/api/schedules/export")
def export_schedules(handler, token_payload, qs, body):
    """导出排课 CSV"""
    date_from = qs.get("date_from", [None])[0]
    date_to = qs.get("date_to", [None])[0]
    teacher_id = qs.get("teacher_id", [None])[0]
    status = qs.get("status", [None])[0]
    search = qs.get("search", [None])[0]

    where = ["1=1"]
    params = []
    role = token_payload["role"]
    user_id = token_payload["sub"]
    scope_clause, scope_params = scope_where("schedule", role, user_id, "s")
    where.append(scope_clause)
    params.extend(scope_params)

    if date_from:
        where.append("s.start_time >= ?")
        params.append(date_from)
    if date_to:
        where.append("s.start_time <= ?")
        params.append(date_to)
    if teacher_id:
        where.append("s.teacher_id=?")
        params.append(int(teacher_id))
    if status:
        where.append("s.status=?")
        params.append(status)
    if search:
        where.append("l.name LIKE ?")
        params.append(f"%{search}%")

    rows = query(
        f"""SELECT s.id, l.name as lead_name, t.name as teacher_name,
                   s.subject, s.tutoring_form, s.start_time, s.end_time,
                   s.duration_minutes, s.actual_duration_minutes, s.status,
                   s.remark, s.classin_link
            FROM schedules s
            LEFT JOIN leads l ON s.lead_id = l.id
            LEFT JOIN teachers t ON s.teacher_id = t.id
            WHERE {' AND '.join(where)}
            ORDER BY s.start_time ASC""",
        tuple(params),
    )

    columns = [
        ("id", "ID"),
        ("lead_name", "学生"),
        ("teacher_name", "教师"),
        ("subject", "科目"),
        ("tutoring_form", "辅导形式"),
        ("start_time", "开始时间"),
        ("end_time", "结束时间"),
        ("duration_minutes", "计划时长(min)"),
        ("actual_duration_minutes", "实际时长(min)"),
        ("status", "状态"),
        ("remark", "备注"),
        ("classin_link", "ClassIn链接"),
    ]
    csv_response(handler, rows, columns, "排课导出.csv")


@get("/api/schedules/{schedule_id}")
def get_schedule(handler, token_payload, qs, body, schedule_id=None):
    s = query_one(
        """SELECT s.*, l.name as lead_name, u.display_name as tutor_name,
                  t.name as teacher_name,
                  t.academic_background as teacher_background,
                  t.subjects as teacher_subjects,
                  t.level as teacher_level,
                  cr.display_name as creator_name
           FROM schedules s
           LEFT JOIN leads l ON s.lead_id = l.id
           LEFT JOIN users u ON s.tutor_id = u.id
           LEFT JOIN teachers t ON s.teacher_id = t.id
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
    if not can(token_payload["role"], "schedule:manage"):
        error_response(handler, "无权创建排课", 403)
        return
    lead_id = body.get("lead_id")
    start_time = (body.get("start_time") or "").replace('T', ' ')
    end_time = (body.get("end_time") or "").replace('T', ' ')

    if not lead_id or not start_time or not end_time:
        error_response(handler, "缺少必填参数 (lead_id, start_time, end_time)")
        return

    # ── 教师排课冲突检测 ──
    teacher_id = body.get("teacher_id")
    if teacher_id:
        conflicts = _check_teacher_conflict(teacher_id, start_time, end_time)
        if conflicts:
            names = [f"{c['lead_name'] or '?'} ({c['start_time'][:16]}-{c['end_time'][:16]})" for c in conflicts[:3]]
            msg = f"教师排课冲突：该时间段已有 {len(conflicts)} 个排课"
            if names:
                msg += "：" + "；".join(names)
            error_response(handler, msg, 409)
            return

    # 计算时长（分钟）
    duration = 0
    try:
        from datetime import datetime
        fmt = "%Y-%m-%d %H:%M"
        st = datetime.strptime(start_time[:16].replace('T', ' '), fmt)
        et = datetime.strptime(end_time[:16].replace('T', ' '), fmt)
        duration = int((et - st).total_seconds() // 60)
    except (ValueError, IndexError):
        pass

    # 如果传了 teacher_id 就用，否则兼容旧 tutor_id
    if not teacher_id and body.get("tutor_id"):
        # 从旧 tutor_id 反查 teachers 表（兼容旧前端）
        t = query_one(
            "SELECT id FROM teachers WHERE name=(SELECT display_name FROM users WHERE id=?)",
            (int(body["tutor_id"]),),
        )
        teacher_id = t["id"] if t else None

    repeat_count = int(body.get("repeat_count", 1))
    if repeat_count < 1:
        repeat_count = 1
    if repeat_count > 52:
        repeat_count = 52  # 最多一年

    from datetime import datetime, timedelta
    fmt = "%Y-%m-%d %H:%M"
    base_start = datetime.strptime(start_time[:16].replace('T', ' '), fmt) if start_time else None
    base_end = datetime.strptime(end_time[:16].replace('T', ' '), fmt) if end_time else None

    first_sid = None
    for week in range(repeat_count):
        if week > 0 and base_start and base_end:
            cur_start = (base_start + timedelta(weeks=week)).strftime(fmt)
            cur_end = (base_end + timedelta(weeks=week)).strftime(fmt)
        else:
            cur_start = start_time
            cur_end = end_time

        sid = execute_lastrowid(
            """INSERT INTO schedules (lead_id, tutor_id, teacher_id, subject, start_time, end_time,
               duration_minutes, status, remark, created_by, tutoring_form)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                int(lead_id),
                int(body["tutor_id"]) if body.get("tutor_id") else None,
                int(teacher_id) if teacher_id else None,
                body.get("subject", ""),
                cur_start,
                cur_end,
                duration,
                body.get("status", "pending"),
                body.get("remark", ""),
                token_payload["sub"],
                body.get("tutoring_form", ""),
            ),
        )

        if first_sid is None:
            first_sid = sid

        add_oplog(token_payload["sub"], token_payload.get("name", ""),
                  "create", "schedule", sid,
                  f"创建排课{' (每周重复 第' + str(week+1) + '周)' if repeat_count > 1 else ''}")

        # 如果创建时直接标了 completed，也扣课时
        if body.get("status") == "completed" and duration > 0:
            hours = round(duration / 60, 1)
            pkg = query_one(
                """SELECT p.id FROM packages p
                   JOIN contracts c ON p.contract_id = c.id
                   WHERE c.lead_id=? AND c.status='active'
                   ORDER BY p.created_at ASC LIMIT 1""",
                (lead_id,),
            )
            if pkg:
                execute(
                    "UPDATE packages SET used_hours = ROUND(used_hours + ?, 1) WHERE id=?",
                    (hours, pkg["id"]),
                )

    s = query_one("SELECT * FROM schedules WHERE id=?", (first_sid,))
    ok_response(handler, {"message": f"已创建 {repeat_count} 个排课", "first": s, "count": repeat_count}, 201)


@put("/api/schedules/{schedule_id}")
def update_schedule(handler, token_payload, qs, body, schedule_id=None):
    if not can(token_payload["role"], "schedule:manage"):
        error_response(handler, "无权操作", 403)
        return
    sid = int(schedule_id)
    existing = query_one("SELECT * FROM schedules WHERE id=?", (sid,))
    if not existing:
        error_response(handler, "排课不存在", 404)
        return

    # ── 教师排课冲突检测（基于更新后的值）──
    check_teacher = body.get("teacher_id") or existing.get("teacher_id")
    check_start = body.get("start_time") or existing.get("start_time")
    check_end = body.get("end_time") or existing.get("end_time")
    if check_teacher and check_start and check_end:
        conflicts = _check_teacher_conflict(check_teacher, check_start, check_end, exclude_id=sid)
        if conflicts:
            names = [f"{c['lead_name'] or '?'} ({c['start_time'][:16]}-{c['end_time'][:16]})" for c in conflicts[:3]]
            msg = f"教师排课冲突：该时间段已有 {len(conflicts)} 个排课"
            if names:
                msg += "：" + "；".join(names)
            error_response(handler, msg, 409)
            return

    allowed = ["tutor_id", "teacher_id", "subject", "start_time", "end_time", "status", "remark",
               "lead_id", "tutoring_form", "actual_duration_minutes"]
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
            st = datetime.strptime(body["start_time"][:16].replace('T', ' '), fmt)
            et = datetime.strptime(body["end_time"][:16].replace('T', ' '), fmt)
            updates.append("duration_minutes=?")
            params.append(int((et - st).total_seconds() // 60))
        except (ValueError, IndexError):
            pass

    params.append(sid)
    execute(f"UPDATE schedules SET {','.join(updates)} WHERE id=?", tuple(params))

    # ── 实际时长录入 → 自动扣课时 ──
    # 如果 actual_duration_minutes 被设置且旧值为 NULL（首次录入实际时长）
    new_actual = body.get("actual_duration_minutes")
    old_actual = existing.get("actual_duration_minutes")
    if new_actual is not None and old_actual is None:
        lead_id = body.get("lead_id") or existing["lead_id"]
        hours = round(int(new_actual) / 60, 1)
        if hours > 0:
            pkg = query_one(
                """SELECT p.id, p.used_hours
                   FROM packages p
                   JOIN contracts c ON p.contract_id = c.id
                   WHERE c.lead_id=? AND c.status='active'
                   ORDER BY p.created_at ASC LIMIT 1""",
                (lead_id,),
            )
            if pkg:
                execute(
                    "UPDATE packages SET used_hours = ROUND(used_hours + ?, 1) WHERE id=?",
                    (hours, pkg["id"]),
                )
                add_oplog(token_payload["sub"], token_payload.get("name", ""),
                          "use", "package", pkg["id"],
                          f"录入实际时长自动扣课时: {hours}h (排课ID: {sid})")

    # ── 自动扣课时：排课标为 completed 时，从学生活跃课时包扣减 ──
    new_status = body.get("status")
    old_status = existing["status"]
    if new_status == "completed" and old_status != "completed":
        lead_id = body.get("lead_id") or existing["lead_id"]
        # 优先使用实际时长
        actual = new_actual or existing.get("actual_duration_minutes")
        if actual is not None:
            dur = int(actual)
        else:
            dur = body.get("duration_minutes") or existing["duration_minutes"]
        if not dur or dur <= 0:
            error_response(handler, "缺少上课时长，请先录入实际上课时长", 400)
            return
        hours = round(dur / 60, 1)  # 分钟转小时

        # 找到该学生 active 合同的第一个课时包
        pkg = query_one(
            """SELECT p.id, p.used_hours
               FROM packages p
               JOIN contracts c ON p.contract_id = c.id
               WHERE c.lead_id=? AND c.status='active'
               ORDER BY p.created_at ASC LIMIT 1""",
            (lead_id,),
        )
        if pkg:
            execute(
                "UPDATE packages SET used_hours = ROUND(used_hours + ?, 1) WHERE id=?",
                (hours, pkg["id"]),
            )
            add_oplog(token_payload["sub"], token_payload.get("name", ""),
                      "use", "package", pkg["id"],
                      f"排课完成自动扣课时: {hours}h (排课ID: {sid})")
    elif new_status != "completed" and old_status == "completed":
        # 取消已完成状态 → 还回课时（防止误操作回退）
        lead_id = body.get("lead_id") or existing["lead_id"]
        # 优先使用实际时长
        actual = new_actual or existing.get("actual_duration_minutes")
        if actual is not None:
            dur = int(actual)
        else:
            dur = body.get("duration_minutes") or existing["duration_minutes"] or 60
        hours = round(dur / 60, 1)
        pkg = query_one(
            """SELECT p.id, p.used_hours
               FROM packages p
               JOIN contracts c ON p.contract_id = c.id
               WHERE c.lead_id=? AND c.status='active'
               ORDER BY p.created_at ASC LIMIT 1""",
            (lead_id,),
        )
        if pkg and (pkg["used_hours"] or 0) >= hours:
            execute(
                "UPDATE packages SET used_hours = ROUND(used_hours - ?, 1) WHERE id=?",
                (hours, pkg["id"]),
            )

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "update", "schedule", sid, f"更新排课")

    updated = query_one(
        """SELECT s.*, l.name as lead_name, u.display_name as tutor_name,
                  t.name as teacher_name,
                  t.academic_background as teacher_background,
                  t.subjects as teacher_subjects,
                  t.level as teacher_level
           FROM schedules s
           LEFT JOIN leads l ON s.lead_id = l.id
           LEFT JOIN users u ON s.tutor_id = u.id
           LEFT JOIN teachers t ON s.teacher_id = t.id
           WHERE s.id=?""",
        (sid,),
    )
    ok_response(handler, updated)


@delete("/api/schedules/{schedule_id}")
def delete_schedule(handler, token_payload, qs, body, schedule_id=None):
    if not can(token_payload["role"], "schedule:manage"):
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
