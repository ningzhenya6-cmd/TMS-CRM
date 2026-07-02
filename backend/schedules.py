"""排课管理 API — CRUD + 日期筛选 + 教师筛选 + 冲突检测 + 批量排课"""
import datetime
import math
from router import get, post, put, delete
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid, get_conn
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


def _duration_minutes(start_str, end_str):
    """计算两个时间字符串之间的分钟差"""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            s = datetime.datetime.strptime(start_str[:16], fmt)
            e = datetime.datetime.strptime(end_str[:16], fmt)
            return int((e - s).total_seconds() / 60)
        except (ValueError, TypeError):
            continue
    return 0


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
                   COALESCE(t.name, s.teacher_name, '') as teacher_name,
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
        f"""SELECT s.id, l.name as lead_name, COALESCE(t.name, s.teacher_name, '') as teacher_name,
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
                  COALESCE(t.name, s.teacher_name, '') as teacher_name,
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
    # 附加课时包进度
    if s["lead_id"]:
        pkg = query_one(
            """SELECT COALESCE(SUM(p.total_hours),0) as total_hours,
                      COALESCE(SUM(p.used_hours),0) as used_hours
               FROM packages p
               JOIN contracts c ON p.contract_id = c.id
               WHERE c.lead_id=? AND c.status='active'""",
            (s["lead_id"],),
        )
        if pkg:
            s["total_hours"] = pkg["total_hours"]
            s["used_hours"] = pkg["used_hours"]
            s["remaining_hours"] = round(pkg["total_hours"] - pkg["used_hours"], 1)
    ok_response(handler, s)


@post("/api/schedules")
def create_schedule(handler, token_payload, qs, body):
    """创建单条排课（含每周重复）"""
    if not can(token_payload["role"], "schedule:manage"):
        error_response(handler, "无权操作", 403)
        return

    lead_id = body.get("lead_id")
    if not lead_id:
        error_response(handler, "请选择学生")
        return

    teacher_id = body.get("teacher_id")
    start_time = body.get("start_time")
    end_time = body.get("end_time")
    if not start_time or not end_time:
        error_response(handler, "请填写时间")
        return

    duration = _duration_minutes(start_time, end_time)
    repeat_count = body.get("repeat_count", 1)
    if repeat_count > 52:
        error_response(handler, "重复周数不能超过 52")
        return

    uid = token_payload["sub"]
    created_ids = []

    conn = get_conn()
    try:
        conn.execute("BEGIN")
        for week in range(repeat_count):
            if repeat_count > 1:
                base_dt = datetime.datetime.strptime(start_time[:10], "%Y-%m-%d")
                cur_start = (base_dt + datetime.timedelta(weeks=week)).strftime("%Y-%m-%d") + start_time[10:]
                cur_end = (base_dt + datetime.timedelta(weeks=week)).strftime("%Y-%m-%d") + end_time[10:]
            else:
                cur_start, cur_end = start_time, end_time

            sid = execute_lastrowid(
                """INSERT INTO schedules (lead_id, tutor_id, teacher_id, teacher_name, subject, start_time, end_time,
                   duration_minutes, status, remark, created_by, tutoring_form)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    int(lead_id),
                    int(body["tutor_id"]) if body.get("tutor_id") else None,
                    int(teacher_id) if teacher_id else None,
                    body.get("teacher_name", ""),
                    body.get("subject", ""),
                    cur_start,
                    cur_end,
                    duration,
                    body.get("status", "pending"),
                    body.get("remark", ""),
                    uid,
                    body.get("tutoring_form", ""),
                ),
            )
            created_ids.append(sid)

            # 如果创建时就是 completed 状态，直接扣课时
            if body.get("status") == "completed":
                hours = round(duration / 60, 1)
                if hours > 0:
                    pkg = query_one(
                        """SELECT p.id FROM packages p
                           JOIN contracts c ON p.contract_id = c.id
                           WHERE c.lead_id=? AND c.status='active'
                           ORDER BY p.created_at ASC LIMIT 1""",
                        (int(lead_id),),
                    )
                    if pkg:
                        conn.execute("UPDATE packages SET used_hours = ROUND(used_hours + ?, 1) WHERE id=?", (hours, pkg["id"]))

        conn.commit()
    except Exception as e:
        conn.execute("ROLLBACK")
        error_response(handler, f"创建失败: {e}", 500)
        return

    add_oplog(uid, token_payload.get("name", ""), "create", "schedule", created_ids[0],
              f"创建排课 {len(created_ids)} 条 (含重复)")
    ok_response(handler, {"id": created_ids[0], "count": len(created_ids)}, 201)


