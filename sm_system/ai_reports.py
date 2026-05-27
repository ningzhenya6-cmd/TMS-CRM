"""
AI Reports — Auto-generate student feedback & academic reports via DeepSeek API.

Three report types:
  - post_class:    课后反馈 (per-session, for teacher/coordinator to send after class)
  - feedback:      客户反馈 (periodic, academic manager sends to parents/student)
  - academic_report: 学情报告 (comprehensive progress report)

All prompts are designed to produce structured, professional output
that staff can review/publish with minimal edits.
"""
import sys
import os
import json

# Ensure parent dir is on path so we can import knowledge.ai
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from knowledge.ai import ask_deepseek


# ─── Prompt Templates ────────────────────────────────────────────────────────

SYSTEM_PROMPT_BASE = """你是一位专业的留学课辅机构资深教务老师兼学管师。
你精通留学生学业规划，擅长将零散的信息整合成结构化、有温度的专业反馈。
你的输出语言为简体中文，语气专业、温暖、具体。
禁止在报告中添加任何推广营销内容，保持纯粹的教育反馈。
除非明确要求，否则不使用markdown格式，使用纯文本段落。"""


def _build_post_class_prompt(data):
    """课后反馈 — 发给家长/学生，告知当堂课情况。"""
    return f"""请根据以下信息，生成一份**当堂课后反馈**，供授课老师或教务发给学生/家长。

## 学生信息
- 姓名：{data.get('student_name', '未知')}
- 科目：{data.get('subject', '未知')}
- 国家/地区：{data.get('country', '未知')}

## 课程信息
- 上课时间：{data.get('lesson_time', '未知')}
- 课程主题：{data.get('topic', '未知')}
- 上课时长：{data.get('duration_minutes', '未知')} 分钟

## ClassIn AI 课堂总结
{data.get('classin_summary', '（暂无AI总结数据）')}

## 老师/教务备注
{data.get('teacher_notes', '（暂无）')}

## 生成要求

请按以下结构生成课后反馈（纯文本，不要markdown格式）：

【课堂概要】用1-2句话概括本节课的主要内容和目标。

【课堂表现】描述学生的课堂参与度、互动情况、理解程度等。结合ClassIn总结中的数据来说话。

【知识点掌握】列出本节课涉及的核心知识点，标注学生的掌握程度（优/良/待加强）。

【课后建议】给学生的具体复习建议和练习方向（2-3条）。

【下次课预告】预告下次课的时间范围和主题（如有）。

整篇反馈控制在200-300字之间，语气温暖、鼓励为主。"""


def _build_feedback_prompt(data):
    """客户反馈 — 学管定期反馈给家长/学生，汇报近期综合情况。"""
    activities_text = ""
    if data.get('activities'):
        for a in data['activities']:
            activities_text += f"- [{a.get('created_at', '')}] {a.get('type', '跟进')}: {a.get('content', '')[:200]}\n"

    packages_text = ""
    if data.get('packages'):
        for p in data['packages']:
            remaining = float(p.get('total_hours', 0)) - float(p.get('used_hours', 0))
            packages_text += f"- {p.get('package_name', '课时包')}: 已用{p.get('used_hours', 0)}h / 总计{p.get('total_hours', 0)}h，剩余{remaining:.1f}h\n"

    schedules_text = ""
    if data.get('recent_schedules'):
        for s in data['recent_schedules']:
            schedules_text += f"- {s.get('start_time', '')} | {s.get('topic', '')} | 老师: {s.get('tutor_name', '')} | 状态: {s.get('status', '')}\n"

    return f"""请根据以下学生信息和近期跟进记录，生成一份**客户反馈**，供学管师发给家长或学生。

## 学生信息
- 姓名：{data.get('student_name', '未知')}
- 科目：{data.get('subject', '未知')}
- 国家/地区：{data.get('country', '未知')}
- 年级：{data.get('grade', '未知')}
- 当前状态：{data.get('status', '未知')}

## 课时包使用情况
{packages_text or '（暂无课时包数据）'}

## 近期课程记录
{schedules_text or '（暂无课程记录）'}

## 跟进/沟通记录
{activities_text or '（暂无跟进记录）'}

## 生成要求

请按以下结构生成客户反馈（纯文本，不要markdown格式）：

【学习概况】简述学生当前整体学习情况，用1-2句话概括。

【近期进展】详细说明近期的学习进展和亮点，结合课程记录和跟进记录中的具体信息。包括课时消耗进度。

【存在不足】客观指出目前学习中需要关注的问题或薄弱环节（如有）。

【学管建议】给出2-3条具体可行的学习建议。

【后续安排】预告未来的课程安排和计划。

整篇反馈控制在300-500字之间，语气温暖专业，既要让家长了解真实情况，又要传递信心。"""


