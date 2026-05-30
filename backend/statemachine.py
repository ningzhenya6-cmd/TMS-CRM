"""
状态机引擎 — 线索生命周期合法性校验
所有 leads.status 变更必须经过此模块，不能直接 UPDATE
"""
from db import query_one, execute


class InvalidTransition(Exception):
    """非法状态转换"""
    pass


# ── 合法转换表 ──
# key = from_status, value = set of allowed to_status
_TRANSITIONS = {
    "pending":   {"assigned", "closed"},
    "assigned":  {"following", "pending", "closed"},
    "following": {"trial", "enrolled", "closed", "lost"},
    "trial":     {"following", "enrolled", "lost"},
    "enrolled":  {"closed"},
    "closed":    {"pending"},
    "lost":      {"following"},
}

# ── 人性化状态名（供错误提示用） ──
_STATUS_LABEL = {
    "pending": "待分配",
    "assigned": "已分配",
    "following": "跟进中",
    "trial": "试听中",
    "enrolled": "已签约",
    "closed": "已关闭",
    "lost": "已流失",
}


def validate_transition(from_status: str, to_status: str):
    """校验转换是否合法，非法则抛异常"""
    if from_status == to_status:
        return  # 相同状态视为合法（幂等）
    allowed = _TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        from_label = _STATUS_LABEL.get(from_status, from_status)
        to_label = _STATUS_LABEL.get(to_status, to_status)
        raise InvalidTransition(
            f"不允许从「{from_label}」转换为「{to_label}」"
        )


def transition_lead(lead_id: int, to_status: str, operator_id: int = None) -> dict:
    """
    核心函数：安全地将线索从当前状态转换到目标状态。

    参数:
        lead_id:     线索 ID
        to_status:   目标状态
        operator_id: 操作人 ID（仅用于日志 / 预留）

    返回：
        更新后的线索 dict

    抛出：
        InvalidTransition — 非法转换
    """
    lead = query_one("SELECT * FROM leads WHERE id=?", (lead_id,))
    if not lead:
        raise InvalidTransition("线索不存在")

    from_status = lead["status"]
    validate_transition(from_status, to_status)

    # 如果状态没变化，直接返回
    if from_status == to_status:
        return lead

    # ── 执行转换 ──
    execute("UPDATE leads SET status=? WHERE id=?", (to_status, lead_id))

    # ── 副作用 ──
    # enrolled：自动推进签约（合同创建在 contracts.py 中处理，这里只更新状态）
    # closed：预留记录关闭原因

    return query_one("SELECT * FROM leads WHERE id=?", (lead_id,))


def transition_lead_safe(lead_id: int, to_status: str, operator_id: int = None) -> dict:
    """
    安全版本：捕获非法转换异常，返回 (success, result_or_error)
    适用于批量操作等需要逐个处理但不希望中断的场景。
    """
    try:
        new_lead = transition_lead(lead_id, to_status, operator_id)
        return True, new_lead
    except InvalidTransition as e:
        return False, str(e)
