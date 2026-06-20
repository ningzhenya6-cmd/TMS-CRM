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
    date_from = qs.get("date_from", [None])[0]
    date_to = qs.get("date_to", [None])[0]
    search = qs.get("search", [None])[0]

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
    sign_type = "renewal" if prev_hours > 10 else "new"

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
    # 强制更新为已签约状态（不经过状态机，因为外部导入的线索可能从pending直接签约）
    execute("UPDATE leads SET status='enrolled' WHERE id=?", (int(lead_id),))

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
    allowed = ["contract_no", "total_amount", "status", "signed_at", "remark", "lead_id", "sign_type"]
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
    c = query_one("SELECT id, contract_no, lead_id FROM contracts WHERE id=?", (cid,))
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

    # 删除合同后检查该线索是否还有剩余合同，没有则回退签约状态
    lid = c.get("lead_id")
    if lid:
        remaining = query_one("SELECT COUNT(*) as cnt FROM contracts WHERE lead_id=?", (lid,))
        if not remaining or remaining["cnt"] == 0:
            execute("UPDATE leads SET status='assigned' WHERE id=? AND status='enrolled'", (lid,))

    ok_response(handler, {"message": "已删除"})


@post("/api/signing")
def create_signing(handler, token_payload, qs, body):
    """一键签约：创建合同 + 课时包 + 收款，一个事务"""
    if not can(token_payload["role"], "contract:manage"):
        error_response(handler, "无权操作", 403)
        return

    lead_id = body.get("lead_id")
    if not lead_id:
        error_response(handler, "缺少学生信息")
        return

    total_hours = float(body.get("total_hours", 0))
    if total_hours <= 0:
        error_response(handler, "总课时必须大于 0")
        return

    payment_amount = float(body.get("payment_amount", 0))
    if payment_amount <= 0:
        error_response(handler, "收款金额必须大于 0")
        return

    # 计算新签/续费：该学生已有合同下课时包的总课时
    prev_hours = query_one(
        """SELECT COALESCE(SUM(p.total_hours),0) as h
           FROM packages p
           JOIN contracts c ON p.contract_id = c.id
           WHERE c.lead_id=?""",
        (int(lead_id),),
    )["h"]
    sign_type = "renewal" if prev_hours > 10 else "new"

    signed_at = body.get("signed_at", "")
    if not signed_at:
        signed_at = __import__("datetime").datetime.now().strftime("%Y-%m-%d")

    payment_date = body.get("payment_date", "")
    if not payment_date:
        payment_date = signed_at

    uid = token_payload["sub"]
    uname = token_payload.get("name", "")

    conn = get_conn()
    try:
        conn.execute("BEGIN")

        # 1. 创建合同
        cid = execute_lastrowid(
            """INSERT INTO contracts (lead_id, contract_no, total_amount, status, signed_at, remark, created_by, sign_type, paid_amount)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                int(lead_id),
                body.get("contract_no", ""),
                payment_amount,  # total_amount = 收款金额（合同金额由收款决定）
                body.get("status", "active"),
                signed_at,
                body.get("remark", ""),
                uid,
                sign_type,
                payment_amount,  # 首笔收款直接计入 paid_amount
            ),
        )

        # 2. 创建课时包
        pid = execute_lastrowid(
            """INSERT INTO packages (contract_id, name, total_hours, used_hours, price_per_hour, status, remark)
               VALUES (?,?,?,?,?,?,?)""",
            (
                cid,
                body.get("package_name", "") or "标准课时包",
                total_hours,
                0,
                float(body.get("price_per_hour", 0)),
                "active",
                "",
            ),
        )

        # 3. 创建收款记录（每笔收款独立记录课时）
        pay_id = execute_lastrowid(
            """INSERT INTO payment_records (contract_id, amount, type, method, note, operator_id, payment_date, hours)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                cid,
                payment_amount,
                "payment",
                body.get("payment_method", ""),
                body.get("note", ""),
                uid,
                payment_date,
                total_hours,
            ),
        )

        # 4. 更新学生状态为已签约
        execute("UPDATE leads SET status='enrolled' WHERE id=?", (int(lead_id),))

        conn.commit()
    except Exception as e:
        conn.execute("ROLLBACK")
        error_response(handler, f"签约失败：{e}", 500)
        return

    add_oplog(uid, uname, "signing", "contract", cid, f"一键签约 {sign_type} · {total_hours}h · ¥{payment_amount:.2f}")

    # 返回完整数据
    contract = query_one("SELECT * FROM contracts WHERE id=?", (cid,))
    package = query_one("SELECT * FROM packages WHERE id=?", (pid,))
    payment = query_one("SELECT * FROM payment_records WHERE id=?", (pay_id,))
    lead = query_one("SELECT id, name, phone FROM leads WHERE id=?", (int(lead_id),))

    ok_response(handler, {
        "contract": contract,
        "package": package,
        "payment": payment,
        "lead_name": lead["name"] if lead else "",
        "sign_type": sign_type,
    }, 201)


@post("/api/contracts/refresh-sign-types")
def refresh_sign_types(handler, token_payload, qs, body):
    """根据实际累计课时重新计算所有合同的 sign_type
       规则: 同一学生下，签该合同时已有累计 > 10 课时 → renewal，否则 → new
    """
    if not can(token_payload["role"], "contract:manage"):
        error_response(handler, "无权操作", 403)
        return

    contracts = query(
        """SELECT c.id, c.lead_id, c.sign_type, c.signed_at
           FROM contracts c ORDER BY c.lead_id, c.signed_at ASC"""
    )

    updated = 0
    lead_hours = {}  # lead_id -> cumulative hours so far

    for c in contracts:
        cid = c["id"]
        lid = c["lead_id"]
        prior = lead_hours.get(lid, 0)
        should = "renewal" if prior > 10 else "new"

        if c["sign_type"] != should:
            execute("UPDATE contracts SET sign_type=? WHERE id=?", (should, cid))
            updated += 1

        # 累加当前合同的课时供后续合同判断
        cur_hrs = query_one(
            "SELECT COALESCE(SUM(total_hours),0) as h FROM packages WHERE contract_id=?",
            (cid,),
        )["h"]
        lead_hours[lid] = prior + cur_hrs

    uid = token_payload["sub"]
    uname = token_payload.get("name", "")
    add_oplog(uid, uname, "refresh", "contract", 0, f"重算 sign_type，修正 {updated} 条")

    ok_response(handler, {"updated": updated, "message": f"已重算，{updated} 条合同类型已修正"})
