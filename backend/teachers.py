"""师资管理 API — CRUD + 搜索"""
from router import get, post, put
from utils import ok_response, error_response
from db import query, query_one, execute, execute_lastrowid
from permissions import can


@get("/api/teachers")
def list_teachers(handler, token_payload, qs, body):
    """师资列表，支持搜索和筛选"""
    page = int(qs.get("page", [1])[0])
    page_size = int(qs.get("page_size", [50])[0])
    search = qs.get("search", [None])[0]
    level = qs.get("level", [None])[0]
    direction = qs.get("direction", [None])[0]

    where = ["active=1"]
    params = []

    if search:
        like = f"%{search}%"
        where.append("(name LIKE ? OR subjects LIKE ? OR teaching_direction LIKE ? OR academic_background LIKE ?)")
        params.extend([like, like, like, like])
    if level:
        where.append("level=?")
        params.append(level)
    if direction:
        where.append("teaching_direction LIKE ?")
        params.append(f"%{direction}%")

    where_sql = " AND ".join(where)

    total = query_one(f"SELECT COUNT(*) as cnt FROM teachers WHERE {where_sql}", tuple(params))["cnt"]

    offset = (page - 1) * page_size
    rows = query(
        f"SELECT * FROM teachers WHERE {where_sql} ORDER BY level, name LIMIT ? OFFSET ?",
        tuple(params) + (page_size, offset),
    )

    ok_response(handler, {"total": total, "page": page, "page_size": page_size, "items": rows})


@get("/api/teachers/levels")
def list_levels(handler, token_payload, qs, body):
    """获取所有级别选项（供筛选）"""
    rows = query("SELECT DISTINCT level FROM teachers WHERE active=1 AND level!='' ORDER BY level")
    ok_response(handler, [r["level"] for r in rows])


@get("/api/teachers/{teacher_id}")
def get_teacher(handler, token_payload, qs, body, teacher_id=None):
    t = query_one("SELECT * FROM teachers WHERE id=?", (int(teacher_id),))
    if not t:
        error_response(handler, "老师不存在", 404)
        return
    ok_response(handler, t)


@post("/api/teachers")
def create_teacher(handler, token_payload, qs, body):
    if not can(token_payload["role"], "teacher:manage"):
        error_response(handler, "无权操作", 403)
        return

    name = (body.get("name") or "").strip()
    if not name:
        error_response(handler, "老师姓名不能为空")
        return

    tid = execute_lastrowid(
        """INSERT INTO teachers
           (name, academic_background, highest_degree, subjects,
            teaching_direction, tools, teaching_style, level,
            pay_rate, payment_method, notes, phone)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            name,
            body.get("academic_background", ""),
            body.get("highest_degree", ""),
            body.get("subjects", ""),
            body.get("teaching_direction", ""),
            body.get("tools", ""),
            body.get("teaching_style", ""),
            body.get("level", ""),
            body.get("pay_rate", ""),
            body.get("payment_method", ""),
            body.get("notes", ""),
            body.get("phone", ""),
        ),
    )
    t = query_one("SELECT * FROM teachers WHERE id=?", (tid,))
    ok_response(handler, t, 201)


@put("/api/teachers/{teacher_id}")
def update_teacher(handler, token_payload, qs, body, teacher_id=None):
    if not can(token_payload["role"], "teacher:manage"):
        error_response(handler, "无权操作", 403)
        return

    tid = int(teacher_id)
    existing = query_one("SELECT id FROM teachers WHERE id=?", (tid,))
    if not existing:
        error_response(handler, "老师不存在", 404)
        return

    allowed = [
        "name", "academic_background", "highest_degree", "subjects",
        "teaching_direction", "tools", "teaching_style", "level",
        "pay_rate", "payment_method", "notes", "phone", "active",
    ]
    updates = []
    params = []
    for field in allowed:
        if field in body:
            updates.append(f"{field}=?")
            params.append(body[field])

    if updates:
        params.append(tid)
        execute(f"UPDATE teachers SET {','.join(updates)} WHERE id=?", tuple(params))

    t = query_one("SELECT * FROM teachers WHERE id=?", (tid,))
    ok_response(handler, t)

