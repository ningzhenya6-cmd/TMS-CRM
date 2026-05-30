"""跟进记录 API"""
from router import get, post, delete
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid
from statemachine import transition_lead
from permissions import can


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
    if not can(token_payload["role"], "lead:edit"):
        error_response(handler, "无权操作", 403)
        return
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

    followup_type = body.get("followup_type", "")
    if followup_type not in ("", "电话沟通", "微信沟通", "到访面谈", "试听反馈", "续费沟通", "其他"):
        followup_type = ""
    fid = execute_lastrowid(
        "INSERT INTO followups (lead_id, content, next_action, next_date, created_by, followup_type) VALUES (?,?,?,?,?,?)",
        (lead_id, content, body.get("next_action", ""), body.get("next_date", ""), token_payload["sub"], followup_type),
    )

    # ── 通过状态机推进线索状态 ──
    if lead["status"] in ("pending", "assigned"):
        try:
            transition_lead(lead_id, "following")
        except Exception:
            pass  # 不阻塞跟进记录创建

    # 更新跟进时间
    execute(
        "UPDATE leads SET last_followup_at=datetime('now','localtime'), next_followup_at=? WHERE id=?",
        (body.get("next_date", ""), lead_id),
    )

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "create", "followup", fid, f"跟进线索: {lead['name']}")

    followup = query_one(
        "SELECT f.*, u.display_name as creator_name FROM followups f LEFT JOIN users u ON f.created_by=u.id WHERE f.id=?",
        (fid,),
    )
    ok_response(handler, followup, 201)


@delete("/api/followups/{followup_id}")
def delete_followup(handler, token_payload, qs, body, followup_id=None):
    if not can(token_payload["role"], "lead:edit"):
        error_response(handler, "无权操作", 403)
        return
    fid = int(followup_id)
    f = query_one("SELECT id FROM followups WHERE id=?", (fid,))
    if not f:
        error_response(handler, "跟进记录不存在", 404)
        return
    execute("DELETE FROM followups WHERE id=?", (fid,))
    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "delete", "followup", fid, "删除跟进记录")
    ok_response(handler, {"message": "已删除"})
