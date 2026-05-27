"""DeepSeek AI integration - make API calls using stdlib urllib.

Supports hybrid search: knowledge base + web search for school/program info.
"""
import os
import json
import urllib.request
import urllib.error

API_URL = "https://api.deepseek.com/v1/chat/completions"

def _get_custom_endpoint():
    """Read custom AI model config from config/ai_endpoint.json."""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "ai_endpoint.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                cfg = json.load(f)
            if cfg.get("enabled") and cfg.get("api_url"):
                return cfg["api_url"], cfg.get("api_key", ""), cfg.get("model", "custom-model")
        except:
            pass
    return None, None, None

# Keywords that suggest a query needs specific school/program info
SCHOOL_KEYWORDS = [
    "大学", "学院", "school", "university", "college", "institute",
    "专业", "major", "program", "课程", "curriculum", "课",
    "学费", "tuition", "录取", "admission", "申请", "apply",
    "排名", "ranking", "QS", "US News",
    "CS", "计算机", "商科", "business", "engineering", "工程",
    "数据科学", "data science", "金融", "finance", "经济", "economics",
    "心理学", "psychology", "传媒", "communication",
    "生物", "biology", "化学", "chemistry", "物理", "physics",
    "选课", "GPA", "学分", "credit",
]

def _query_needs_web_search(query):
    """Check if a query likely needs current web data (school/program specifics)."""
    q = query.lower()
    for kw in SCHOOL_KEYWORDS:
        if kw.lower() in q:
            return True
    return False


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


def build_system_prompt(role=None):
    prompt = """你是一位资深的留学生课业规划顾问，拥有数千真实案例的实战经验。
你的任务是为留学生提供学业规划、选课策略、升学准备等方面的实用建议。

---

## 回答准则

1. **直接有用** — 先正面回答用户的问题，再展开细节。不要绕圈子，不要先给免责声明。
2. **温暖专业** — 像有经验的学长学姐那样说话，体现出对留学生处境的理解。
3. **具体可操作** — 给出明确的步骤、时间节点、行动建议，不要泛泛而谈。
4. **简洁精炼** — 每句话都要传递信息。能不说的就不说。

---

## 来源标注（自然融入）

把信息来源自然地融入叙述中，不要在每个句子后面贴标签。

✅ 好的写法：
- 「根据案例库中 8 个相似案例，建议优先选修 CS 方向的课程…」
- 「网络搜索显示 2025 年该专业学费约 $55,000」
- 「这方面我没有找到完全匹配的案例，以下建议仅供参考」

❌ 不要这样写：
- 「建议选修 CS 方向的课程以匹配申请要求【案例库】【可信度：高 | 基于 8 条相似案例】」

**段落级别标注一次即可**，不需要每条建议都带标签。

---

## 模糊问题处理

如果用户问题缺少关键信息（如只说"签证怎么办"但没说哪个国家）：
- 先提问确认 1-2 个最关键的信息，再回答
- 语气友好，不要生硬
- 不要猜测，也不要列出所有可能性
- 用户补充信息后再完整回答

---

## 推荐结构（灵活参考，不必严格照搬）

```
① 直接回答核心问题
② 分点给出具体建议（每段自然注明来源）
③ 2-3 个延伸话题/相关方向
```

---

## 绝对不要做

- ❌ 每条建议后面加 【可信度】 标签
- ❌ 做任何形式的推销或服务引导
- ❌ 回答具体的作业题或考试题
- ❌ 编造案例或数据

---

## 免责声明

回答末尾添加：
「⚠️ 以上建议基于案例库生成，仅供参考，不构成专业建议。具体决策请结合个人实际情况或咨询专业顾问。」"""

    if role == "parent":
        prompt += """

## 家长用户须知（当前用户是家长）

- 每个专业术语都要解释清楚（GPA 是什么、学分制怎么运作等）
- 语气更加温暖体贴，理解家长的关切
- 可以补充如何与孩子沟通这些学业问题的建议"""

    return prompt


def build_neutral_system_prompt():
    """不包含任何商业/推广内容的纯净版系统提示（用于用户询问系统本身时）。"""
    return """你是一位资深的留学生课业规划顾问。

你的核心能力：
1. 回答关于留学生课业规划、学术策略、选课技巧、升学规划、签证政策、海外生活等问题
2. 结合真实案例和实时搜索信息，给出具体、实用的建议
3. 用温暖、专业的中文语气回答

回答规则：
- 回答要简洁、客观，仅针对用户的问题本身
- 不要提及任何具体的机构名称、服务项目或商业内容
- 不要做任何形式的推广、引导或推销
- 如果用户问到这个系统/工具本身的用途，回答：这是一个基于数千真实案例的AI留学课业辅助工具，帮助海外留学生获取学业规划建议
- 不要添加任何不属于问题范围的额外信息
- 不要主动推荐后续话题，除非用户明确要求"""


