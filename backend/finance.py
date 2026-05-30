"""财务管理 API — 收入概览、合同统计"""
from router import get
from utils import ok_response, error_response
from db import query_one
from permissions import can


@get("/api/finance/summary")
def finance_summary(handler, token_payload, qs, body):
    """财务概览数据"""
    if not can(token_payload["role"], "finance:view"):
        error_response(handler, "无权访问", 403)
        return
    total_contracts = query_one("SELECT COUNT(*) as cnt FROM contracts")["cnt"]
    active_contracts = query_one("SELECT COUNT(*) as cnt FROM contracts WHERE status='active'")["cnt"]
    total_amount = query_one("SELECT COALESCE(SUM(total_amount),0) as s FROM contracts")["s"]
    total_paid = query_one("SELECT COALESCE(SUM(paid_amount),0) as s FROM contracts")["s"]
    total_refund = query_one(
        "SELECT COALESCE(SUM(ABS(amount)),0) as s FROM payment_records WHERE type='refund'"
    )["s"]
    total_packages = query_one("SELECT COUNT(*) as cnt FROM packages")["cnt"]
    total_hours_sold = query_one("SELECT COALESCE(SUM(total_hours),0) as h FROM packages")["h"]
    total_hours_used = query_one("SELECT COALESCE(SUM(used_hours),0) as h FROM packages")["h"]

    ok_response(handler, {
        "total_contracts": total_contracts,
        "active_contracts": active_contracts,
        "total_amount": total_amount,
        "total_paid": total_paid,
        "total_unpaid": round(total_amount - total_paid, 2),
        "total_refund": total_refund,
        "total_packages": total_packages,
        "total_hours_sold": total_hours_sold,
        "total_hours_used": total_hours_used,
    })
