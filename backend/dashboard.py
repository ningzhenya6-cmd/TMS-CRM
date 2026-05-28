"""仪表盘 API"""
from router import get
from utils import ok_response
from db import query_one


@get("/api/dashboard")
def dashboard(handler, token_payload, qs, body):
    role = token_payload["role"]
    user_id = token_payload["sub"]

    result = {}

    if role in ("admin", "supervisor"):
        result["pending_unassigned"] = query_one("SELECT COUNT(*) as cnt FROM leads WHERE status='pending'")["cnt"]
        result["pool_count"] = query_one("SELECT COUNT(*) as cnt FROM leads WHERE status='assigned' AND assignee_id IS NULL")["cnt"]
        result["today_followups"] = query_one(
            "SELECT COUNT(*) as cnt FROM leads WHERE next_followup_at <= datetime('now','localtime','+1 day') AND next_followup_at >= datetime('now','localtime','-1 day')",
        )["cnt"]
    elif role in ("cs", "consultant"):
        result["my_total"] = query_one("SELECT COUNT(*) as cnt FROM leads WHERE assignee_id=?", (user_id,))["cnt"]
        result["my_following"] = query_one("SELECT COUNT(*) as cnt FROM leads WHERE assignee_id=? AND status='following'", (user_id,))["cnt"]
        result["my_enrolled"] = query_one("SELECT COUNT(*) as cnt FROM leads WHERE assignee_id=? AND status='enrolled'", (user_id,))["cnt"]
        result["overdue"] = query_one(
            "SELECT COUNT(*) as cnt FROM leads WHERE assignee_id=? AND next_followup_at IS NOT NULL AND next_followup_at < datetime('now','localtime')",
            (user_id,),
        )["cnt"]
    elif role == "coordinator":
        result["pending_schedules"] = query_one("SELECT COUNT(*) as cnt FROM schedules WHERE status='pending'")["cnt"]
        result["today_classes"] = query_one(
            "SELECT COUNT(*) as cnt FROM schedules WHERE start_time >= datetime('now','localtime') AND start_time < datetime('now','localtime','+1 day')",
        )["cnt"]
    # 通用
    result["total_leads"] = query_one("SELECT COUNT(*) as cnt FROM leads")["cnt"]
    ok_response(handler, result)