def _classify_query(text):
    """Classify self-referential queries into risk tiers.

    Returns:
        'green' — safe to answer openly about the system's purpose and capabilities
        'yellow' — give high-level vague answers, no specific details
        'red' — deflect, do not answer, use pre-written response
        None — normal study query, use normal flow
    """
    t = text.lower().strip()

    # Red tier — internal/sensitive info, deflect immediately
    red_indicators = [
        "怎么搭建", "怎么实现", "怎么开发", "怎么部署",
        "技术架构", "架构", "后台架构",
        "商业模式", "怎么赚钱", "怎么收费", "收多少钱",
        "源代码", "源码", "代码怎么看", "代码能",
        "后台怎么", "服务端",
        "数据库", "用了什么库",
        "多少条数据", "知识库多大", "多少案例",
        "竞品", "竞争对手",
        "团队多少人", "你们团队", "几个人",
        "什么模型", "deepseek", "gpt", "claude",
        "服务器配置", "服务器在哪",
        "成本", "投入多少",
    ]
    for kw in red_indicators:
        if kw in t:
            return "red"

    # Yellow tier — technical/implementation details, give high-level only
    yellow_indicators = [
        "做了哪些优化", "优化了哪些", "有什么优化", "怎么优化",
        "什么技术", "技术栈", "后端", "前端",
        "什么语言", "什么框架",
        "逻辑是什么", "逻辑是",
        "原理", "工作流程", "工作流",
        "后台",
    ]
    # Only match yellow if NOT already matched red
    for kw in yellow_indicators:
        if kw in t:
            return "yellow"

    # Green tier — general system info, safe to answer
    green_indicators = [
        "你是什么", "你是谁", "你的目的是", "你在做什么",
        "这个系统", "这个平台", "这个工具", "你这套",
        "what is this", "what are you", "who are you",
        "your purpose", "what does this",
        "你的功能是什么", "你有什么用", "你能做什么",
        "这个工具", "这套系统",
        "数据哪来的", "数据来源",
        "隐私", "安全", "隐私安全",
        "信息.", "信息保护", "信息安全",
    ]
    for kw in green_indicators:
        if kw in t:
            return "green"

    return None


RED_DEFLECTION = (
    "感谢你的关注！不过我更擅长为留学生提供课业规划方面的帮助——比如选课策略、"
    "GPA管理、升学规划、海外生活适应等等。如果你在这些方面有什么疑问，"
    "我很乐意结合真实案例经验为你提供参考建议。请问有什么具体的留学问题我可以帮你解答吗？"
)


def _build_green_prompt():
    """Self-referential prompt for green-tier queries: answer openly about the system."""
    return """你是一位资深的留学生课业规划顾问，同时也是这个AI工具的友善代言人。

用户正在询问关于这个系统本身的问题。请用温暖、专业、坦诚的语气回答。

你可以自然介绍以下信息：
- 这是一个基于数千真实留学案例的AI留学课业辅助工具
- 核心功能是为海外留学生提供选课策略、GPA管理、升学规划等个性化建议
- 数据来源于大量真实留学生辅导经验的积累
- 结合AI能力与专业知识库，针对每个问题匹配最相关的案例经验

回答原则：
- 坦诚、开放，展现专业性
- 不要提及任何具体的模型名称、技术框架或实现细节
- 不要透露具体的功能清单或开发细节
- 回答简洁明了（60-100字），说清楚即可
- 回答的最后自然引回到留学话题，例如询问用户有什么具体的留学问题需要帮助"""


def _build_yellow_prompt():
    """Self-referential prompt for yellow-tier queries: high-level vague only."""
    return """你是一位资深的留学生课业规划顾问。

用户正在询问关于这个系统技术或实现层面的问题。请给出高度概括性的回答，不透露任何具体实现。

回答原则：
- 用概括性语言，例如"集成了主流AI能力并配合自有的知识库引擎"
- 不要提及任何具体的模型名称、技术栈、框架名称
- 不要提及具体的优化方法、数量指标或技术方案
- 不要透露任何内部实现信息
- 语气保持友好、专业
- 回答尽量简短（30-50字）
- 快速将对话引导回留学相关话题"""


def _resolve_endpoint():
    """Return (api_url, api_key, model). Prefer custom config, else DeepSeek."""
    custom_url, custom_key, custom_model = _get_custom_endpoint()
    if custom_url:
        return custom_url, custom_key or _get_api_key(), custom_model
    return API_URL, _get_api_key(), "deepseek-chat"


def ask_deepseek(messages, stream=False, temperature=0.3, max_tokens=2048):
    """Call AI API and return response. Supports custom model endpoints."""
    api_url, api_key, model = _resolve_endpoint()
    if not api_key and api_url == API_URL:
        return {"error": "API key not found. Set DEEPSEEK_API_KEY in .env"}
    if not api_key and api_url != API_URL:
        pass

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }

    data = json.dumps(payload).encode('utf-8')
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        api_url,
        data=data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            return str(result)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8') if e.fp else ""
        return f"API Error {e.code}: {body}"
    except Exception as e:
        return f"Error: {str(e)}"


