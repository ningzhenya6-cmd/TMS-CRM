#!/usr/bin/env python3
"""
课后反馈 AI 生成器
用法: python3 feedback_generator.py <classin_link>
输出: JSON (content_covered, student_performance, difficulties, etc.)
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error

# API 配置
API_KEY = ""
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip()
                break

if not API_KEY:
    API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
PIPELINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline.py")


def call_llm(messages, temperature=0.3, max_tokens=2000):
    """调用 DeepSeek API"""
    if not API_KEY:
        return {"error": "DEEPSEEK_API_KEY 未配置"}

    data = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        API_URL, data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read())
        return {
            "content": result["choices"][0]["message"]["content"],
            "usage": result.get("usage", {}),
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"error": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def run_pipeline(classin_link, timeout=600):
    """调用 pipeline.py，从 JSON 输出中解析 (info, transcript, error)"""
    if not os.path.exists(PIPELINE_PATH):
        return None, "", f"pipeline.py 不存在: {PIPELINE_PATH}"

    try:
        result = subprocess.run(
            ["python3", PIPELINE_PATH, classin_link],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, "", "pipeline 执行超时（超过10分钟）"
    except FileNotFoundError:
        return None, "", "python3 未找到"

    if result.returncode != 0:
        return None, "", f"pipeline 失败: {result.stderr[:300]}"

    # 从 stdout 中提取 __JSON_RESULT__ 后的 JSON 行
    output = result.stdout
    marker = "__JSON_RESULT__"
    idx = output.find(marker)
    if idx < 0:
        return None, "", "pipeline 输出中未找到 JSON 结果标记"

    json_line = output[idx + len(marker):].strip().split("\n")[0]
    try:
        data = json.loads(json_line)
    except json.JSONDecodeError:
        return None, "", f"pipeline JSON 解析失败: {json_line[:200]}"

    info = data.get("info", {})
    transcript = data.get("transcript", "")
    feedback_text = data.get("feedback_text", "")
    return info, transcript, None, feedback_text


def structure_feedback(feedback_text, info):
    """用 LLM 将 pipeline 已生成的反馈文本拆分为结构化字段（廉价调用）"""
    if not feedback_text or len(feedback_text) < 20:
        return {"error": "反馈文本过短"}

    system_prompt = """你是一位数据整理助手。将一段课后反馈文本解析为结构化 JSON，提取以下字段：

客观字段（必须忠于原文，不添加主观评价）：
- content_covered: 本节课教学内容（2-4句话）
- student_performance: 学生课堂表现（1-3句话，只描述事实，如"能正确回答XX题""在某知识点上犯错"）
- difficulties: 学习难点/吸收情况（1-3句话，没有则写"无明显难点"）
- homework_completion: 作业完成情况（1-2句话）
- next_focus: 下次课重点建议（1-2句话）

分析字段（供学管/班主任内部参考，可以加入你的专业分析）：
- teacher_notes: 教师综合评语（2-4句话）。包含：对本堂课的整体观察、学生反馈的困扰、老师的实质性建议、AI 观察到的学习模式。这部分是给工作人员看的，可以有自己的分析和判断。

输出纯 JSON，不要 markdown 代码块。"""

    user_prompt = f"""学生：{info.get('student', '未知')}
课程：{info.get('course', '未知')}

反馈原文：
{feedback_text[:3000]}

请输出 JSON："""

    result = call_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ], temperature=0.1, max_tokens=1000)

    if "error" in result:
        return result

    content = result["content"].strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)

    try:
        parsed = json.loads(content)
        defaults = {
            "content_covered": "", "student_performance": "",
            "difficulties": "", "homework_completion": "",
            "teacher_notes": "", "next_focus": "",
        }
        for k in defaults:
            if k not in parsed or not parsed[k]:
                parsed[k] = defaults[k]
        return parsed
    except json.JSONDecodeError:
        return {
            "content_covered": content[:200],
            "_parse_error": "结构化解析失败，返回原文片段",
            "_raw": content,
        }


def generate_structured_feedback(info, transcript):
    """用 LLM 生成结构化反馈"""
    if not transcript or len(transcript) < 50:
        return {"error": "转录文本过短或为空"}

    # 截断转录（避免超出 token 限制）
    max_chars = 6000
    truncated = transcript[:max_chars]
    if len(transcript) > max_chars:
        truncated += "\n\n[...以下内容因长度限制已截断...]"

    system_prompt = """你是一位留学生学科辅导老师，负责写课后反馈。请根据课堂录音转录和学生信息，生成结构化的课后反馈。

