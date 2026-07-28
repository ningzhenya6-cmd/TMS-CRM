"""仪表盘 API"""
from router import get
from utils import ok_response
from db import query, query_one
from permissions import can


def _date_str(sql):
    """查询 SQLite 返回单行单列"""
    from db import query_one as _q
    r = _q(f"SELECT {sql}")
    return list(r.values())[0] if r else ""

def _cur():    return _date_str("strftime('%Y-%m', 'now', 'localtime')")
def _prev():   return _date_str("strftime('%Y-%m', 'now', 'localtime', '-1 month')")
def _qstart(): return _date_str("strftime('%Y-%m', datetime('now','localtime','start of month','-2 months'))")
def _ystart(): return _date_str("strftime('%Y', 'now', 'localtime')") + "-01"


@get("/api/dashboard")
def dashboard(handler, token_payload, qs, body):
    role = token_payload["role"]
    user_id = token_payload["sub"]

    result = {}

    if can(role, "dashboard:view_admin"):
        result["pending_unassigned"] = query_one("SELECT COUNT(*) as cnt FROM leads WHERE status='pending'")["cnt"]
        result["pool_count"] = query_one("SELECT COUNT(*) as cnt FROM leads WHERE status='assigned' AND assignee_id IS NULL")["cnt"]
        result["today_followups"] = query_one(
            "SELECT COUNT(*) as cnt FROM leads WHERE next_followup_at <= datetime('now','localtime','+1 day') AND next_followup_at >= datetime('now','localtime','-1 day')",
        )["cnt"]

    if can(role, "dashboard:view_consultant"):
        result["my_total"] = query_one("SELECT COUNT(*) as cnt FROM leads WHERE assignee_id=?", (user_id,))["cnt"]
        result["my_following"] = query_one("SELECT COUNT(*) as cnt FROM leads WHERE assignee_id=? AND status='following'", (user_id,))["cnt"]
        result["my_enrolled"] = query_one("SELECT COUNT(*) as cnt FROM leads WHERE assignee_id=? AND status='enrolled'", (user_id,))["cnt"]
        result["pending_contact"] = query_one(
            "SELECT COUNT(*) as cnt FROM leads WHERE assignee_id=? AND (contact_status IN ('not_reached','follow_up') OR (contact_status='' AND (SELECT COUNT(*) FROM followups WHERE lead_id=leads.id)=0))",
            (user_id,),
        )["cnt"]
        result["overdue"] = query_one(
            "SELECT COUNT(*) as cnt FROM leads WHERE assignee_id=? AND next_followup_at IS NOT NULL AND next_followup_at < datetime('now','localtime')",
            (user_id,),
        )["cnt"]

    # ── 待办行动项（按角色隔离） ──
    _scope_user = user_id
    _scope_field = "assignee_id"
    if role == "coordinator":
        _scope_field = "coordinator_id"
    scope_sql = "l." + _scope_field + "=?"
    scope_params = (_scope_user,)

    if role in ("admin", "supervisor"):
        result["action_new_leads"] = query(
            "SELECT l.id, l.name, l.phone, l.source, l.created_at, l.remark, u.display_name as assignee_name FROM leads l LEFT JOIN users u ON l.assignee_id = u.id WHERE l.last_followup_at IS NULL AND l.status NOT IN ('enrolled','closed','lost') ORDER BY l.created_at DESC LIMIT 20")
        result["action_overdue"] = query(
            "SELECT l.id, l.name, l.phone, l.lead_rank, l.next_followup_at, u.display_name as assignee_name, (SELECT f.content FROM followups f WHERE f.lead_id=l.id ORDER BY f.created_at DESC LIMIT 1) as last_content FROM leads l LEFT JOIN users u ON l.assignee_id = u.id WHERE l.next_followup_at IS NOT NULL AND l.next_followup_at != '' AND l.next_followup_at < datetime('now','localtime') AND l.status NOT IN ('enrolled','closed','lost') AND COALESCE(l.followup_paused, 0)=0 ORDER BY l.next_followup_at ASC LIMIT 20")
        result["action_today"] = query(
            "SELECT l.id, l.name, l.phone, l.lead_rank, l.next_followup_at, u.display_name as assignee_name FROM leads l LEFT JOIN users u ON l.assignee_id = u.id WHERE l.next_followup_at >= datetime('now','localtime','start of day') AND l.next_followup_at < datetime('now','localtime','+1 day','start of day') AND l.status NOT IN ('enrolled','closed','lost') ORDER BY l.next_followup_at ASC LIMIT 20")
    else:
        result["action_new_leads"] = query(
            "SELECT l.id, l.name, l.phone, l.source, l.created_at, l.remark FROM leads l WHERE l.last_followup_at IS NULL AND l.status NOT IN ('enrolled','closed','lost') AND " + scope_sql + " ORDER BY l.created_at DESC LIMIT 20", scope_params)
        result["action_overdue"] = query(
            "SELECT l.id, l.name, l.phone, l.lead_rank, l.next_followup_at, (SELECT f.content FROM followups f WHERE f.lead_id=l.id ORDER BY f.created_at DESC LIMIT 1) as last_content FROM leads l WHERE l.next_followup_at IS NOT NULL AND l.next_followup_at != '' AND l.next_followup_at < datetime('now','localtime') AND l.status NOT IN ('enrolled','closed','lost') AND COALESCE(l.followup_paused,0)=0 AND " + scope_sql + " ORDER BY l.next_followup_at ASC LIMIT 20", scope_params)
        result["action_today"] = query(
            "SELECT l.id, l.name, l.phone, l.lead_rank, l.next_followup_at FROM leads l WHERE l.next_followup_at >= datetime('now','localtime','start of day') AND l.next_followup_at < datetime('now','localtime','+1 day','start of day') AND l.status NOT IN ('enrolled','closed','lost') AND " + scope_sql + " ORDER BY l.next_followup_at ASC LIMIT 20", scope_params)

    if can(role, "dashboard:view_academic"):
        result["need_renewal"] = query_one(
            """SELECT COUNT(*) as cnt FROM (
               SELECT l.id FROM leads l
               JOIN contracts c ON l.id=c.lead_id AND c.status='active'
               JOIN packages p ON p.contract_id=c.id
               WHERE l.assignee_id=? AND l.status='enrolled'
               GROUP BY l.id
               HAVING COALESCE(SUM(p.total_hours),0) - COALESCE(SUM(p.used_hours),0) <= 5
            )""",
            (user_id,),
        )["cnt"]

    if can(role, "dashboard:view_coordinator"):
        result["pending_schedules"] = query_one("SELECT COUNT(*) as cnt FROM schedules WHERE status='pending'")["cnt"]
        result["today_classes"] = query_one(
            "SELECT COUNT(*) as cnt FROM schedules WHERE start_time >= datetime('now','localtime') AND start_time < datetime('now','localtime','+1 day')",
        )["cnt"]
        result["my_students"] = query_one(
            "SELECT COUNT(*) as cnt FROM leads WHERE coordinator_id=? AND status='enrolled'",
            (user_id,),
        )["cnt"]
        result["my_pending_schedules"] = query_one(
            """SELECT COUNT(*) as cnt FROM schedules s
               JOIN leads l ON s.lead_id = l.id
               WHERE l.coordinator_id=? AND s.status='pending'""",
            (user_id,),
        )["cnt"]
        result["newly_assigned_students"] = query(
            """SELECT l.id, l.name, l.phone, l.coordinator_at,
                      COALESCE((SELECT SUM(p.total_hours) FROM contracts c
                                JOIN packages p ON p.contract_id=c.id
                                WHERE c.lead_id=l.id AND c.status='active'), 0) as total_hours,
                      COALESCE((SELECT SUM(p.used_hours) FROM contracts c
                                JOIN packages p ON p.contract_id=c.id
                                WHERE c.lead_id=l.id AND c.status='active'), 0) as used_hours
               FROM leads l
               WHERE l.coordinator_id=? AND l.status='enrolled'
                 AND l.coordinator_at IS NOT NULL
               ORDER BY l.coordinator_at DESC
               LIMIT 20""",
            (user_id,),
        )

    # ═══════════════════════════════════════
    #  通用统计看板
    # ═══════════════════════════════════════

    cur, prev = _cur(), _prev()
    qstart, ystart = _qstart(), _ystart()

    # 本月/上月新录入
    result["leads_this_month"] = query_one(
        "SELECT COUNT(*) as cnt FROM leads WHERE strftime('%Y-%m', created_at) = ?", (cur,))["cnt"]
    result["leads_last_month"] = query_one(
        "SELECT COUNT(*) as cnt FROM leads WHERE strftime('%Y-%m', created_at) = ?", (prev,))["cnt"]

    # ABC 等级（只统计未签约的）
    not_enrolled = "status NOT IN ('enrolled','closed','lost')"
    result["rank_a"] = query_one(f"SELECT COUNT(*) as cnt FROM leads WHERE lead_rank='A' AND {not_enrolled}")["cnt"]
    result["rank_b"] = query_one(f"SELECT COUNT(*) as cnt FROM leads WHERE lead_rank='B' AND {not_enrolled}")["cnt"]
    result["rank_c"] = query_one(f"SELECT COUNT(*) as cnt FROM leads WHERE lead_rank='C' AND {not_enrolled}")["cnt"]
    result["rank_a_last"] = query_one(
        f"SELECT COUNT(*) as cnt FROM leads WHERE lead_rank='A' AND strftime('%Y-%m', updated_at)=? AND {not_enrolled}", (prev,))["cnt"]
    result["rank_b_last"] = query_one(
        f"SELECT COUNT(*) as cnt FROM leads WHERE lead_rank='B' AND strftime('%Y-%m', updated_at)=? AND {not_enrolled}", (prev,))["cnt"]
    result["rank_c_last"] = query_one(
        f"SELECT COUNT(*) as cnt FROM leads WHERE lead_rank='C' AND strftime('%Y-%m', updated_at)=? AND {not_enrolled}", (prev,))["cnt"]

    # ── 本月签约明细 ──
    # 核心原则：签约数据用 signed_at（实际签约日期），收款数据用 payment_date（实际收款日期）
    # 不能用 created_at（录入时间），否则跨月录入的数据会计入错误月份
    signed_where = "strftime('%Y-%m', COALESCE(NULLIF(signed_at,''), created_at))=?"
    pay_where = "strftime('%Y-%m', COALESCE(NULLIF(payment_date,''), created_at))=?"
    result["contracts_this_month"] = query_one(f"SELECT COUNT(*) as cnt FROM contracts WHERE {signed_where}", (cur,))["cnt"]
    result["payments_this_month"] = query_one(f"SELECT COUNT(*) as cnt FROM payment_records WHERE type='payment' AND {pay_where}", (cur,))["cnt"]
    result["new_sign_this_month"] = query_one(
        f"SELECT COUNT(*) as cnt FROM payment_records WHERE type='payment' AND {pay_where} AND sign_type='new'", (cur,))["cnt"]
    result["renewal_this_month"] = query_one(
        f"SELECT COUNT(*) as cnt FROM payment_records WHERE type='payment' AND {pay_where} AND sign_type='renewal'", (cur,))["cnt"]
    result["enrolled_this_month"] = query_one(f"SELECT COUNT(DISTINCT lead_id) as cnt FROM contracts WHERE {signed_where}", (cur,))["cnt"]
    result["hours_this_month"] = query_one(
        f"SELECT COALESCE(SUM(pr.hours),0) as total FROM payment_records pr WHERE pr.type='payment' AND {pay_where}", (cur,))["total"]
    # 新签/续费流水（按收款日期统计）
    result["new_sign_amt"] = query_one(
        f"SELECT COALESCE(SUM(amount),0) as total FROM payment_records WHERE type='payment' AND {pay_where} AND sign_type='new'", (cur,))["total"]
    result["renewal_amt"] = query_one(
        f"SELECT COALESCE(SUM(amount),0) as total FROM payment_records WHERE type='payment' AND {pay_where} AND sign_type='renewal'", (cur,))["total"]

    # 上月签约
    result["contracts_last_month"] = query_one(f"SELECT COUNT(*) as cnt FROM contracts WHERE {signed_where}", (prev,))["cnt"]
    result["new_sign_last_month"] = query_one(
        f"SELECT COUNT(*) as cnt FROM payment_records WHERE type='payment' AND {pay_where} AND sign_type='new'", (prev,))["cnt"]
    result["renewal_last_month"] = query_one(
        f"SELECT COUNT(*) as cnt FROM payment_records WHERE type='payment' AND {pay_where} AND sign_type='renewal'", (prev,))["cnt"]

    # ── 季度汇总 ──
    result["quarter_amt"] = query_one(
        "SELECT COALESCE(SUM(amount),0) as total FROM payment_records WHERE type='payment' AND strftime('%Y-%m', COALESCE(NULLIF(payment_date,''), created_at)) BETWEEN ? AND ?", (qstart, cur))["total"]
    result["quarter_new_amt"] = query_one(
        "SELECT COALESCE(SUM(amount),0) as total FROM payment_records WHERE type='payment' AND sign_type='new' AND strftime('%Y-%m', COALESCE(NULLIF(payment_date,''), created_at)) BETWEEN ? AND ?", (qstart, cur))["total"]
    result["quarter_renewal_amt"] = query_one(
        "SELECT COALESCE(SUM(amount),0) as total FROM payment_records WHERE type='payment' AND sign_type='renewal' AND strftime('%Y-%m', COALESCE(NULLIF(payment_date,''), created_at)) BETWEEN ? AND ?", (qstart, cur))["total"]
    result["quarter_students"] = query_one(
        "SELECT COUNT(DISTINCT c.lead_id) as cnt FROM payment_records pr JOIN contracts c ON pr.contract_id=c.id WHERE pr.type='payment' AND strftime('%Y-%m', COALESCE(NULLIF(pr.payment_date,''), pr.created_at)) BETWEEN ? AND ?", (qstart, cur))["cnt"]
    result["quarter_hours"] = query_one(
        "SELECT COALESCE(SUM(pr.hours),0) as total FROM payment_records pr WHERE pr.type='payment' AND strftime('%Y-%m', COALESCE(NULLIF(pr.payment_date,''), pr.created_at)) BETWEEN ? AND ?", (qstart, cur))["total"]

    # ── 年度汇总 ──
    result["year_amt"] = query_one("SELECT COALESCE(SUM(amount),0) as total FROM payment_records WHERE type='payment' AND strftime('%Y-%m', COALESCE(NULLIF(payment_date,''), created_at)) >= ?", (ystart,))["total"]
    result["year_new_amt"] = query_one(
        "SELECT COALESCE(SUM(amount),0) as total FROM payment_records WHERE type='payment' AND sign_type='new' AND strftime('%Y-%m', COALESCE(NULLIF(payment_date,''), created_at)) >= ?", (ystart,))["total"]
    result["year_renewal_amt"] = query_one(
        "SELECT COALESCE(SUM(amount),0) as total FROM payment_records WHERE type='payment' AND sign_type='renewal' AND strftime('%Y-%m', COALESCE(NULLIF(payment_date,''), created_at)) >= ?", (ystart,))["total"]
    result["year_students"] = query_one(
        "SELECT COUNT(DISTINCT c.lead_id) as cnt FROM payment_records pr JOIN contracts c ON pr.contract_id=c.id WHERE pr.type='payment' AND strftime('%Y-%m', COALESCE(NULLIF(pr.payment_date,''), pr.created_at)) >= ?", (ystart,))["cnt"]
    result["year_hours"] = query_one(
        "SELECT COALESCE(SUM(pr.hours),0) as total FROM payment_records pr WHERE pr.type='payment' AND strftime('%Y-%m', COALESCE(NULLIF(pr.payment_date,''), pr.created_at)) >= ?", (ystart,))["total"]

    # 收款
    result["paid_this_month"] = query_one(
        "SELECT COALESCE(SUM(amount),0) as total FROM payment_records WHERE type='payment' AND strftime('%Y-%m', COALESCE(NULLIF(payment_date,''), created_at)) = ?", (cur,))["total"]
    result["paid_last_month"] = query_one(
        "SELECT COALESCE(SUM(amount),0) as total FROM payment_records WHERE type='payment' AND strftime('%Y-%m', COALESCE(NULLIF(payment_date,''), created_at)) = ?", (prev,))["total"]
    result["total_paid"] = query_one("SELECT COALESCE(SUM(amount),0) as total FROM payment_records WHERE type='payment'")["total"]
    result["enrolled_count"] = query_one("SELECT COUNT(*) as cnt FROM leads WHERE status='enrolled'")["cnt"]
    result["total_leads"] = query_one("SELECT COUNT(*) as cnt FROM leads")["cnt"]

    ok_response(handler, result)
