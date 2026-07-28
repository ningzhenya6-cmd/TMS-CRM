"""
服务层 — 集中封装核心业务规则

所有重复实现的业务逻辑收敛于此，各模块引用同一份实现。
新增业务函数优先写在这里，不要在 handler 中自行推导。

当前覆盖：
  - compute_sign_type(lead_id)    → "new" | "renewal"
  - deduct_hours(lead_id, hours)  → 扣课时
  - calc_duration_minutes(start, end) → 分钟数
"""
from db import query_one, execute


# ═══════════════════════════════════════════
# 签约类型判断
# ═══════════════════════════════════════════

# 续费阈值：累计课时超过此值视为续费
RENEWAL_THRESHOLD = 10


def compute_sign_type(lead_id: int) -> str:
    """
    判断一笔新签约是新签还是续费。

    规则：该学生历史累计课时 > RENEWAL_THRESHOLD → 'renewal'，否则 'new'
    查询依据：payment_records.hours（每笔收款对应的课时数）

    这是一个纯函数，不依赖调用上下文（是否在事务内均可）。
    """
    prev = query_one(
        """SELECT COALESCE(SUM(pr.hours),0) as h
           FROM payment_records pr
           JOIN contracts c2 ON pr.contract_id = c2.id
           WHERE c2.lead_id=?""",
        (int(lead_id),),
    )
    total = prev["h"] if prev else 0
    return "renewal" if total > RENEWAL_THRESHOLD else "new"


def compute_sign_type_from_packages(lead_id: int) -> str:
    """
    根据课时包累计课时判断签约类型（历史原因：部分场景需要查 packages 表）。

    建议优先用 compute_sign_type()（payment_records 更准确）。
    """
    prev = query_one(
        """SELECT COALESCE(SUM(p.total_hours),0) as h
           FROM packages p
           JOIN contracts c ON p.contract_id = c.id
           WHERE c.lead_id=?""",
        (int(lead_id),),
    )
    total = prev["h"] if prev else 0
    return "renewal" if total > RENEWAL_THRESHOLD else "new"


# ═══════════════════════════════════════════
# 课时扣减
# ═══════════════════════════════════════════

def deduct_hours(lead_id: int, hours: float) -> bool:
    """
    从该学生第一个活跃课时包中扣除课时。

    规则：
      1. 找到该学生 status='active' 的课时包（按创建时间升序）
      2. 从第一个课时包扣减

    参数:
      lead_id: 线索 ID
      hours:   扣减的课时数

    返回:
      True  = 扣减成功（或无可扣包时不报错）
      False = 扣减量不合法
    """
    if hours <= 0:
        return False

    pkg = query_one(
        """SELECT p.id FROM packages p
           JOIN contracts c ON p.contract_id = c.id
           WHERE c.lead_id=? AND c.status='active' AND p.status='active'
           ORDER BY p.created_at ASC LIMIT 1""",
        (int(lead_id),),
    )
    if not pkg:
        return False

    execute(
        "UPDATE packages SET used_hours = ROUND(COALESCE(used_hours, 0) + ?, 1) WHERE id=?",
        (hours, pkg["id"]),
    )
    return True


def deduct_hours_from_package(package_id: int, hours: float) -> bool:
    """
    从指定课时包中扣减课时。
    """
    if hours <= 0:
        return False
    pkg = query_one("SELECT id, total_hours, used_hours FROM packages WHERE id=?", (int(package_id),))
    if not pkg:
        return False
    remaining = (pkg["total_hours"] or 0) - (pkg["used_hours"] or 0)
    if hours > remaining:
        return False
    execute(
        "UPDATE packages SET used_hours = ROUND(COALESCE(used_hours, 0) + ?, 1) WHERE id=?",
        (hours, pkg["id"]),
    )
    return True


# ═══════════════════════════════════════════
# 时长计算
# ═══════════════════════════════════════════

def calc_duration_minutes(start_time: str, end_time: str) -> int:
    """
    计算两个时间字符串之间的分钟数。

    支持格式：
      - "YYYY-MM-DD HH:MM"（完整日期时间）
      - "HH:MM"（仅时间）

    返回：
      分钟数（> 0），解析失败返回 0。
    """
    import datetime

    if not start_time or not end_time:
        return 0

    # 尝试完整格式
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            st = datetime.datetime.strptime(start_time[:16], fmt)
            et = datetime.datetime.strptime(end_time[:16], fmt)
            diff = (et - st).total_seconds() // 60
            return max(0, int(diff))
        except (ValueError, IndexError):
            continue

    # 只有 HH:MM
    if ":" in start_time and ":" in end_time:
        parts_s = start_time.strip().split(":")
        parts_e = end_time.strip().split(":")
        try:
            st_min = int(parts_s[0]) * 60 + int(parts_s[1])
            et_min = int(parts_e[0]) * 60 + int(parts_e[1])
            diff = et_min - st_min
            return max(0, diff)
        except (ValueError, IndexError):
            pass

    return 0
