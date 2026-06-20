"""
付款 API — 收款/退款记录 + 流水查询
铁律：
  - 所有金额操作用原子 SQL（SET paid_amount = paid_amount +/- ?）
  - 跨表操作包事务（BEGIN/COMMIT/ROLLBACK）
  - 每笔操作写审计日志
  - 退款不超过已收金额
"""
import datetime
from router import get, post, delete, put
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid, get_conn
from permissions import can


@get("/api/payments/list")
def list_all_payments(handler, token_payload, qs, body):
    """所有收款记录列表，按日期倒序，附带学生/合同/课时包信息"""
    if not can(token_payload["role"], "contract:view"):
        error_response(handler, "无权访问", 403)
        return

    date_from = qs.get("date_from", [None])[0]
    date_to = qs.get("date_to", [None])[0]
    search = qs.get("search", [None])[0]

    join_clause = "LEFT JOIN contracts c ON pr.contract_id = c.id LEFT JOIN leads l ON c.lead_id = l.id"
    where = ["pr.type = 'payment'"]
    params = []

    if date_from:
        where.append("pr.payment_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("pr.payment_date <= ?")
        params.append(date_to)
    if search:
        where.append("l.name LIKE ?")
        params.append(f"%{search}%")

    where_sql = " AND ".join(where)

    rows = query(
        f"""SELECT pr.id as payment_id, pr.payment_date, pr.amount, pr.method,
                   pr.contract_id, c.lead_id, c.sign_type, c.signed_at,
                   l.name as lead_name,
                   COALESCE((SELECT SUM(p.total_hours) FROM packages p WHERE p.contract_id = pr.contract_id), 0) as total_hours
            FROM payment_records pr
            {join_clause}
            WHERE {where_sql}
            ORDER BY pr.payment_date DESC, pr.id DESC""",
        tuple(params),
    )
    ok_response(handler, rows)


@get("/api/contracts/{contract_id}/payments")
def list_payments(handler, token_payload, qs, body, contract_id=None):
    """查询某合同的付款流水"""
    if not can(token_payload["role"], "contract:view"):
        error_response(handler, "无权访问", 403)
        return
    cid = int(contract_id)
    c = query_one("SELECT id, contract_no, lead_id FROM contracts WHERE id=?", (cid,))
    if not c:
        error_response(handler, "合同不存在", 404)
        return
    rows = query(
        """SELECT p.*, u.display_name as operator_name
           FROM payment_records p
           LEFT JOIN users u ON p.operator_id = u.id
           WHERE p.contract_id = ?
           ORDER BY p.created_at ASC""",
        (cid,),
    )
    ok_response(handler, rows)


@post("/api/contracts/{contract_id}/payments")
def create_payment(handler, token_payload, qs, body, contract_id=None):
    """记录一笔收款"""
    if not can(token_payload["role"], "contract:manage"):
        error_response(handler, "无权操作", 403)
        return
    cid = int(contract_id)
    amount = float(body.get("amount", 0))
    if amount <= 0:
        error_response(handler, "收款金额必须大于 0")
        return

    c = query_one("SELECT id, total_amount, paid_amount, status FROM contracts WHERE id=?", (cid,))
    if not c:
        error_response(handler, "合同不存在", 404)
        return

    method = body.get("method", "")
    note = body.get("note", "")
    uid = token_payload["sub"]
    uname = token_payload.get("name", "")

    payment_date = body.get("payment_date", "")
    if not payment_date:
        payment_date = datetime.datetime.now().strftime("%Y-%m-%d")

    conn = get_conn()
    try:
        conn.execute("BEGIN")

        # 写入流水
        execute_lastrowid(
            "INSERT INTO payment_records (contract_id, amount, type, method, note, operator_id, payment_date) VALUES (?,?,?,?,?,?,?)",
            (cid, amount, "payment", method, note, uid, payment_date),
        )

        # 原子更新实收金额
        execute("UPDATE contracts SET paid_amount = ROUND(COALESCE(paid_amount, 0) + ?, 2) WHERE id=?", (amount, cid))

        # 检查是否收满 → 自动完成
        updated = query_one("SELECT paid_amount, total_amount FROM contracts WHERE id=?", (cid,))
        new_paid = updated["paid_amount"]
        if new_paid >= updated["total_amount"] and c["status"] != "completed":
            execute("UPDATE contracts SET status='completed' WHERE id=?", (cid,))

        conn.commit()
    except Exception as e:
        conn.execute("ROLLBACK")
        error_response(handler, f"收款失败：{e}", 500)
        return

    add_oplog(uid, uname, "payment", "contract", cid, f"收款 ¥{amount:.2f} 方式:{method}")

    contract = query_one(
        """SELECT c.*, l.name as lead_name, u.display_name as creator_name
           FROM contracts c
           LEFT JOIN leads l ON c.lead_id = l.id
           LEFT JOIN users u ON c.created_by = u.id
           WHERE c.id=?""",
        (cid,),
    )
    ok_response(handler, contract)


@post("/api/contracts/{contract_id}/refunds")
def create_refund(handler, token_payload, qs, body, contract_id=None):
    """记录一笔退款"""
    if not can(token_payload["role"], "contract:manage"):
        error_response(handler, "无权操作", 403)
        return
    cid = int(contract_id)
    amount = float(body.get("amount", 0))
    if amount <= 0:
        error_response(handler, "退款金额必须大于 0")
        return

    c = query_one("SELECT id, total_amount, paid_amount, status FROM contracts WHERE id=?", (cid,))
    if not c:
        error_response(handler, "合同不存在", 404)
        return

    paid = c["paid_amount"] or 0
    if amount > paid:
        error_response(handler, f"退款金额 ¥{amount:.2f} 超过已收金额 ¥{paid:.2f}")
        return

    reason = body.get("reason", "")
    uid = token_payload["sub"]
    uname = token_payload.get("name", "")

    conn = get_conn()
    try:
        conn.execute("BEGIN")

        # 写入流水（退款用负数记录）
        execute_lastrowid(
            "INSERT INTO payment_records (contract_id, amount, type, method, note, operator_id) VALUES (?,?,?,?,?,?)",
            (cid, -amount, "refund", "退款", reason, uid),
        )

        # 原子扣减实收金额
        execute("UPDATE contracts SET paid_amount = ROUND(COALESCE(paid_amount, 0) - ?, 2) WHERE id=?", (amount, cid))

        # 如果之前已完成，退款后退回 active
        if c["status"] == "completed":
            execute("UPDATE contracts SET status='active' WHERE id=?", (cid,))

        conn.commit()
    except Exception as e:
        conn.execute("ROLLBACK")
        error_response(handler, f"退款失败：{e}", 500)
        return

    add_oplog(uid, uname, "refund", "contract", cid, f"退款 ¥{amount:.2f} 原因:{reason}")

    contract = query_one(
        """SELECT c.*, l.name as lead_name, u.display_name as creator_name
           FROM contracts c
           LEFT JOIN leads l ON c.lead_id = l.id
           LEFT JOIN users u ON c.created_by = u.id
           WHERE c.id=?""",
        (cid,),
    )
    ok_response(handler, contract)


@put("/api/contracts/{contract_id}/payments/{payment_id}")
def update_payment(handler, token_payload, qs, body, contract_id=None, payment_id=None):
    """更新付款记录的收款日期"""
    if not can(token_payload["role"], "contract:manage"):
        error_response(handler, "无权操作", 403)
        return
    pid = int(payment_id)
    p = query_one("SELECT id FROM payment_records WHERE id=? AND contract_id=?", (pid, int(contract_id)))
    if not p:
        error_response(handler, "记录不存在", 404)
        return
    payment_date = body.get("payment_date", "")
    execute("UPDATE payment_records SET payment_date=? WHERE id=?", (payment_date, pid))
    add_oplog(token_payload["sub"], token_payload.get("name", ""), "update", "payment", pid, f"修改收款日期: {payment_date}")
    ok_response(handler, {"message": "已更新"})


@put("/api/contracts/{contract_id}/payments/{payment_id}/amount")
def update_payment_amount(handler, token_payload, qs, body, contract_id=None, payment_id=None):
    """更新付款金额（原子调整 paid_amount）"""
    if not can(token_payload["role"], "contract:manage"):
        error_response(handler, "无权操作", 403)
        return
    cid = int(contract_id)
    pid = int(payment_id)
    p = query_one("SELECT id, amount FROM payment_records WHERE id=? AND contract_id=?", (pid, cid))
    if not p:
        error_response(handler, "记录不存在", 404)
        return
    new_amt = float(body.get("amount", 0))
    old_amt = p["amount"]
    diff = new_amt - old_amt
    conn = get_conn()
    try:
        conn.execute("BEGIN")
        execute("UPDATE payment_records SET amount=? WHERE id=?", (new_amt, pid))
        execute("UPDATE contracts SET paid_amount = ROUND(COALESCE(paid_amount,0) + ?, 2) WHERE id=?", (diff, cid))
        conn.commit()
    except Exception as e:
        conn.execute("ROLLBACK")
        error_response(handler, f"修改失败：{e}", 500)
        return
    add_oplog(token_payload["sub"], token_payload.get("name", ""), "update", "payment", pid, f"收款金额 {old_amt} -> {new_amt}")
    ok_response(handler, {"message": "已更新"})


@delete("/api/contracts/{contract_id}/payments/{payment_id}")
def delete_payment(handler, token_payload, qs, body, contract_id=None, payment_id=None):
    """删除一条付款流水，原子回滚合同的 paid_amount"""
    if not can(token_payload["role"], "contract:manage"):
        error_response(handler, "无权操作", 403)
        return
    cid = int(contract_id)
    pid = int(payment_id)

    p = query_one("SELECT * FROM payment_records WHERE id=? AND contract_id=?", (pid, cid))
    if not p:
        error_response(handler, "付款记录不存在", 404)
        return

    amount = p["amount"]
    uid = token_payload["sub"]
    uname = token_payload.get("name", "")

    conn = get_conn()
    try:
        conn.execute("BEGIN")

        if amount > 0:
            # 原先的收款 → 扣减已收金额
            execute("UPDATE contracts SET paid_amount = ROUND(COALESCE(paid_amount, 0) - ?, 2) WHERE id=?", (amount, cid))
        else:
            # 原先的退款 → 加回已收金额
            execute("UPDATE contracts SET paid_amount = ROUND(COALESCE(paid_amount, 0) + ?, 2) WHERE id=?", (abs(amount), cid))

        # 删除流水
        execute("DELETE FROM payment_records WHERE id=?", (pid,))

        conn.commit()
    except Exception as e:
        conn.execute("ROLLBACK")
        error_response(handler, f"删除失败：{e}", 500)
        return

    add_oplog(uid, uname, "delete", "payment", pid, f"删除付款流水 ¥{abs(amount):.2f}")
    ok_response(handler, {"message": "已删除"})