def _build_academic_report_prompt(data):
    """学情报告 — 综合性的学习进展报告（较详细的版本）。"""
    activities_text = ""
    if data.get('activities'):
        for a in data['activities']:
            activities_text += f"- [{a.get('created_at', '')}] {a.get('type', '跟进')}: {a.get('content', '')[:200]}\n"

    packages_text = ""
    if data.get('packages'):
        for p in data['packages']:
            remaining = float(p.get('total_hours', 0)) - float(p.get('used_hours', 0))
            percent = round(float(p.get('used_hours', 0)) / max(float(p.get('total_hours', 1)), 1) * 100, 1)
            packages_text += f"- {p.get('package_name', '课时包')}: 总课时{p.get('total_hours', 0)}h | 已消耗{p.get('used_hours', 0)}h ({percent}%) | 剩余{remaining:.1f}h | 有效期至{p.get('valid_until', '无期限')}\n"

    schedules_text = ""
    if data.get('recent_schedules'):
        for s in data['recent_schedules']:
            schedules_text += f"- {s.get('start_time', '')} | {s.get('topic', '')} | 老师: {s.get('tutor_name', '')} | 时长: {s.get('duration_minutes', '')}min | 状态: {s.get('status', '')}\n"

    consumption_text = ""
    if data.get('recent_consumptions'):
        for c in data['recent_consumptions']:
            consumption_text += f"- 排课时长: {c.get('hours_scheduled', 0)}h | 实际上课: {c.get('hours_actual', 0)}h | 确认消耗: {c.get('hours_consumed', 0)}h | 状态: {c.get('status', '')}\n"

    return f"""请根据以下完整数据，生成一份**学情报告**——这是给家长或学生本人的综合性学习进展报告，需要全面、专业、有温度。

## 学生信息
- 姓名：{data.get('student_name', '未知')}
- 科目：{data.get('subject', '未知')}
- 国家/地区：{data.get('country', '未知')}
- 年级/学位：{data.get('grade', '未知')}

## 课时包详情
{packages_text or '（暂无课时包数据）'}

## 近期课程记录（按时间倒序）
{schedules_text or '（暂无课程记录）'}

## 课时消耗记录
{consumption_text or '（暂无消耗记录）'}

## 跟进记录（学管沟通日志）
{activities_text or '（暂无跟进记录）'}

## 生成要求

请按以下结构生成学情报告（纯文本，不要markdown格式）：

【学员概况】学生基本信息、课程目标、当前整体进度的一句话总结。

【课时进度】详细说明课时包的使用情况：总课时、已消耗课时、剩余课时、消耗比例、有效期。如果临近耗尽要提醒续费。

【近期课程详情】逐一说明近期上课情况：上了什么内容、学生表现如何、出勤情况。

【学习成果评估】综合评估学生在该科目上的进步情况。知识点掌握程度、作业完成质量、考试成绩变化（如有）。

【学管综合评价】学管师从整体角度对学生的学习态度、时间管理、配合度等方面进行评价。

【后续学习计划】建议的后续课程重点、频率调整建议、备考/作业支持计划。

【续费/加课建议】如果课时即将用尽，给出续费建议。如果有余力加课，给出加课建议。

整篇报告控制在500-800字。语气专业、温暖，体现学管的用心和关注。"""


# ─── Report Generation ───────────────────────────────────────────────────────

REPORT_TYPES = {
    'post_class': {
        'name': '课后反馈',
        'temperature': 0.3,
        'prompt_builder': _build_post_class_prompt,
    },
    'feedback': {
        'name': '客户反馈',
        'temperature': 0.4,
        'prompt_builder': _build_feedback_prompt,
    },
    'academic_report': {
        'name': '学情报告',
        'temperature': 0.4,
        'prompt_builder': _build_academic_report_prompt,
    },
}


def generate_report(report_type, data):
    """Generate an AI report of the given type.

    Args:
        report_type: 'post_class', 'feedback', or 'academic_report'
        data: dict containing all needed context (student info, activities, etc.)

    Returns:
        dict with {'content': str, 'title': str} or {'error': str}
    """
    tpl = REPORT_TYPES.get(report_type)
    if not tpl:
        return {'error': f'未知报告类型: {report_type}'}

    user_prompt = tpl['prompt_builder'](data)

    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT_BASE},
        {'role': 'user', 'content': user_prompt},
    ]

    result = ask_deepseek(messages, temperature=tpl['temperature'], max_tokens=3072)

    if isinstance(result, str) and (result.startswith('API Error') or result.startswith('Error:')):
        return {'error': result}

    if isinstance(result, str):
        return {
            'content': result.strip(),
            'title': _generate_title(report_type, data.get('student_name', '')),
        }

    return {'error': f'AI返回异常: {str(result)[:200]}'}


def _generate_title(report_type, student_name):
    """Generate a human-readable title for the report."""
    from datetime import date
    today = date.today().isoformat()
    titles = {
        'post_class': f'课后反馈 - {student_name} - {today}',
        'feedback': f'客户反馈 - {student_name} - {today}',
        'academic_report': f'学情报告 - {student_name} - {today}',
    }
    return titles.get(report_type, f'报告 - {student_name} - {today}')


def _get_available_fields():
    """Return fields needed for each report type (for frontend reference)."""
    return {
        'post_class': {
            'description': '每节课后，结合ClassIn AI总结生成课后反馈',
            'required_context': ['student_name', 'topic', 'duration_minutes', 'lesson_time'],
            'optional_context': ['classin_summary', 'teacher_notes', 'subject', 'country'],
        },
        'feedback': {
            'description': '学管定期反馈学生学习近况给家长/学生',
            'required_context': ['student_name', 'activities', 'packages'],
            'optional_context': ['recent_schedules', 'grade', 'country', 'subject', 'status'],
        },
        'academic_report': {
            'description': '综合性学习进展报告，含课时消耗、课程记录、学管评估',
            'required_context': ['student_name', 'packages'],
            'optional_context': ['activities', 'recent_schedules', 'recent_consumptions', 'grade', 'country', 'subject'],
        },
    }
