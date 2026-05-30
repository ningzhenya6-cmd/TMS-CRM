"""仪表盘 API"""
from router import get
from utils import ok_response
from db import query, query_one
from permissions import can


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
        result["overdue"] = query_one(
            "SELECT COUNT(*) as cnt FROM leads WHERE assignee_id=? AND next_followup_at IS NOT NULL AND next_followup_at < datetime('now','localtime')",
            (user_id,),
        )["cnt"]

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
        # 新分配学生
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

    # 通用
    result["total_leads"] = query_one("SELECT COUNT(*) as cnt FROM leads")["cnt"]
    ok_response(handler, result)
