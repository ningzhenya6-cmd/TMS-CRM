"""Smart knowledge entry — use AI to parse raw coaching records into structured entries.

Usage:
    from knowledge.smart_add import parse_raw_text
    result = parse_raw_text("学生情况：英国硕士...")
    # Returns: {title, category, tags, content}
"""
import json
import os
import urllib.request
import urllib.error
import urllib.parse

API_URL = "https://api.deepseek.com/v1/chat/completions"

CATEGORIES = [
    "uk-academic", "uk-life", "uk-visa", "uk-grad",
    "us-academic", "us-life", "us-visa", "us-grad",
    "au-academic", "au-life", "au-visa", "au-career",
    "ca-academic", "ca-life", "ca-visa",
    "hk-academic", "hk-life", "hk-visa",
    "sg-academic", "sg-life", "sg-visa",
    "academic-writing", "gpa-management", "course-selection",
    "major-selection", "grad-application", "career-planning",
    "daily-life", "cross-cultural", "general-comparison",
    "general-entry", "general-parents", "general-preparation",
    "emergency", "academic",
]

SYSTEM_PROMPT = """你是一个留学知识库管理员。你的任务是把一段留学辅导记录结构化，提取以下字段并以 JSON 格式返回（不要包含任何其他文字）：

1. title: 简短标题，8-15字，概括核心问题，如"英国硕士挂科补救方案"
2. category: 分类标识。从以下列表中选择最匹配的一个（如果都不匹配就选 closest 的）:
   {categories}
3. tags: 标签列表，3-5个关键词，如["挂科","英国","硕士","补考"]
4. content: 结构化的知识内容。要求：
   - 去除口语化表述、寒暄、重复内容
   - 提炼为清晰的知识点，按逻辑分段
   - 保留具体的时间节点、分数要求、操作步骤等关键信息
   - 段首不要加数字序号
   - 500-800字

返回格式（严格 JSON，不要 markdown 代码块标记）：
{{"title":"...","category":"...","tags":[...],"content":"..."}}
"""


def _get_api_key():
    """Read API key from .env file."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return os.environ.get("DEEPSEEK_API_KEY", "")


def parse_raw_text(text):
    """Parse raw coaching record text into structured knowledge entry.

    Returns dict with {title, category, tags, content} or {error: ...}.
    """
    api_key = _get_api_key()
    if not api_key:
        return {"error": "API key not found"}

    categories_str = ", ".join(sorted(CATEGORIES))
    system_prompt = SYSTEM_PROMPT.format(categories=categories_str)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请结构化以下辅导记录：\n\n{text}"},
    ]

    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2048,
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    req = urllib.request.Request(
        API_URL,
        data=data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Clean possible markdown code block wrapping
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        parsed = json.loads(content)
        # Validate required fields
        if not parsed.get("title"):
            return {"error": "AI 未能提取出标题"}
        if not parsed.get("content"):
            return {"error": "AI 未能提取出内容"}
        if not parsed.get("category"):
            parsed["category"] = "general"
        if not isinstance(parsed.get("tags"), list):
            parsed["tags"] = []

        return parsed

    except json.JSONDecodeError:
        return {"error": "AI 返回格式异常，请重试"}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {"error": f"API 请求失败: {e.code}"}
    except Exception as e:
        return {"error": str(e)}