@put("/api/schedules/{schedule_id}")
def update_schedule(handler, token_payload, qs, body, schedule_id=None):
    """更新排课（含实际时长录入→自动扣课时）"""
    if not can(token_payload["role"], "schedule:manage"):
        error_response(handler, "无权操作", 403)
        return
    sid = int(schedule_id)
    existing = query_one("SELECT * FROM schedules WHERE id=?", (sid,))
    if not existing:
        error_response(handler, "排课不存在", 404)
        return

    allowed = ["tutor_id", "teacher_id", "teacher_name", "subject", "start_time", "end_time", "status",
               "remark", "lead_id", "tutoring_form", "actual_duration_minutes"]
    updates = []
    params = []
    for field in allowed:
        if field in body:
            updates.append(f"{field}=?")
            params.append(body[field])
    if updates:
        params.append(sid)
        execute(f"UPDATE schedules SET {','.join(updates)} WHERE id=?", tuple(params))

    new_actual = body.get("actual_duration_minutes")
    old_actual = existing.get("actual_duration_minutes")
    new_status = body.get("status")
    old_status = existing["status"]

    # 避免双重扣减：同一请求同时设 actual_duration 和 status=completed 时只扣一次
    both_completing = (new_actual is not None and old_actual is None
                       and new_status == "completed" and old_status != "completed")

    if new_actual is not None and old_actual is None and not both_completing:
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
                execute("UPDATE packages SET used_hours = ROUND(used_hours + ?, 1) WHERE id=?", (hours, pkg["id"]))

    # 排课标为 completed 时自动扣课时
    if new_status == "completed" and old_status != "completed":
        lead_id = body.get("lead_id") or existing["lead_id"]
        actual = new_actual or existing.get("actual_duration_minutes")
        if actual is not None:
            dur = int(actual)
        else:
            dur = body.get("duration_minutes") or existing["duration_minutes"]
        if not dur or dur <= 0:
            error_response(handler, "缺少上课时长，请先录入实际上课时长", 400)
            return
        hours = round(dur / 60, 1)
        pkg = query_one(
            """SELECT p.id, p.used_hours
               FROM packages p
               JOIN contracts c ON p.contract_id = c.id
               WHERE c.lead_id=? AND c.status='active'
               ORDER BY p.created_at ASC LIMIT 1""",
            (lead_id,),
        )
        if pkg:
            execute("UPDATE packages SET used_hours = ROUND(used_hours + ?, 1) WHERE id=?", (hours, pkg["id"]))

    add_oplog(token_payload["sub"], token_payload.get("name", ""), "update", "schedule", sid, "更新排课")
    updated = query_one("SELECT * FROM schedules WHERE id=?", (sid,))
    ok_response(handler, updated)


@delete("/api/schedules/{schedule_id}")
def delete_schedule(handler, token_payload, qs, body, schedule_id=None):
    """删除排课——退回课时（已完成课程才需退回）"""
    if not can(token_payload["role"], "schedule:manage"):
        error_response(handler, "无权操作", 403)
        return
    sid = int(schedule_id)
    s = query_one("SELECT * FROM schedules WHERE id=?", (sid,))
    if not s:
        error_response(handler, "排课不存在", 404)
        return
    uid = token_payload["sub"]
    uname = token_payload.get("name", "")

    conn = get_conn()
    try:
        conn.execute("BEGIN")

        lead_id = s["lead_id"]
        # 获取实际消耗的时长
        actual = s.get("actual_duration_minutes") or s.get("duration_minutes") or 0
        # 判断是否已经扣过课时（排课状态为 completed 或 actual_duration 非空）
        was_deducted = s["status"] == "completed" or s.get("actual_duration_minutes") is not None
        # 检查操作日志中有没有扣课时记录
        if was_deducted and actual > 0:
            hours_to_restore = round(actual / 60, 1)
            if hours_to_restore > 0:
                pkgs = query(
                    "SELECT id, used_hours FROM packages WHERE contract_id IN (SELECT id FROM contracts WHERE lead_id=? AND status='active') ORDER BY created_at DESC",
                    (lead_id,),
                )
                if pkgs:
                    remaining_to_restore = hours_to_restore
                    for pkg in pkgs:
                        if remaining_to_restore <= 0:
                            break
                        current_used = pkg["used_hours"] or 0
                        if current_used >= remaining_to_restore:
                            conn.execute("UPDATE packages SET used_hours = ROUND(used_hours - ?, 1) WHERE id=?", (remaining_to_restore, pkg["id"]))
                            remaining_to_restore = 0
                        else:
                            conn.execute("UPDATE packages SET used_hours = 0 WHERE id=?", (pkg["id"],))
                            remaining_to_restore -= current_used

        conn.execute("DELETE FROM lesson_feedback WHERE schedule_id=?", (sid,))
        conn.execute("DELETE FROM schedules WHERE id=?", (sid,))
        conn.commit()

        add_oplog(uid, uname, "delete", "schedule", sid, f"删除排课 (已退款)")
    except Exception as e:
        conn.execute("ROLLBACK")
        error_response(handler, f"删除失败: {e}", 500)
        return
    ok_response(handler, {"message": "已删除"})


