"""
外部线索接入 Webhook — 微信/抖音等平台抓取客户联系方式后推送到 CRM

抓取平台 → POST JSON + API Key → /api/webhook/lead → 创建线索

支持两种输入格式：
1. 结构化：直接传 name + phone/wechat（平台已提取好）
2. 原始消息：传 message（完整聊天记录），AI 自动提取联系方式
"""
import json
import os
import secrets
import urllib.request
import urllib.error
import re
from router import post
from utils import ok_response, error_response, parse_body, add_oplog
from db import query_one, execute_lastrowid


# ── API Key 管理 ──

def _env_path() -> str:
    """返回 .env 文件路径"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")


def _read_env() -> dict:
    """读取 .env 文件，返回 {KEY: VALUE} 字典"""
    result = {}
    env_file = _env_path()
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    result[k.strip()] = v.strip()
    return result


def _write_env(updates: dict):
    """更新 .env 文件中的键值对"""
    env_file = _env_path()
    existing = _read_env()
    existing.update(updates)
    lines = []
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line_stripped = line.strip()
                if "=" in line_stripped and not line_stripped.startswith("#"):
                    k = line_stripped.split("=", 1)[0].strip()
                    if k in updates:
                        continue  # 后面重新写
                lines.append(line)
    # 追加新增的或覆盖的 key
    written_keys = set()
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if "=" in line_stripped and not line_stripped.startswith("#"):
            k = line_stripped.split("=", 1)[0].strip()
            if k in updates:
                lines[i] = f"{k}={updates[k]}\n"
                written_keys.add(k)
    for k, v in updates.items():
        if k not in written_keys:
            lines.append(f"{k}={v}\n")
    with open(env_file, "w") as f:
        f.writelines(lines)


def get_webhook_api_key() -> str:
    """获取 Webhook API Key，不存在则自动生成"""
    env = _read_env()
    key = env.get("WEBHOOK_API_KEY", "")
    if not key:
        key = "tms_wh_" + secrets.token_hex(16)
        _write_env({"WEBHOOK_API_KEY": key})
    return key


# ── AI 提取联系方式 ──

def _load_deepseek_key() -> str:
    """加载 DeepSeek API Key"""
    env_file = _env_path()
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return os.environ.get("DEEPSEEK_API_KEY", "")


def _extract_contact_from_message(raw_text: str) -> dict:
    """调用 DeepSeek 从聊天记录中提取联系方式"""
    api_key = _load_deepseek_key()
    if not api_key:
        # 降级：用正则粗略提取手机号和微信号
        phone_match = re.search(r'1[3-9]\d{9}', raw_text)
        wechat_match = re.search(r'[a-zA-Z][a-zA-Z0-9_-]{5,19}', raw_text)
        return {
            "name": "",
            "phone": phone_match.group(0) if phone_match else "",
            "wechat": wechat_match.group(0) if wechat_match else "",
            "summary": raw_text[:200],
        }

    system_prompt = """你是一个客户信息提取助手。从聊天记录中提取客户的联系方式。

输出 JSON 格式：
{
  "name": "客户姓名或称呼（没有则返回空字符串）",
  "phone": "手机号（没有则返回空字符串）",
  "wechat": "微信号（没有则返回空字符串）",
  "summary": "一句话概括客户需求（限30字）"
}

注意：
- 手机号格式：1开头的11位数字
- 微信号可能以字母开头
- 如果有多条消息，以最后提供的联系方式为准
- 聊天记录中可能有客服回复，注意区分客户和客服
- 只返回 JSON，不要其他文字"""

    data = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"聊天记录：\n{raw_text[:3000]}"},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
    }).encode()

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
        content = resp["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        return json.loads(content)
    except Exception:
        return {"name": "", "phone": "", "wechat": "", "summary": ""}


# ── Webhook 端点 ──

@post("/api/webhook/lead", auth=False)
def webhook_receive_lead(handler, token_payload, qs, body):
    """接收外部平台推送的线索"""
    # 1. 解析请求体
    data = body if body else parse_body(handler)

    # 2. 验证 API Key（所有请求必须携带有效的 API Key）
    api_key = data.get("api_key", "")
    if not api_key or api_key != get_webhook_api_key():
        error_response(handler, "API Key 无效", 401)
        return

    # 3. 提取信息：优先用结构化字段，没有则从原始消息中 AI 提取
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    wechat = (data.get("wechat") or "").strip()
    source = (data.get("source") or "").strip()
    message = (data.get("message") or data.get("content") or "").strip()

    # 如果没有结构化数据但有原始消息，用 AI 提取
    if (not name or (not phone and not wechat)) and message:
        extracted = _extract_contact_from_message(message)
        name = name or extracted.get("name", "") or ""
        phone = phone or extracted.get("phone", "") or ""
        wechat = wechat or extracted.get("wechat", "") or ""

    # 如果 AI 也没提取到，用正则从原始消息中提取手机号
    if not phone and message:
        m = re.search(r'1[3-9]\d{9}', message)
        if m:
            phone = m.group(0)
    if not wechat and message:
        m = re.search(r'(?:微信号?|微信)[：:]\s*([a-zA-Z][a-zA-Z0-9_-]{5,20})', message)
        if m:
            wechat = m.group(1)
    country = (data.get("country") or "").strip()
    grade = (data.get("grade") or "").strip()
    remark = (data.get("remark") or "").strip()

    # 如果有原始消息但没单独 remark，把消息内容作为备注
    if message and not remark:
        remark = message[:500]  # 只存前500字

    if not name:
        # 从原始消息中提取称呼或使用 phone/wechat 做临时名
        if phone:
            name = phone
        elif wechat:
            name = wechat
        elif message:
            # 取消息前10个字作为临时名
            name = message.strip()[:10]
        else:
            error_response(handler, "姓名不能为空", 400)
            return
    if not phone and not wechat:
        error_response(handler, "手机号和微信号至少填写一个", 400)
        return

    # 4. 去重检测：按 phone 或 wechat 查重
    if phone:
        existing = query_one("SELECT id, name, phone, wechat, source, status, created_at FROM leads WHERE phone=?", (phone,))
        if existing:
            ok_response(handler, {
                "status": "duplicate",
                "existing_lead_id": existing["id"],
                "lead": existing,
            })
            return
    if wechat and not phone:
        existing = query_one("SELECT id, name, phone, wechat, source, status, created_at FROM leads WHERE wechat=?", (wechat,))
        if existing:
            ok_response(handler, {
                "status": "duplicate",
                "existing_lead_id": existing["id"],
                "lead": existing,
            })
            return

    # 5. 创建线索（使用系统管理员作为 creator_id）
    from db import query_one as _q1
    sys_user = _q1("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1")
    creator_id = sys_user["id"] if sys_user else 1
    lead_id = execute_lastrowid(
        """INSERT INTO leads (name, phone, wechat, source, country, grade, remark, creator_id, status)
           VALUES (?,?,?,?,?,?,?,?,'pending')""",
        (name, phone, wechat, source or "外部导入", country, grade, remark, creator_id),
    )

    # 6. 记录操作日志
    add_oplog(creator_id, "webhook", "create", "lead", lead_id, f"外部线索: {name}", json.dumps({"source": source, "phone": phone, "wechat": wechat}, ensure_ascii=False))

    # 7. 返回创建结果
    lead = query_one("SELECT id, name, phone, wechat, source, status, created_at FROM leads WHERE id=?", (lead_id,))
    ok_response(handler, {"status": "created", "lead_id": lead_id, "lead": lead})