def _build_context(query, context_chunks, web_results=None):
    """Build context prompt from KB and web search results with tiered relevance.

    Tier 1 (top 2): Full content (~800 chars) — highest relevance entries
    Tier 2 (3-4): Content summary (~300 chars) — moderately relevant
    Tier 3 (5+): Title only — marginal relevance, shown for completeness
    """
    kb_parts = []
    for i, chunk in enumerate(context_chunks):
        entry = chunk['entry']
        score = chunk.get('score', 0)

        if i < 2:
            # Tier 1: full content
            content = entry.get('content', '')[:800]
        elif i < 4:
            # Tier 2: summary
            content = entry.get('content', '')[:300]
        else:
            # Tier 3: title only
            content = ''

        if i < 4:
            kb_parts.append(
                f"\U0001f4da 【案例 {i+1}】{entry.get('category', '通用')} - {entry.get('title', '')}\n"
                f"匹配度：{score:.2f}\n"
                f"{content}"
            )
        else:
            kb_parts.append(
                f"\U0001f4da 【案例 {i+1}】{entry.get('category', '通用')} - {entry.get('title', '')} "
                f"(匹配度：{score:.2f})"
            )

    web_parts = []
    if web_results:
        for i, r in enumerate(web_results[:5]):
            if i < 3:
                # Top web results: full snippet
                snippet = r.get('snippet', '')[:400]
            else:
                # Lower web results: title only
                snippet = ''
            web_parts.append(
                f"\U0001f310 【网络搜索】{r.get('title', '')}\n"
                f"来源：{r.get('url', '')}\n"
                + (f"摘要：{snippet}" if snippet else "(参考来源)")
            )

    parts = [f"## 知识库检索结果（共找到 {len(context_chunks)} 条相关案例）"]
    if kb_parts:
        parts.append("\n\n".join(kb_parts))
    else:
        parts.append("（未找到直接相关的案例）")

    if web_parts:
        parts.append(f"\n\n## 网络搜索结果（共找到 {len(web_results)} 条相关信息）")
        parts.append("\n\n".join(web_parts))

    parts.append("""
## 当前问题

""" + query + """

## 使用说明

- 优先使用检索到的案例和网络搜索结果来回答
- 将来源自然融入叙述（如"根据案例库中 X 个案例…"），段落级别标注即可
- 案例覆盖充分 → 自信回答
- 案例部分相关 → 标注"案例覆盖有限"
- 完全没有相关信息 → 明确告知用户，给出通用建议并标注「仅供参考」
- 如果用户问题缺少关键信息，先提问确认再回答""")

    return "\n".join(parts)


def ask_stream(query, context_chunks, web_results=None, on_chunk=None, user_role=None):
    """Single-turn streaming. Calls on_chunk(text) for each piece."""
    context = _build_context(query, context_chunks, web_results)
    _do_stream(context, [], on_chunk, user_role, raw_query=query)


def ask_stream_with_history(query, context_chunks, web_results, history, on_chunk, user_role=None):
    """Multi-turn streaming with conversation history.

    Args:
        query: Current user question
        context_chunks: KB search results for current question
        web_results: Web search results for current question
        history: List of {role, content} from previous turns
        on_chunk: Callback for each text chunk
        user_role: User role for tailored system prompt ('student' or 'parent')
    """
    context = _build_context(query, context_chunks, web_results)
    _do_stream(context, history, on_chunk, user_role, raw_query=query)


def _do_stream(context, history, on_chunk, user_role=None, raw_query=None):
    """Core streaming logic shared by single-turn and multi-turn."""
    api_url, api_key, model = _resolve_endpoint()
    if not api_key and api_url == API_URL:
        on_chunk("API key 未配置，请在 .env 文件中设置 DEEPSEEK_API_KEY，或配置 config/ai_endpoint.json")
        return

    # Classify query for self-referential risk control
    tier = _classify_query(raw_query) if raw_query else None

    if tier == "red":
        # Canned deflection — skip API call entirely
        on_chunk(RED_DEFLECTION)
        return

    if tier == "green":
        sys_prompt = _build_green_prompt()
    elif tier == "yellow":
        sys_prompt = _build_yellow_prompt()
    else:
        sys_prompt = build_system_prompt(user_role)

    messages = [{"role": "system", "content": sys_prompt}]

    # Append conversation history (previous turns, no search context)
    for msg in history:
        messages.append(msg)

    # Current turn with fresh search context
    messages.append({"role": "user", "content": context})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 4096,
        "stream": True,
    }

    data = json.dumps(payload).encode('utf-8')
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        api_url,
        data=data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            while True:
                line = resp.readline()
                if not line:
                    break
                line_str = line.decode('utf-8').strip()
                if line_str.startswith('data: '):
                    data_str = line_str[6:]
                    if data_str == '[DONE]':
                        return
                    try:
                        data_json = json.loads(data_str)
                        if 'choices' in data_json and data_json['choices']:
                            delta = data_json['choices'][0].get('delta', {})
                            if 'content' in delta:
                                on_chunk(delta['content'])
                    except:
                        pass
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8') if e.fp else ""
        on_chunk(f"\n\n[API Error {e.code}: {body}]")
    except Exception as e:
        on_chunk(f"\n\n[Error: {str(e)}]")