@post("/api/schedules/batch-delete")
def batch_delete_schedules(handler, token_payload, qs, body):
    """批量删除排课——全部退回课时"""
    if not can(token_payload["role"], "schedule:manage"):
        error_response(handler, "无权操作", 403)
        return
    ids = body.get("ids", [])
    if not ids:
        error_response(handler, "请选择要删除的排课")
        return
    uid = token_payload["sub"]
    uname = token_payload.get("name", "")
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        for sid in ids:
            s = query_one("SELECT * FROM schedules WHERE id=?", (sid,))
            if not s:
                continue
            actual = s.get("actual_duration_minutes") or s.get("duration_minutes") or 0
            was_deducted = s["status"] == "completed" or s.get("actual_duration_minutes") is not None
            if was_deducted and actual > 0 and s.get("lead_id"):
                hours_to_restore = round(actual / 60, 1)
                if hours_to_restore > 0:
                    conn.execute("""UPDATE packages SET used_hours = ROUND(used_hours - ?, 1)
                        WHERE id = (SELECT p.id FROM packages p JOIN contracts c ON p.contract_id=c.id
                                    WHERE c.lead_id=? AND c.status='active' ORDER BY p.created_at DESC LIMIT 1)""",
                                 (hours_to_restore, s["lead_id"]))
            conn.execute("DELETE FROM lesson_feedback WHERE schedule_id=?", (sid,))
            conn.execute("DELETE FROM schedules WHERE id=?", (sid,))
        conn.commit()
    except Exception as e:
        conn.execute("ROLLBACK")
        error_response(handler, f"批量删除失败: {e}", 500)
        return
    add_oplog(uid, uname, "batch_delete", "schedule", 0, f"批量删除排课 {len(ids)} 条")
    ok_response(handler, {"message": f"已删除 {len(ids)} 条"})


