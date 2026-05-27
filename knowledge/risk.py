"""风险控制模块 - 敏感内容过滤 + 速率限制 + 系统健康"""
import re
import time
import threading
from collections import defaultdict

# ============================================================
# 敏感内容检测
# ============================================================

SENSITIVE_PATTERNS = {
    "academic_dishonesty": [
        r"代写", r"代考", r"代课", r"替考", r"作弊", r"买卖论文",
        r"代做作业", r"代做题目", r"代做课题", r"代做项目", r"代做实验",
        r"代考试", r"代考研", r"代上课", r"代上学", r"替考", r"替课",
        r"作业代写", r"考试代写", r"考试代考", r"论文代写",
        r"买论文", r"卖论文", r"代写作业", r"代写论文",
        r"包过", r"保过", r"考前答案",
        r"买毕业设计", r"卖毕业设计", r"买毕设", r"卖毕设",
        r"代写毕业论文", r"代写毕业设计",
    ],
    "illegal": [
        r"签证欺诈", r"签证造假", r"假签证", r"伪造文件",
        r"移民造假", r"移民欺诈", r"假结婚",
        r"非法打工", r"打黑工",
        r"买卖护照", r"买卖身份",
        r"伪造学历", r"假学历", r"买卖学历",
        r"洗钱", r"逃税", r"漏税",
        r"挂黑", r"非法滞留", r"逾期居留",
    ],
    "self_harm": [
        r"自杀", r"自残", r"不想活了", r"活着没意思",
        r"想死", r"结束生命", r"伤害自己",
        r"轻生", r"自尽", r"自我了断", r"活不下去",
        r"想不开", r"了结", r"死了一了百了",
    ],
    "academic_crisis": [
        r"退学", r"劝退", r"开除", r"休学",
        r"被退学", r"被开除", r"勒令退学",
        r"挂科太多", r"被劝退", r"学业警告",
        r"留级", r"毕不了业", r"拿不到学位",
        r"被遣返", r"遣返回国", r"取消签证",
    ],
    "political_sensitive": [
        r"六四", r"天安门事件", r"八九学潮",
        r"法轮功", r"FLG",
        r"台独", r"疆独", r"藏独", r"港独",
        r"新疆独立", r"西藏独立", r"台湾独立",
        r"分裂国家", r"颠覆国家",
        r"学潮", r"民运", r"颜色革命",
        r"茉莉花革命",
        r"共匪", r"中共",
        r"和平演变",
        r"迫害", r"人权",
    ],
    "harassment": [
        r"色情", r"裸聊", r"约炮",
        r"毒品", r"吸毒", r"大麻", r"可卡因", r"海洛因", r"冰毒", r"摇头丸",
        r"赌博", r"赌场", r"网络赌",
    ],
}

_COMPILED_RULES = {}
for category, patterns in SENSITIVE_PATTERNS.items():
    if patterns:
        _COMPILED_RULES[category] = re.compile(
            "|".join(patterns), re.UNICODE)


def check_sensitive(text):
    """检查文本是否包含敏感内容.
    返回 (is_sensitive, category, matched_text)
    """
    if not text:
        return False, "", ""
    for category, regex in _COMPILED_RULES.items():
        m = regex.search(text)
        if m:
            return True, category, m.group(0)
    return False, "", ""


