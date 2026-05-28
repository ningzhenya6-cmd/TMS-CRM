"""跟进记录 API"""
from router import get, post
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid


@get("/api/followups/{lead_id}")
def list_followups(handler, token_payload, qs, body, lead_id=None):
    rows = query(
        """SELECT f.*, u.display_name as creator_name
           FROM followups f LEFT JOIN users u ON f.created_by = u.id
           WHERE f.lead_id=? ORDER BY f.created_at DESC""",
        (int(lead_id),),
    )
    ok_response(handler, rows)


@post("/api/followups")
def create_followup(handler, token_payload, qs, body):
    lead_id = body.get("lead_id")
    content = (body.get("content") or "").strip()
    if not lead_id or not content:
        error_response(handler, "参数不完整")
        return

    # 更新线索的最近跟进时间和状态
    lead = query_one("SELECT * FROM leads WHERE id=?", (lead_id,))
    if not lead:
        error_response(handler, "线索不存在", 404)
        return

    fid = execute_lastrowid(
        "INSERT INTO followups (lead_id, content, next_action, next_date, created_by) VALUES (?,?,?,?,?)",
        (lead_id, content, body.get("next_action", ""), body.get("next_date", ""), token_payload["sub"]),
    )

    # 更新线索的跟进时间和状态
    now_sql = "datetime('now','localtime')"
    execute(
        f"UPDATE leads SET status= CASE WHEN status='pending' OR status='assigned' THEN 'following' ELSE status END, "
        f"last_followup_at={now_sql}, next_followup_at=? WHERE id=?",
        (body.get("next_date", ""), lead_id),
    )

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "create", "followup", fid, f"跟进线索: {lead['name']}")

    followup = query_one(
        "SELECT f.*, u.display_name as creator_name FROM followups f LEFT JOIN users u ON f.created_by=u.id WHERE f.id=?",
        (fid,),
    )
    ok_response(handler, followup, 201)