@post("/api/schedules/batch")
def batch_create_schedules(handler, token_payload, qs, body):
    """批量排课——一次性创建多条排课（混合：指定日期 + 每周重复）

    请求格式:
    {
      "lead_id": 123,
      "status": "pending",          // 统一状态
      "items": [
        { "type": "fixed",          // 指定日期
          "date": "2026-07-06",
          "start_time": "14:00", "end_time": "15:00",
          "teacher_id": 5, "subject": "雅思", "tutoring_form": "1v1"
        },
        { "type": "weekly",         // 每周重复
          "day_of_week": 1,         // 0=周日, 1=周一 ... 6=周六
          "start_time": "14:00", "end_time": "15:00",
          "teacher_id": 5, "subject": "雅思", "tutoring_form": "1v1",
          "repeat_weeks": 4,
          "start_date": "2026-07-06"  // 起始日期（周一）
        }
      ]
    }
    """
    if not can(token_payload["role"], "schedule:manage"):
        error_response(handler, "无权操作", 403)
        return

    lead_id = body.get("lead_id")
    items = body.get("items", [])
    status = body.get("status", "pending")

    if not lead_id:
        error_response(handler, "请选择学生")
        return
    if not items or not isinstance(items, list) or len(items) == 0:
        error_response(handler, "请添加至少一条排课")
        return
    if len(items) > 100:
        error_response(handler, "单次最多 100 条")
        return

    uid = token_payload["sub"]
    uname = token_payload.get("name", "")
    conn = get_conn()
    created_ids = []

    def parse_time(t_str):
        """从 '14:00' 或 '2026-07-06 14:00' 提取小时和分钟"""
        if ':' in t_str:
            parts = t_str.strip().split(':')
            return int(parts[0]), int(parts[1])
        return 0, 0

    def calc_duration_minutes(start, end):
        h1, m1 = parse_time(start)
        h2, m2 = parse_time(end)
        return (h2 * 60 + m2) - (h1 * 60 + m1)

    try:
        conn.execute("BEGIN")

        for idx, item in enumerate(items):
            typ = item.get("type", "fixed")
            teacher_id = item.get("teacher_id")
            teacher_name = item.get("teacher_name", "")
            subject = item.get("subject", "")
            tutoring_form = item.get("tutoring_form", "")
            remark = item.get("remark", "")

            if typ == "fixed":
                date = item.get("date", "")
                st = item.get("start_time", "")
                et = item.get("end_time", "")
                if not date or not st or not et:
                    continue
                start_dt = date + " " + (st if ':' in st else st + ":00")
                end_dt = date + " " + (et if ':' in et else et + ":00")
                dur = calc_duration_minutes(st, et) or _duration_minutes(start_dt, end_dt)

                sid = execute_lastrowid(
                    """INSERT INTO schedules (lead_id, teacher_id, teacher_name, subject, start_time, end_time,
                       duration_minutes, status, remark, created_by, tutoring_form)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (int(lead_id),
                     int(teacher_id) if teacher_id else None,
                     teacher_name, subject, start_dt, end_dt,
                     dur, status, remark, uid, tutoring_form),
                )
                created_ids.append(sid)

            elif typ == "weekly":
                dow = item.get("day_of_week", 0)  # 0=周日, 1=周一
                st = item.get("start_time", "")
                et = item.get("end_time", "")
                repeat_weeks = item.get("repeat_weeks", 1)
                start_date_str = item.get("start_date", "")

                if not st or not et or not start_date_str:
                    continue

                dur = calc_duration_minutes(st, et)
                base_date = datetime.datetime.strptime(start_date_str[:10], "%Y-%m-%d")
                # 找到第一个符合 day_of_week 的日期
                days_ahead = dow - base_date.weekday()
                if days_ahead < 0:
                    days_ahead += 7
                first_date = base_date + datetime.timedelta(days=days_ahead)

                for w in range(repeat_weeks):
                    cur_date = first_date + datetime.timedelta(weeks=w)
                    cur_date_str = cur_date.strftime("%Y-%m-%d")
                    start_dt = cur_date_str + " " + (st if ':' in st else st + ":00")
                    end_dt = cur_date_str + " " + (et if ':' in et else et + ":00")

                    sid = execute_lastrowid(
                        """INSERT INTO schedules (lead_id, teacher_id, teacher_name, subject, start_time, end_time,
                           duration_minutes, status, remark, created_by, tutoring_form)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (int(lead_id),
                         int(teacher_id) if teacher_id else None,
                         teacher_name, subject, start_dt, end_dt,
                         dur, status, remark, uid, tutoring_form),
                    )
                    created_ids.append(sid)

        # 如果状态是 completed，统一扣课时（避免每次 INSERT 单独扣）
        if status == "completed":
            total_minutes = 0
            for item in items:
                if item.get("type") == "fixed":
                    total_minutes += calc_duration_minutes(item.get("start_time", ""), item.get("end_time", ""))
                elif item.get("type") == "weekly":
                    rw = item.get("repeat_weeks", 1)
                    dur = calc_duration_minutes(item.get("start_time", ""), item.get("end_time", ""))
                    total_minutes += dur * rw
            total_hours = round(total_minutes / 60, 1)
            if total_hours > 0:
                pkg = query_one(
                    """SELECT p.id FROM packages p
                       JOIN contracts c ON p.contract_id = c.id
                       WHERE c.lead_id=? AND c.status='active'
                       ORDER BY p.created_at ASC LIMIT 1""",
                    (int(lead_id),),
                )
                if pkg:
                    conn.execute("UPDATE packages SET used_hours = ROUND(used_hours + ?, 1) WHERE id=?", (total_hours, pkg["id"]))

        conn.commit()
    except Exception as e:
        conn.execute("ROLLBACK")
        error_response(handler, f"批量排课失败: {e}", 500)
        return

    add_oplog(uid, uname, "batch_create", "schedule", 0, f"批量排课 {len(created_ids)} 条 ({status})")
    ok_response(handler, {"count": len(created_ids), "ids": created_ids}, 201)