BLOCKED_RESPONSES = {
    "academic_dishonesty": (
        "抱歉，我们无法协助与学术不端相关的问题。\n\n"
        "Global 1v1 · AcadAI 致力于帮助留学生提升真实的学术能力，"
        "包括选课策略、学习方法、时间管理等正当学术支持。"
        "如果您在学习中遇到困难，可以告诉我具体是哪个方面需要帮助，"
        "我很乐意为您提供合规的学术建议。"
    ),
    "illegal": (
        "抱歉，我无法回答涉及违法违规的问题。\n\n"
        "如果您有关于留学合规手续、签证政策、合法打工规定等方面的问题，"
        "请以官方渠道信息为准。我很乐意为您提供合规的留学规划建议。"
    ),
    "self_harm": (
        "我感受到您正在经历困难的时刻。您的健康和安全是最重要的。\n\n"
        "建议您联系专业的心理支持：\n"
        "• 国内心理援助热线：010-82951332（24小时）\n"
        "• 希望24热线：400-161-9995\n"
        "• 学校心理咨询中心：大多数海外大学提供免费保密服务\n\n"
        "如果您想谈谈留学中的压力或适应问题，我随时在这里为您提供支持。"
    ),
    "academic_crisis": (
        "我理解您可能正在面对学业上的困难，这确实让人焦虑。\n\n"
        "请不要慌张，大多数海外大学都设有完善的学术支持体系：\n"
        "• 第一时间联系您的学术顾问（Academic Advisor）讨论选课调整方案\n"
        "• 了解学校的退学/休学政策及申诉流程（Appeal Process）\n"
        "• 利用学校提供的写作中心、辅导课程等免费资源\n"
        "• 如果涉及签证状态，请咨询国际学生办公室（International Student Office）\n\n"
        "Global 1v1 · AcadAI 可以为您提供学业规划建议，帮助您找到合规的解决方案。"
        "如果您需要，请告诉我您具体遇到了什么情况，我会尽力提供专业建议。"
    ),
    "political_sensitive": (
        "抱歉，我无法回应此类内容。\n\n"
        "Global 1v1 · AcadAI 专注于留学生课业规划与学术支持，"
        "请提出与留学、学习相关的问题，我将为您提供专业帮助。"
    ),
    "harassment": (
        "抱歉，我们无法回应此类内容。\n\n"
        "Global 1v1 · AcadAI 是为留学生和家长提供课业规划支持的专业平台。"
        "如果您有留学相关的问题，欢迎提出。"
    ),
}

DEFAULT_BLOCKED = (
    "抱歉，我无法回答这个问题。请提出与留学课业规划相关的问题。"
)


# ============================================================
# 速率限制
# ============================================================

class RateLimiter:
    """内存速率限制器 (滑动窗口)."""

    def __init__(self, max_requests=20, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, client_ip):
        """检查客户端是否超限. 返回 (allowed, remaining, reset_seconds)."""
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            self._requests[client_ip] = [
                t for t in self._requests[client_ip] if t > cutoff
            ]
            if len(self._requests[client_ip]) >= self.max_requests:
                reset_at = self._requests[client_ip][0] + self.window_seconds
                return False, 0, int(reset_at - now)
            self._requests[client_ip].append(now)
            remaining = self.max_requests - len(self._requests[client_ip])
            return True, remaining, 0


rate_limiter = RateLimiter(max_requests=20, window_seconds=60)


# ============================================================
# 系统健康
# ============================================================

class HealthTracker:
    """跟踪系统健康状态."""

    def __init__(self, start_time=None):
        self.start_time = start_time or time.time()
        self.total_requests = 0
        self.blocked_requests = 0
        self.errors = []
        self._lock = threading.Lock()

    def record_request(self, blocked=False):
        with self._lock:
            self.total_requests += 1
            if blocked:
                self.blocked_requests += 1

    def record_error(self, msg):
        with self._lock:
            self.errors.append({
                "time": time.strftime("%H:%M:%S"),
                "msg": str(msg)[:200],
            })
            if len(self.errors) > 100:
                self.errors = self.errors[-100:]

    def status(self):
        with self._lock:
            return {
                "status": "ok",
                "uptime": int(time.time() - self.start_time),
                "total_requests": self.total_requests,
                "blocked_requests": self.blocked_requests,
                "block_rate_pct": round(
                    self.blocked_requests / max(self.total_requests, 1) * 100, 1
                ),
                "recent_errors": self.errors[-10:],
            }


health = HealthTracker()