采用**两层结构**：

【第一层：客观字段】严格忠于课堂转录，只描述事实，不做主观评价
- content_covered: 本节课教学内容（2-4句话）
- student_performance: 学生课堂表现（1-3句话）。只写客观事实，如："能正确回答XX题""在某知识点上反复出错""学生主动说对XX感到困惑""老师建议用XX方法练习"
- difficulties: 课堂中暴露的具体难点（1-3句话，没有则写"无明显难点"）
- homework_completion: 作业完成情况（1-2句话）
- next_focus: 下次课重点（1-2句话）

【第二层：分析字段】供学管/班主任内部参考，可以加入你的专业分析
- teacher_notes: 综合评语（3-5句话）。包含：
  a) 这堂课的整体情况概述
  b) 学生反映的困扰和老师给的实质性建议
  c) AI 观察到的学习模式和值得关注的点
  d) 给学管和班主任的参考建议
  这部分是写给工作人员看的，允许有自己的判断和分析。

输出纯 JSON，不要 markdown 代码块。"""

    user_prompt = f"""学生信息：
姓名：{info.get('student', '未知')}
课程：{info.get('course', '未知')}
日期：{info.get('date', '未知')}
时长：{info.get('duration', '未知')}
教师：{info.get('teacher', '未知')}

课堂录音转录：
{truncated}

请输出 JSON："""

    result = call_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ], temperature=0.3, max_tokens=1500)

    if "error" in result:
        return result

    content = result["content"].strip()

    # 尝试解析 JSON
    # 去除可能的 markdown 代码块标记
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)

    try:
        parsed = json.loads(content)
        # 确保所有字段都存在
        defaults = {
            "content_covered": "",
            "student_performance": "",
            "difficulties": "",
            "homework_completion": "",
            "teacher_notes": "",
            "next_focus": "",
        }
        for k in defaults:
            if k not in parsed or not parsed[k]:
                parsed[k] = defaults[k]
        return parsed
    except json.JSONDecodeError:
        # 如果无法解析为 JSON，尝试从文本中提取
        return {
            "content_covered": content[:200],
            "student_performance": "",
            "difficulties": "",
            "homework_completion": "",
            "teacher_notes": "",
            "next_focus": "",
            "_parse_error": "LLM 返回非 JSON 格式，已作为纯文本保存",
            "_raw": content,
        }


def main(classin_link):
    """主流程：pipeline(v2) → 结构化 → JSON"""
    print(f"[feedback_generator] 处理链接: {classin_link[:60]}...", file=sys.stderr)

    # Step 1: 调用 pipeline v2 提取信息 + 转录 + 反馈
    print("[feedback_generator] Step 1/3: 调用 pipeline...", file=sys.stderr)
    info, transcript, error, feedback_text = run_pipeline(classin_link)

    if error:
        result = {"error": error}
        print(json.dumps(result, ensure_ascii=False))
        return

    print(f"[feedback_generator] 转录: {len(transcript)}字", file=sys.stderr)
    print(f"[feedback_generator] 学生: {info.get('student', '?')} 教师: {info.get('teacher', '?')}", file=sys.stderr)

    # Step 2: 获取结构化反馈（始终用完整转录生成，确保 teacher_notes 有充分上下文）
    print("[feedback_generator] Step 2/3: 生成结构化反馈...", file=sys.stderr)
    print(f"[feedback_generator] 基于 {len(transcript)} 字转录生成...", file=sys.stderr)
    feedback = generate_structured_feedback(info, transcript)

    if "error" in feedback:
        result = {"error": feedback["error"]}
        print(json.dumps(result, ensure_ascii=False))
        return

    # Step 3: 输出 JSON
    print("[feedback_generator] Step 3/3: 输出结果", file=sys.stderr)
    result = {
        "status": "ok",
        "feedback": {
            "content_covered": feedback.get("content_covered", ""),
            "student_performance": feedback.get("student_performance", ""),
            "difficulties": feedback.get("difficulties", ""),
            "homework_completion": feedback.get("homework_completion", ""),
            "teacher_notes": feedback.get("teacher_notes", ""),
            "next_focus": feedback.get("next_focus", ""),
        },
        "info": info,
        "transcript_length": len(transcript),
    }

    if "_parse_error" in feedback:
        result["_parse_warning"] = feedback["_parse_error"]
        result["_raw"] = feedback.get("_raw", "")

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "用法: python3 feedback_generator.py <classin_link>"}))
        sys.exit(1)

    main(sys.argv[1])
