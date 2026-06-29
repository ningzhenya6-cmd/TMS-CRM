"""
钉钉通知模块 — 群机器人 Webhook + 签名
发送跟进超期提醒到钉钉群，支持 @指定人
"""
import os
import json
import time
import hmac
import hashlib
import base64
import urllib.request
import urllib.parse

# 默认配置（从 .env 读取或覆盖）
_WEBHOOK_URL = os.environ.get("DINGTALK_WEBHOOK", "")
_WEBHOOK_SECRET = os.environ.get("DINGTALK_SECRET", "")


def _sign(timestamp):
    """HMAC-SHA256 签名"""
    secret_key = _WEBHOOK_SECRET.encode("utf-8")
    string_to_sign = f"{timestamp}\n{_WEBHOOK_SECRET}".encode("utf-8")
    h = hmac.new(secret_key, string_to_sign, digestmod=hashlib.sha256)
    sign = base64.b64encode(h.digest()).decode("utf-8")
    return urllib.parse.quote(sign, safe="")


def send_overdue_notice(overdue_list):
    """发送超期跟进提醒到钉钉群
    overdue_list: [{name, rank, overdue_days, deadline, last_content, phone}]
    """
    if not _WEBHOOK_URL:
        return False, "未配置钉钉 Webhook"

    at_mobiles = []
    items_text = ""
    for idx, item in enumerate(overdue_list[:10]):  # 一次最多10条
        items_text += f"""
{idx+1}. **{item.get('name', '未知')}**
   评级：{item.get('rank', '-')} | 超期：{item.get('overdue_days', 0)}天
   截止：{item.get('deadline', '-')}
   最近跟进：{item.get('last_content', '无')[:50]}
---"""
        phone = item.get("phone", "")
        if phone:
            at_mobiles.append(phone)

    if len(overdue_list) > 10:
        items_text += f"\n... 还有 {len(overdue_list)-10} 条超期未展示"

    markdown_text = f"""## 🔔 跟进超期提醒

共 {len(overdue_list)} 条超期未跟进

{items_text}

👉 [点击前往 CRM 处理](https://tms.global1v1.com/go.html)
"""

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": "🔔 跟进超期提醒",
            "text": markdown_text,
        },
        "at": {
            "atMobiles": at_mobiles,
            "isAtAll": False,
        },
    }

    # 加签
    timestamp = str(int(round(time.time() * 1000)))
    sign = _sign(timestamp)
    url = f"{_WEBHOOK_URL}&timestamp={timestamp}&sign={sign}"

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("errcode") == 0:
                return True, f"已发送 {len(overdue_list)} 条超期提醒"
            return False, result.get("errmsg", "发送失败")
    except Exception as e:
        return False, f"网络错误: {e}"


def configure_dingtalk(webhook_url=None, secret=None):
    """配置钉钉 Webhook（供 server.py 启动时调用）"""
    global _WEBHOOK_URL, _WEBHOOK_SECRET
    if webhook_url:
        _WEBHOOK_URL = webhook_url
    if secret:
        _WEBHOOK_SECRET = secret
