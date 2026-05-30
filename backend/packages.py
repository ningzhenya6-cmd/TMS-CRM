"""课时包 API — CRUD + 课时使用记录"""
from router import get, post, put, delete
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid
from permissions import can


@get("/api/packages")
def list_packages(handler, token_payload, qs, body):
    contract_id = qs.get("contract_id", [None])[0]
    status = qs.get("status", [None])[0]
    lead_id = qs.get("lead_id", [None])[0]

    where = ["1=1"]
    params = []
    if contract_id:
        where.append("p.contract_id=?")
        params.append(int(contract_id))
    if status:
        where.append("p.status=?")
        params.append(status)
    if lead_id:
        where.append("c.lead_id=?")
        params.append(int(lead_id))

    join = ""
    if lead_id:
        join = "JOIN contracts c ON p.contract_id = c.id"

    where_sql = " AND ".join(where)
    rows = query(
        f"""SELECT p.*, c.lead_id, l.name as lead_name
            FROM packages p
            {join}
            LEFT JOIN contracts c ON p.contract_id = c.id
            LEFT JOIN leads l ON c.lead_id = l.id
            WHERE {where_sql}
            ORDER BY p.created_at DESC""",
        tuple(params),
    )
    ok_response(handler, rows)


@post("/api/packages")
def create_package(handler, token_payload, qs, body):
    if not can(token_payload["role"], "package:manage"):
        error_response(handler, "无权操作", 403)
        return
    contract_id = body.get("contract_id")
    if not contract_id:
        error_response(handler, "缺少合同信息")
        return
    name = body.get("name", "")
    if not name:
        name = "标准课时包"
    pid = execute_lastrowid(
        """INSERT INTO packages (contract_id, name, total_hours, used_hours, price_per_hour, status, remark)
           VALUES (?,?,?,?,?,?,?)""",
        (
            int(contract_id),
            name,
            float(body.get("total_hours", 0)),
            float(body.get("used_hours", 0)),
            float(body.get("price_per_hour", 0)),
            body.get("status", "active"),
            body.get("remark", ""),
        ),
    )
    add_oplog(token_payload["sub"], token_payload.get("name", ""), "create", "package", pid, f"创建课时包: {name}")
    p = query_one("SELECT * FROM packages WHERE id=?", (pid,))
    ok_response(handler, p, 201)


@put("/api/packages/{package_id}")
def update_package(handler, token_payload, qs, body, package_id=None):
    if not can(token_payload["role"], "package:manage"):
        error_response(handler, "无权操作", 403)
        return
    pid = int(package_id)
    existing = query_one("SELECT * FROM packages WHERE id=?", (pid,))
    if not existing:
        error_response(handler, "课时包不存在", 404)
        return
    allowed = ["name", "total_hours", "used_hours", "price_per_hour", "status", "remark"]
    updates = []
    params = []
    for field in allowed:
        if field in body:
            updates.append(f"{field}=?")
            params.append(body[field])
    if not updates:
        error_response(handler, "没有需要更新的字段")
        return
    params.append(pid)
    execute(f"UPDATE packages SET {','.join(updates)} WHERE id=?", tuple(params))
    add_oplog(token_payload["sub"], token_payload.get("name", ""), "update", "package", pid, "更新课时包")
    updated = query_one("SELECT * FROM packages WHERE id=?", (pid,))
    ok_response(handler, updated)


@post("/api/packages/{package_id}/use")
def use_package_hours(handler, token_payload, qs, body, package_id=None):
    """消耗课时"""
    if not can(token_payload["role"], "package:manage"):
        error_response(handler, "无权操作", 403)
        return
    pid = int(package_id)
    pkg = query_one("SELECT * FROM packages WHERE id=?", (pid,))
    if not pkg:
        error_response(handler, "课时包不存在", 404)
        return
    hours = float(body.get("hours", 0))
    if hours <= 0:
        error_response(handler, "消耗课时必须大于0")
        return
    remaining = pkg["total_hours"] - pkg["used_hours"]
    if hours > remaining:
        error_response(handler, f"剩余课时不足 (剩余 {remaining} 小时)")
        return
    execute("UPDATE packages SET used_hours = used_hours + ? WHERE id=?", (hours, pid))
    add_oplog(token_payload["sub"], token_payload.get("name", ""), "use", "package", pid,
              f"消耗课时: {hours}h (剩余: {remaining - hours}h)")
    updated = query_one("SELECT * FROM packages WHERE id=?", (pid,))
    ok_response(handler, updated)
