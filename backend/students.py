"""签约学生管理 API — 聚合视图"""
from router import get
from utils import ok_response, csv_response
from db import query, query_one
from permissions import scope_where


@get("/api/students")
def list_students(handler, token_payload, qs, body):
    """已签约学生列表，聚合合同、课时包剩余、排课数据"""
    page = int(qs.get("page", [1])[0])
    page_size = int(qs.get("page_size", [20])[0])
    search = qs.get("search", [None])[0]
    assignee_id = qs.get("assignee_id", [None])[0]
    coordinator_id = qs.get("coordinator_id", [None])[0]

    role = token_payload["role"]
    user_id = token_payload["sub"]

    where = ["l.status='enrolled'"]
    params = []

    scope_clause, scope_params = scope_where("student", role, user_id, "l")
    where.append(scope_clause)
    params.extend(scope_params)

    if assignee_id:
        where.append("l.assignee_id=?")
        params.append(int(assignee_id))
    if coordinator_id:
        where.append("l.coordinator_id=?")
        params.append(int(coordinator_id))

    if search:
        like = f"%{search}%"
        where.append("(l.name LIKE ? OR l.phone LIKE ?)")
        params.extend([like, like])

    where_sql = " AND ".join(where)

    total = query_one(
        f"SELECT COUNT(*) as cnt FROM leads l WHERE {where_sql}", tuple(params)
    )["cnt"]

    offset = (page - 1) * page_size
    rows = query(
        f"""SELECT l.id, l.name, l.phone, l.wechat, l.source, l.country, l.grade,
                   l.remark, l.status, l.assignee_id, l.coordinator_id,
                   l.last_followup_at, l.next_followup_at, l.created_at,
                   u.display_name as assignee_name,
                   uc.display_name as coordinator_name
            FROM leads l
            LEFT JOIN users u ON l.assignee_id = u.id
            LEFT JOIN users uc ON l.coordinator_id = uc.id
            WHERE {where_sql}
            ORDER BY l.updated_at DESC
            LIMIT ? OFFSET ?""",
        tuple(params) + (page_size, offset),
    )

    # 聚合每个学生的合同、课时包、排课
    for r in rows:
        # 合同
        contracts = query(
            """SELECT id, contract_no, total_amount, status, signed_at
               FROM contracts WHERE lead_id=?
               ORDER BY created_at DESC LIMIT 1""",
            (r["id"],),
        )
        r["contract"] = contracts[0] if contracts else None

        # 课时包汇总（仅 active 合同下的）
        pkg = query_one(
            """SELECT COALESCE(SUM(p.total_hours),0) as total_hours,
                      COALESCE(SUM(p.used_hours),0) as used_hours
               FROM packages p
               JOIN contracts c ON p.contract_id = c.id
               WHERE c.lead_id=? AND c.status='active'""",
            (r["id"],),
        )
        r["total_hours"] = pkg["total_hours"] if pkg else 0
        r["used_hours"] = pkg["used_hours"] if pkg else 0
        r["remaining_hours"] = round(r["total_hours"] - r["used_hours"], 1)

        # 最近一次已上课
        r["last_class"] = query_one(
            """SELECT start_time, end_time, subject, status
               FROM schedules
               WHERE lead_id=? AND start_time <= datetime('now','localtime')
               ORDER BY start_time DESC LIMIT 1""",
            (r["id"],),
        )

        # 下一次课
        r["next_class"] = query_one(
            """SELECT start_time, end_time, subject, status
               FROM schedules
               WHERE lead_id=? AND start_time > datetime('now','localtime')
               ORDER BY start_time ASC LIMIT 1""",
            (r["id"],),
        )

        # 跟进人是否当前用户（可编辑）
        r["is_mine"] = r["assignee_id"] == user_id

    ok_response(
        handler,
        {"total": total, "page": page, "page_size": page_size, "items": rows},
    )


@get("/api/students/export")
def export_students(handler, token_payload, qs, body):
    """导出签约学生 CSV"""
    role = token_payload["role"]
    user_id = token_payload["sub"]

    where = ["l.status='enrolled'"]
    params = []
    scope_clause, scope_params = scope_where("student", role, user_id, "l")
    where.append(scope_clause)
    params.extend(scope_params)

    rows = query(
        f"""SELECT l.id, l.name, l.phone, l.source, l.country, l.grade,
                   u.display_name as assignee_name,
                   uc.display_name as coordinator_name,
                   l.created_at,
                   COALESCE((SELECT SUM(p.total_hours) FROM contracts c
                             JOIN packages p ON p.contract_id=c.id
                             WHERE c.lead_id=l.id AND c.status='active'), 0) as total_hours,
                   COALESCE((SELECT SUM(p.used_hours) FROM contracts c
                             JOIN packages p ON p.contract_id=c.id
                             WHERE c.lead_id=l.id AND c.status='active'), 0) as used_hours
            FROM leads l
            LEFT JOIN users u ON l.assignee_id = u.id
            LEFT JOIN users uc ON l.coordinator_id = uc.id
            WHERE {' AND '.join(where)}
            ORDER BY l.updated_at DESC""",
        tuple(params),
    )

    for r in rows:
        r["remaining_hours"] = round(float(r["total_hours"] or 0) - float(r["used_hours"] or 0), 1)

    columns = [
        ("id", "ID"),
        ("name", "姓名"),
        ("phone", "手机"),
        ("source", "来源"),
        ("country", "意向国家"),
        ("grade", "年级"),
        ("assignee_name", "顾问"),
        ("coordinator_name", "班主任"),
        ("total_hours", "总课时"),
        ("used_hours", "已用课时"),
        ("remaining_hours", "剩余课时"),
        ("created_at", "签约时间"),
    ]
    csv_response(handler, rows, columns, "签约学生导出.csv")
