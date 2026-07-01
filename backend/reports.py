"""统计报表 API — 课时统计 / 月度趋势（按角色隔离）"""
from router import get
from utils import ok_response
from db import query, query_one
from permissions import can, scope_where


@get("/api/reports/hour-summary")
def hour_summary(handler, token_payload, qs, body):
    """课时总览：签约课时/已排课时/剩余课时（按角色隔离）
       coordinator → 自己名下的学生
       admin/supervisor → 全部
    """
    role = token_payload["role"]
    user_id = token_payload["sub"]

    scope_clause, scope_params = scope_where("lead", role, user_id, "l")

    contracted = query_one(
        f"""SELECT COALESCE(SUM(p.total_hours),0) as h
            FROM packages p
            JOIN contracts c ON p.contract_id = c.id
            JOIN leads l ON c.lead_id = l.id
            WHERE p.status='active' AND {scope_clause}""",
        tuple(scope_params),
    )["h"]

    scheduled = query_one(
        f"""SELECT COALESCE(SUM(
            CASE WHEN s.actual_duration_minutes > 0 THEN s.actual_duration_minutes
                 ELSE s.duration_minutes END
        ), 0) / 60.0 as h
        FROM schedules s
        JOIN leads l ON s.lead_id = l.id
        WHERE s.status != 'cancelled' AND {scope_clause}""",
        tuple(scope_params),
    )["h"]

    remaining = round(contracted - scheduled, 1)
    if remaining < 0: remaining = 0

    ok_response(handler, {
        "contracted_hours": round(contracted, 1),
        "scheduled_hours": round(scheduled, 1),
        "remaining_hours": remaining,
    })


@get("/api/reports/hour-monthly")
def hour_monthly(handler, token_payload, qs, body):
    """月度趋势：近6个月逐月签约/已排/未排课时（仅admin/supervisor）"""
    role = token_payload["role"]
    if not can(role, "dashboard:view_admin"):
        ok_response(handler, {"months": []})
        return

    user_id = token_payload["sub"]
    scope_clause, scope_params = scope_where("lead", role, user_id, "l")

    from datetime import datetime, timedelta
    now = datetime.now()
    months = []
    for i in range(5, -1, -1):
        ym = (now.replace(day=1) - timedelta(days=30 * i)).strftime("%Y-%m")
        months.append(ym)

    rows = []
    for ym in months:
        signed = query_one(
            """SELECT COALESCE(SUM(pr.hours),0) as h
               FROM payment_records pr
               JOIN contracts c ON pr.contract_id = c.id
               JOIN leads l ON c.lead_id = l.id
               WHERE pr.type='payment'
                 AND strftime('%Y-%m', COALESCE(NULLIF(pr.payment_date,''), pr.created_at)) = ?
                 AND """ + scope_clause,
            tuple([ym] + scope_params),
        )["h"]

        scheduled = query_one(
            f"""SELECT COALESCE(SUM(
                CASE WHEN s.actual_duration_minutes > 0 THEN s.actual_duration_minutes
                     ELSE s.duration_minutes END
            ), 0) / 60.0 as h
            FROM schedules s
            JOIN leads l ON s.lead_id = l.id
            WHERE s.status != 'cancelled'
              AND strftime('%Y-%m', s.start_time) = ?
              AND {scope_clause}""",
            tuple([ym] + scope_params),
        )["h"]

        rows.append({
            "month": ym,
            "signed_hours": round(signed, 1),
            "scheduled_hours": round(scheduled, 1),
        })

    ok_response(handler, {"months": rows})
