"""
声明式权限层 — 集中管理角色权限和数据范围
所有后端 API 通过 can() 和 scope() 获取权限判断，不再写硬编码 if/elif
"""
from utils import error_response

# ═══════════════════════════════════════════
# 动作权限定义：什么角色可以做什么操作
# '*' 表示所有已登录角色
# ═══════════════════════════════════════════
CAN = {
    # ── 线索 ──
    "lead:list":           ["*"],
    "lead:view":           ["*"],
    "lead:create":         ["cs", "consultant", "admin", "supervisor"],
    "lead:edit":           ["cs", "consultant", "admin", "supervisor"],
    "lead:edit_any":       ["admin", "supervisor"],
    "lead:delete":         ["admin", "supervisor"],
    "lead:assign":         ["admin", "supervisor", "cs"],
    "lead:batch_assign":   ["admin", "supervisor"],
    "lead:batch_op":       ["admin", "supervisor"],
    "lead:adjust_coordinator": ["admin", "supervisor", "cs", "consultant"],

    # ── 排课 ──
    "schedule:list":       ["*"],
    "schedule:manage":     ["coordinator", "admin", "supervisor"],

    # ── 试听 ──
    "trial:list":          ["*"],
    "trial:manage":        ["coordinator", "admin", "supervisor"],
    "trial:feedback":      ["cs", "consultant", "admin", "supervisor"],

    # ── 合同 & 课时包 ──
    "contract:view":       ["admin", "supervisor", "cs", "consultant", "coordinator", "academic"],
    "contract:manage":     ["coordinator", "admin", "supervisor"],
    "package:manage":      ["coordinator", "academic", "admin", "supervisor"],

    # ── 财务 ──
    "finance:view":        ["admin", "supervisor", "cs", "consultant"],

    # ── 师资 ──
    "teacher:manage":      ["coordinator", "admin", "supervisor"],

    # ── 用户管理 ──
    "user:manage":         ["admin", "supervisor"],

    # ── 仪表盘 ──
    "dashboard:view":              ["*"],
    "dashboard:view_admin":        ["admin", "supervisor"],
    "dashboard:view_consultant":   ["cs", "consultant", "academic"],
    "dashboard:view_academic":     ["academic"],
    "dashboard:view_coordinator":  ["coordinator"],

    # ── 成长档案 ──
    "growth:view":                 ["*"],
    "growth:manage":               ["cs", "consultant", "academic", "coordinator", "admin", "supervisor"],
    "exam:manage":                 ["cs", "consultant", "academic", "coordinator", "admin", "supervisor"],
    "admission:manage":            ["admin", "supervisor"],

    # ── 学业分析 ──
    "consulting:view":             ["cs", "consultant", "academic", "admin", "supervisor"],
    "consulting:create":           ["cs", "consultant", "academic", "admin", "supervisor"],
    "consulting:generate":         ["cs", "consultant", "academic", "admin", "supervisor"],
    "consulting:manage":           ["cs", "consultant", "academic", "admin", "supervisor"],
}

# ═══════════════════════════════════════════
# 数据范围定义：什么角色只能看到哪些数据
# None = 全部可见（管理层）
# str  = 字段名（不含表别名），如 "assignee_id"
# ═══════════════════════════════════════════
SCOPE = {
    "lead": {
        "admin":        None,
        "supervisor":   None,
        "cs":           "assignee_id",
        "consultant":   "assignee_id",
        "coordinator":  "coordinator_id",
        "academic":     "assignee_id",
    },
    "schedule": {
        "admin":        None,
        "supervisor":   None,
        "coordinator":  None,
        "tutor":        "tutor_id",
        "cs":           None,
        "consultant":   None,
        "academic":     None,
    },
    "student": {
        "admin":        None,
        "supervisor":   None,
        "cs":           "assignee_id",
        "consultant":   "assignee_id",
        "academic":     "assignee_id",
        "coordinator":  "coordinator_id",
    },
}


# ═══════════════════════════════════════════
# 公开函数
# ═══════════════════════════════════════════

def can(role: str, permission: str) -> bool:
    """检查角色是否有指定权限"""
    allowed = CAN.get(permission, [])
    if "*" in allowed:
        return True
    return role in allowed


def require(permission: str):
    """装饰器工厂：在 handler 函数上声明所需权限"""
    def decorator(fn):
        def wrapper(handler, token_payload, qs, body, **kwargs):
            role = token_payload.get("role", "")
            if not can(role, permission):
                error_response(handler, "无权访问", 403)
                return
            return fn(handler, token_payload, qs, body, **kwargs)
        return wrapper
    return decorator


def _scope_field(resource: str, role: str):
    """获取指定资源+角色的数据范围字段名，None 表示不限"""
    mapping = SCOPE.get(resource, {})
    return mapping.get(role)


def scope_where(resource: str, role: str, user_id: int, alias: str = None) -> tuple:
    """获取数据范围 WHERE 条件

    参数:
        resource: 资源名 'lead'/'schedule'/'student'
        role:     用户角色
        user_id:  用户 ID
        alias:    表别名（可选），如 'l' 会生成 'l.assignee_id=?'

    返回 (where_clause, [params])
    """
    field = _scope_field(resource, role)
    if field is None:
        return "1=1", []
    prefixed = f"{alias}.{field}" if alias else field
    return f"{prefixed}=?", [user_id]
