"""
超期跟进扫描器 — 后台线程，每分钟检查
每天 09:00 扫描超期资源，发送钉钉通知
"""
import datetime
import threading
import time
from db import query, query_one, execute


# 上次通知日期（避免同一天重复发）
_last_notify_date = None
_checker_thread = None
_running = False


def _get_overdue_leads():
    """查询所有超期未跟进的线索"""
    return query(
        """SELECT l.id, l.name, l.next_followup_at, l.lead_rank,
                  l.last_followup_at, l.assignee_id,
                  u.display_name as assignee_name, u.phone,
                  COALESCE(l.overdue_count, 0) as overdue_count,
                  (SELECT f.content FROM followups f WHERE f.lead_id=l.id ORDER BY f.created_at DESC LIMIT 1) as last_content,
                  (SELECT l2.coordinator_id FROM leads l2 WHERE l2.id=l.id) as coordinator_id
           FROM leads l
           LEFT JOIN users u ON l.assignee_id = u.id
           WHERE l.next_followup_at IS NOT NULL
             AND l.next_followup_at != ''
             AND l.next_followup_at < datetime('now','localtime')
             AND l.status NOT IN ('enrolled', 'closed', 'lost')
             AND COALESCE(l.followup_paused, 0) = 0
           ORDER BY l.next_followup_at ASC"""
    )


def _is_workday():
    return datetime.datetime.now().weekday() < 5


def _is_notification_hour():
    """早上9点左右才发通知"""
    now = datetime.datetime.now()
    return 8 <= now.hour <= 10


def _update_overdue_counts(overdue_leads):
    """更新超期次数"""
    for lead in overdue_leads:
        lid = lead["id"]
        cnt = lead["overdue_count"] or 0
        execute(
            "UPDATE leads SET overdue_count=?, last_overdue_at=datetime('now','localtime') WHERE id=?",
            (cnt + 1, lid),
        )


def _check_and_notify():
    """核心检查逻辑"""
    global _last_notify_date

    today = datetime.datetime.now().strftime("%Y-%m-%d")

    # 同一天不重复发
    if _last_notify_date == today:
        return

    # 非工作日不发
    if not _is_workday():
        return

    # 非通知时段不发（9点前后1小时）
    if not _is_notification_hour():
        return

    overdue = _get_overdue_leads()
    if not overdue:
        return

    # 更新超期次数
    _update_overdue_counts(overdue)

    # 构建通知数据
    notify_list = []
    for lead in overdue:
        days = 0
        if lead["next_followup_at"]:
            try:
                dt = datetime.datetime.strptime(lead["next_followup_at"][:19], "%Y-%m-%d %H:%M")
                days = (datetime.datetime.now() - dt).days
            except (ValueError, TypeError):
                try:
                    dt = datetime.datetime.strptime(lead["next_followup_at"][:10], "%Y-%m-%d")
                    days = (datetime.datetime.now() - dt).days
                except (ValueError, TypeError):
                    pass

        notify_list.append({
            "name": lead["name"],
            "rank": lead["lead_rank"] or "未评级",
            "overdue_days": days or 1,
            "deadline": lead["next_followup_at"][:10] if lead["next_followup_at"] else "-",
            "last_content": lead.get("last_content") or "无记录",
            "phone": lead.get("phone") or "",
        })

    if not notify_list:
        return

    # 发钉钉
    try:
        from dingtalk_notifier import send_overdue_notice
        ok, msg = send_overdue_notice(notify_list)
        if ok:
            print(f"[OverdueChecker] ✅ {msg}")
        else:
            print(f"[OverdueChecker] ❌ {msg}")
    except Exception as e:
        print(f"[OverdueChecker] 通知发送失败: {e}")

    _last_notify_date = today


def _loop():
    """后台线程主循环"""
    global _running
    _running = True
    while _running:
        try:
            _check_and_notify()
        except Exception as e:
            print(f"[OverdueChecker] 检查异常: {e}")
        time.sleep(60)  # 每分钟检查一次


def start(webhook_url=None, secret=None):
    """启动超期检查后台线程"""
    global _checker_thread, _running

    if webhook_url or secret:
        from dingtalk_notifier import configure_dingtalk
        configure_dingtalk(webhook_url, secret)

    if _checker_thread and _checker_thread.is_alive():
        print("[OverdueChecker] 已在运行")
        return

    _running = True
    _checker_thread = threading.Thread(target=_loop, daemon=True, name="overdue-checker")
    _checker_thread.start()
    print(f"[OverdueChecker] ✅ 已启动 (线程: {_checker_thread.name})")


def stop():
    """停止检查线程"""
    global _running, _checker_thread
    _running = False
    if _checker_thread:
        _checker_thread = None
        print("[OverdueChecker] 已停止")
