"""合同 API — CRUD"""
from router import get, post, put, delete
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid, get_conn
from statemachine import transition_lead
from permissions import can


@get("/api/contracts")
def list_contracts(handler, token_payload, qs, body):
    if not can(token_payload["role"], "contract:view"):
        error_response(handler, "无权访问", 403)
        return
    page = int(qs.get("page", [1])[0])
    page_size = int(qs.get("page_size", [20])[0])
    lead_id = qs.get("lead_id", [None])[0]
    status = qs.get("status", [None])[0]

    where = ["1=1"]
    params = []
    if lead_id:
        where.append("c.lead_id=?")
        params.append(int(lead_id))
    if status:
        where.append("c.status=?")
        params.append(status)

    where_sql = " AND ".join(where)
    total = query_one(f"SELECT COUNT(*) as cnt FROM contracts c WHERE {where_sql}", tuple(params))["cnt"]

    offset = (page - 1) * page_size
    rows = query(
        f"""SELECT c.*, l.name as lead_name, u.display_name as creator_name
            FROM contracts c
            LEFT JOIN leads l ON c.lead_id = l.id
            LEFT JOIN users u ON c.created_by = u.id
            WHERE {where_sql}
            ORDER BY c.created_at DESC
            LIMIT ? OFFSET ?""",
        tuple(params) + (page_size, offset),
    )
    # Attach package count
    for r in rows:
        r["package_count"] = query_one("SELECT COUNT(*) as cnt FROM packages WHERE contract_id=?", (r["id"],))["cnt"]
        r["total_hours"] = query_one("SELECT COALESCE(SUM(total_hours),0) as h FROM packages WHERE contract_id=?", (r["id"],))["h"]

    ok_response(handler, {"total": total, "page": page, "page_size": page_size, "items": rows})


@get("/api/contracts/{contract_id}")
def get_contract(handler, token_payload, qs, body, contract_id=None):
    if not can(token_payload["role"], "contract:view"):
        error_response(handler, "无权访问", 403)
        return
    c = query_one(
        """SELECT c.*, l.name as lead_name, u.display_name as creator_name
           FROM contracts c LEFT JOIN leads l ON c.lead_id=l.id LEFT JOIN users u ON c.created_by=u.id
           WHERE c.id=?""",
        (int(contract_id),),
    )
    if not c:
        error_response(handler, "合同不存在", 404)
        return
    # Attach packages
    c["packages"] = query(
        "SELECT * FROM packages WHERE contract_id=? ORDER BY created_at ASC", (c["id"],)
    )
    ok_response(handler, c)


@post("/api/contracts")
def create_contract(handler, token_payload, qs, body):
    if not can(token_payload["role"], "contract:manage"):
        error_response(handler, "无权操作", 403)
        return
    lead_id = body.get("lead_id")
    if not lead_id:
        error_response(handler, "缺少学生信息")
        return

    # 计算新签/续费
    # 查该学生所有已有合同下课时包的总课时
    prev_hours = query_one(
        """SELECT COALESCE(SUM(p.total_hours),0) as h
           FROM packages p
           JOIN contracts c ON p.contract_id = c.id
           WHERE c.lead_id=?""",
        (int(lead_id),),
    )["h"]
    sign_type = "renewal" if prev_hours >= 10 else "new"

    cid = execute_lastrowid(
        """INSERT INTO contracts (lead_id, contract_no, total_amount, status, signed_at, remark, created_by, sign_type)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            int(lead_id),
            body.get("contract_no", ""),
            float(body.get("total_amount", 0)),
            body.get("status", "active"),
            body.get("signed_at", ""),
            body.get("remark", ""),
            token_payload["sub"],
            sign_type,
        ),
    )
    add_oplog(token_payload["sub"], token_payload.get("name", ""), "create", "contract", cid, "创建合同")

    # 通过状态机将线索推进为"已签约"
    try:
        transition_lead(int(lead_id), "enrolled")
    except Exception:
        pass  # 合同已创建，不阻塞

    c = query_one("SELECT * FROM contracts WHERE id=?", (cid,))
    ok_response(handler, c, 201)


@put("/api/contracts/{contract_id}")
def update_contract(handler, token_payload, qs, body, contract_id=None):
    if not can(token_payload["role"], "contract:manage"):
        error_response(handler, "无权操作", 403)
        return
    cid = int(contract_id)
    existing = query_one("SELECT * FROM contracts WHERE id=?", (cid,))
    if not existing:
        error_response(handler, "合同不存在", 404)
        return
    allowed = ["contract_no", "total_amount", "status", "signed_at", "remark", "lead_id"]
    updates = []
    params = []
    for field in allowed:
        if field in body:
            updates.append(f"{field}=?")
            params.append(body[field])
    if not updates:
        error_response(handler, "没有需要更新的字段")
        return
    params.append(cid)
    execute(f"UPDATE contracts SET {','.join(updates)} WHERE id=?", tuple(params))
    add_oplog(token_payload["sub"], token_payload.get("name", ""), "update", "contract", cid, "更新合同")
    updated = query_one("SELECT * FROM contracts WHERE id=?", (cid,))
    ok_response(handler, updated)


@delete("/api/contracts/{contract_id}")
def delete_contract(handler, token_payload, qs, body, contract_id=None):
    if not can(token_payload["role"], "contract:manage"):
        error_response(handler, "无权操作", 403)
        return
    cid = int(contract_id)
    c = query_one("SELECT id, contract_no FROM contracts WHERE id=?", (cid,))
    if not c:
        error_response(handler, "合同不存在", 404)
        return

    conn = get_conn()
    try:
        conn.execute("BEGIN")
        # 先删付款流水（无 ON DELETE CASCADE）
        execute("DELETE FROM payment_records WHERE contract_id=?", (cid,))
        # 再删课时包（有 CASCADE 但显式删除更安全）
        execute("DELETE FROM packages WHERE contract_id=?", (cid,))
        # 最后删合同
        execute("DELETE FROM contracts WHERE id=?", (cid,))
        conn.commit()
    except Exception as e:
        conn.execute("ROLLBACK")
        error_response(handler, f"删除失败：{e}", 500)
        return

    add_oplog(token_payload["sub"], token_payload.get("name", ""), "delete", "contract", cid, f"删除合同: {c['contract_no']}")
    ok_response(handler, {"message": "已删除"})
