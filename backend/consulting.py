"""
学业风险分析报告 + 行前准备规划 API
直接调用 DeepSeek API（无需 pipeline 子进程），在后台线程中生成报告
"""
import json
import os
import re
import threading
import time
import datetime
import urllib.request
import urllib.error
from io import BytesIO
from router import get, post, put, delete
from utils import json_response, error_response, ok_response, add_oplog
from db import query, query_one, execute, execute_lastrowid
from permissions import can
from export import generate_docx, generate_pdf


# ═══════════════════════════════════════════
# AI 生成进度跟踪（内存）
# ═══════════════════════════════════════════
_gen_progress = {}


def _set_progress(report_id, progress, step, status="generating"):
    _gen_progress[report_id] = {
        "progress": progress, "step": step, "status": status,
    }


def _load_api_key():
    """读取 DeepSeek API Key"""
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return os.environ.get("DEEPSEEK_API_KEY", "")


def _call_deepseek(messages, temperature=0.3, max_tokens=3000, enable_search=False):
    """调用 DeepSeek API"""
    api_key = _load_api_key()
    if not api_key:
        return {"error": "DEEPSEEK_API_KEY 未配置"}

    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if enable_search:
        payload["enable_search"] = True

    data = json.dumps(payload).encode()

    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
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


def _run_generation(report_id, lead_id, skip_research=False):
    """后台线程：调用 DeepSeek 生成学业风险分析报告"""
    try:
        # 1. 读取报告 + 线索信息
        report = query_one("SELECT * FROM consulting_reports WHERE id=?", (report_id,))
        if not report:
            _set_progress(report_id, 0, "报告不存在", "error")
            return

        lead = query_one("SELECT * FROM leads WHERE id=?", (lead_id,))
        if not lead:
            _set_progress(report_id, 0, "学生不存在", "error")
            return

        # 1b. 联网搜索目标院校录取要求（统一报告，非 skip 时执行）
        search_content = ""
        if not skip_research:
            _set_progress(report_id, 5, "正在联网搜索院校信息...", "researching")
            school = report.get('target_school', '')
            major = report.get('target_major', '')
            if school and major:
                search_prompt = (
                    f"请搜索 {school} 的 {major} 专业的官方信息，"
                    f"包括：1) GPA/平均分要求 2) 语言成绩要求（雅思/托福等）"
                    f" 3) 前置修读科目要求 4) 作品集/面试/其他考核形式"
                    f" 5) 该专业课程特色、学制、学分。请用中文回答，提供具体的数据和信息。"
                )
                search_result = _call_deepseek(
                    [{"role": "user", "content": search_prompt}],
                    temperature=0.1, max_tokens=2000, enable_search=True,
                )
                if "error" not in search_result:
                    search_content = search_result["content"]
                    _set_progress(report_id, 20, "院校信息已获取，正在分析学生情况...")
                else:
                    _set_progress(report_id, 5, "联网获取信息失败，将基于 AI 知识库直接分析")
            else:
                _set_progress(report_id, 5, "目标院校信息不完整，跳过联网搜索")

        _set_progress(report_id, 10, "正在分析学生背景...")

        # 2. 构造 prompt — 统一学业风险与规划报告
        system_prompt = """你是一位资深的留学学业规划顾问。请根据学生情况描述，生成一份「学业风险与规划报告」。

报告面向学生和家长，语言专业但易懂。

**差距分析必须是多维度的，不只看前置知识。** 影响学业成功的因素包括但不限于：
- 前置知识基础（学科知识跨度）
- 学习习惯与方法（高中 vs 大学/国内 vs 国外的学习方式差异）
- 语言能力转型（应试英语→学术英语、专业术语、法律/商业/学术写作）
- 心理压力与心态（学术压力、陌生环境、孤独感、想家）
- 教育体系适应（教学方式、考核形式、自主学习要求）
- 文化与环境适应（海外生活、天气、饮食、社交）
- 时间管理与自我驱动力

根据学生具体情况，只分析真正相关的维度，不套固定模板。

输出必须为 JSON 格式，包含以下字段：
{
  "report_title": "报告标题（如：211英专→悉尼大学商法硕士的规划和风险）",
  "student_profile": {
    "background": "学生基础画像（一段话概括当前院校、专业、年级、成绩等）",
    "target": "目标描述（一段话）",
    "key_info": { "当前院校": "", "目标院校": "", "目标专业": "", "当前成绩": "", "语言成绩": "", "申请阶段": "" }
  },
  "program_overview": "目标院校专业概览（学制、学分、特色等），没有足够信息写'待补充'",
  "core_courses": ["推荐的核心课程方向（如有）"],
  "gap_analysis": [
    {
      "dimension": "分析维度（如前置知识、学习习惯、语言转型、心理适应等）",
      "current": "学生当前水平",
      "required": "目标要求",
      "gap": "差距分析",
      "risk": "low/medium/high",
      "improvement_strategy": "具体改进策略"
    }
  ],
  "preparation_plan": [
    {
      "phase": "阶段名称（如：签证等待期/开学前/第一学期/长期）",
      "tasks": ["具体任务"],
      "timeline": "时间线",
      "goal": "目标"
    }
  ],
  "overall_assessment": "综合评估（包含学术、心理、适应等多维度判断）",
  "risk_level": "low/medium/high",
  "recommendations": ["具体建议列表（3-5条，可执行）"],
  "consultant_tips": "给顾问的沟通建议（内部参考，包括如何与家长/学生沟通关键问题）"
}

请确保：
- gap_analysis 维度根据学生实际情况动态确定，不限于学术，涵盖学习习惯、心理、适应等
- recommendations 要具体到可执行层面
- 时间线根据当前日期给出具体月份安排
- consultant_tips 仍要输出，供内部参考"""


        current_date = datetime.datetime.now().strftime("%Y年%m月%d日")
        user_prompt = f"""当前日期：{current_date}

学生姓名：{lead.get('name', '未知')}

【学生情况描述】
{report.get('additional_info', '未提供详细情况')}

【辅助信息】
目标国家：{report.get('target_country', '')}
目标院校：{report.get('target_school', '')}
目标专业：{report.get('target_major', '')}
当前院校：{report.get('current_school', '')}
当前成绩：{report.get('gpa', '')}
语言成绩：{report.get('language_scores', '')}
"""

        # 如果有联网搜索到的院校信息，追加到 prompt 中
        if search_content:
            user_prompt += f"""

【联网搜索获取的院校信息】
{search_content[:2500]}"""

        _set_progress(report_id, 30, "正在调用 AI 分析引擎...")

        result = _call_deepseek([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], temperature=0.3, max_tokens=4000)

        if "error" in result:
            err_msg = result["error"]
            _set_progress(report_id, 0, f"AI 调用失败: {err_msg}", "error")
            execute(
                "UPDATE consulting_reports SET status='error', error_message=?, updated_at=datetime('now','localtime') WHERE id=?",
                (err_msg, report_id),
            )
            return

        _set_progress(report_id, 70, "正在解析分析结果...")

        content = result["content"].strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

        parsed = json.loads(content)
        
        # 分离公开内容和内部参考
        tips = parsed.pop("consultant_tips", "")
        report_json = json.dumps(parsed, ensure_ascii=False)
        full_json = json.dumps({**parsed, "consultant_tips": tips}, ensure_ascii=False)
        
        risk_level = parsed.get("risk_level", "medium")
        summary = parsed.get("overall_assessment", "")[:200] or parsed.get("student_profile", {}).get("background", "")[:200]
        report_title = parsed.get("report_title", "")

        _set_progress(report_id, 90, "正在保存报告...")

        execute(
            """UPDATE consulting_reports
               SET report_json=?, risk_level=?, summary=?,
                   program_url=?, program_courses=?,
                   status='completed', progress=100, updated_at=datetime('now','localtime')
               WHERE id=?""",
            (report_json, risk_level, summary, report_title, full_json, report_id),
        )

        _gen_progress[report_id] = {
            "progress": 100, "step": "✅ 报告生成完成！", "status": "done",
            "result": parsed,
        }

        # 5 分钟后清理进度
        def _cleanup():
            time.sleep(300)
            _gen_progress.pop(report_id, None)
        threading.Thread(target=_cleanup, daemon=True).start()

    except json.JSONDecodeError:
        _set_progress(report_id, 0, "AI 返回格式异常，JSON 解析失败", "error")
        execute(
            "UPDATE consulting_reports SET status='error', error_message=?, updated_at=datetime('now','localtime') WHERE id=?",
            ("AI 返回的 JSON 格式异常", report_id),
        )
    except Exception as e:
        _set_progress(report_id, 0, str(e), "error")
        execute(
            "UPDATE consulting_reports SET status='error', error_message=?, updated_at=datetime('now','localtime') WHERE id=?",
            (str(e), report_id),
        )


def _run_generation_preparation(report_id, lead_id):
    """
    后台线程：调用 DeepSeek 生成行前准备规划报告
    基于真实的课程数据（由 Claude 从学校官网抓取）+ 学生背景，为每门课输出准备建议
    """
    try:
        # 1. 读取报告 + 线索信息
        report = query_one("SELECT * FROM consulting_reports WHERE id=?", (report_id,))
        if not report:
            _set_progress(report_id, 0, "报告不存在", "error")
            return

        lead = query_one("SELECT * FROM leads WHERE id=?", (lead_id,))
        if not lead:
            _set_progress(report_id, 0, "学生不存在", "error")
            return

        _set_progress(report_id, 10, "正在分析学生背景...")

        # 2. 获取课程数据（如果已由 Claude 提交）
        program_courses = report.get("program_courses", "")

        _set_progress(report_id, 30, "正在分析课程匹配度...")

        # 3. 构造 prompt
        system_prompt = """你是一位资深的留学行前学业规划顾问，帮助学生做好目标专业方向的入学前学术准备。

你的任务是：基于目标院校专业的**实际课程设置**和学生当前的学术背景，为每门课程制定详细的准备计划。无论学生是否已拿到 Offer，都可以根据目标院校专业的课程设置给出针对性的准备建议。

请严格确保分析客观、具体、可执行。每门课的准备建议必须基于该课程的实际内容和要求。

输出必须为 JSON 格式，包含以下字段：
{
  "program_overview": "项目总览描述（学制、总学分、项目特色等，2-3句话）",
  "courses": [
    {
      "course_code": "课程代码",
      "course_name": "课程名称",
      "course_description": "课程内容概述",
      "core_topics": ["核心主题列表"],
      "prerequisites_expected": "该课程要求的前置知识/基础",
      "student_readiness": "low/medium/high",
      "readiness_analysis": "基于学生当前背景的 readiness 分析（1-2句话）",
      "preparation_actions": ["具体的准备行动建议列表"],
      "assessment_format": "该课程的考核形式说明",
      "recommended_resources": ["推荐的学习资源"]
    }
  ],
  "overall_timeline": "整体的准备时间线建议",
  "priority_focus": "最需要优先关注的方向和原因",
  "advisor_notes": "给顾问的沟通建议，帮助顾问与学生和家长沟通"
}

请确保：
- 每门课的 preparation_actions 要具体可执行（如"每周完成XX练习"而非"好好学习"）
- student_readiness 要基于学生实际背景客观评估
- recommended_resources 要给出具体的学习资源名称
- 整体时间线要基于当前日期给出**具体的月份安排**，如"建议从2026年6月开始准备...6-7月聚焦XX课程...每周投入8-10小时"，不要写笼统的"提前3个月"
- 确保时间线中出现的年份/月份与当前日期一致，不要使用过去的日期"""

        target_level = report.get('target_level', '') or ''
        level_hint = ""
        if target_level:
            level_map = {
                "high_to_bachelor": "当前为高中阶段，目标为申请本科",
                "bachelor_to_master": "当前为本科阶段，目标为申请硕士",
                "master_to_phd": "当前为硕士阶段，目标为申请博士",
                "bachelor_to_phd": "当前为本科阶段，目标为直博",
            }
            level_hint = "\n申请阶段：" + level_map.get(target_level, target_level)
            if target_level in ("high_to_bachelor",):
                level_hint += "\n提示：该阶段应重点关注高中成绩、语言考试、背景提升活动等"
            elif target_level in ("bachelor_to_master",):
                level_hint += "\n提示：该阶段应重点关注GPA、科研/实习经历、语言成绩、GRE/GMAT等"
            elif target_level in ("master_to_phd", "bachelor_to_phd"):
                level_hint += "\n提示：该阶段应重点关注科研经历、论文发表、推荐信、研究方向匹配等"

        # 构建用户 prompt — 如果有真实课程数据则包含
        current_date = datetime.datetime.now().strftime("%Y年%m月%d日")
        user_prompt = f"""当前日期：{current_date}

学生信息：
姓名：{lead.get('name', '未知')}
当前年级：{lead.get('grade', '未知')}
意向国家：{lead.get('country', '未知')}
备注：{lead.get('remark', '无')}

目标院校：{report.get('target_school', '')}
目标专业：{report.get('target_major', '')}
目标国家：{report.get('target_country', '')}
{level_hint}

学生当前情况：
当前院校：{report.get('current_school', '未提供')}
当前年级：{report.get('current_grade', '未提供')}
GPA：{report.get('gpa', '未提供')}
语言成绩：{report.get('language_scores', '未提供')}
前置修读科目及成绩：{report.get('prerequisite_courses', '未提供')}

顾问补充备注：{report.get('additional_info', '无')}"""

        # 如果有真实的课程数据，追加到 prompt 中
        if program_courses:
            user_prompt += f"""

【目标院校专业的实际课程设置】
以下是从学校官网获取的真实课程信息，请基于此进行分析和规划：

{program_courses}

请基于以上每门课程的实际信息，结合学生背景，生成详细的课程级准备规划。"""

        _set_progress(report_id, 50, "正在调用 AI 规划引擎...")

        result = _call_deepseek([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ], temperature=0.3, max_tokens=4000)

        if "error" in result:
            err_msg = result["error"]
            _set_progress(report_id, 0, f"AI 调用失败: {err_msg}", "error")
            execute(
                "UPDATE consulting_reports SET status='error', error_message=?, updated_at=datetime('now','localtime') WHERE id=?",
                (err_msg, report_id),
            )
            return

        _set_progress(report_id, 70, "正在解析规划结果...")

        content = result["content"].strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

        parsed = json.loads(content)

        # 从结果提取摘要信息
        course_count = len(parsed.get("courses", []))
        summary = f"共 {course_count} 门课程准备规划"
        risk_level = "medium"  # preparation 类型不使用 risk_level

        _set_progress(report_id, 90, "正在保存报告...")

        execute(
            """UPDATE consulting_reports
               SET report_json=?, risk_level=?, summary=?,
                   status='completed', progress=100, updated_at=datetime('now','localtime')
               WHERE id=?""",
            (json.dumps(parsed, ensure_ascii=False), risk_level, summary, report_id),
        )

        _gen_progress[report_id] = {
            "progress": 100, "step": "✅ 规划报告生成完成！", "status": "done",
            "result": parsed,
        }

        # 5 分钟后清理进度
        def _cleanup():
            time.sleep(300)
            _gen_progress.pop(report_id, None)
        threading.Thread(target=_cleanup, daemon=True).start()

    except json.JSONDecodeError:
        _set_progress(report_id, 0, "AI 返回格式异常，JSON 解析失败", "error")
        execute(
            "UPDATE consulting_reports SET status='error', error_message=?, updated_at=datetime('now','localtime') WHERE id=?",
            ("AI 返回的 JSON 格式异常", report_id),
        )
    except Exception as e:
        _set_progress(report_id, 0, str(e), "error")
        execute(
            "UPDATE consulting_reports SET status='error', error_message=?, updated_at=datetime('now','localtime') WHERE id=?",
            (str(e), report_id),
        )


# ═══════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════

@get("/api/consulting/list")
def list_all_reports(handler, token_payload, qs, body):
    """所有学业分析报告列表（跨线索）"""
    role = token_payload["role"]
    if not can(role, "consulting:view"):
        error_response(handler, "无权访问", 403)
        return

    page = int(qs.get("page", [1])[0])
    page_size = int(qs.get("page_size", [15])[0])
    search = qs.get("search", [None])[0]
    report_type = qs.get("report_type", [None])[0]

    where = ["1=1"]
    params = []

    if search:
        like = f"%{search}%"
        where.append("(l.name LIKE ? OR l.phone LIKE ?)")
        params.extend([like, like])
    if report_type and report_type in ("risk", "preparation"):
        where.append("cr.report_type=?")
        params.append(report_type)

    where_sql = " AND ".join(where)

    total = query_one(
        f"SELECT COUNT(*) as cnt FROM consulting_reports cr JOIN leads l ON cr.lead_id=l.id WHERE {where_sql}",
        tuple(params),
    )["cnt"]

    offset = (page - 1) * page_size
    rows = query(
        f"""SELECT cr.id, cr.lead_id, cr.target_country, cr.target_school, cr.target_major,
                   cr.target_level, cr.risk_level, cr.summary, cr.status, cr.progress,
                   cr.report_type, cr.program_url,
                   cr.created_at, cr.updated_at,
                   l.name as lead_name, l.phone as lead_phone,
                   u.display_name as creator_name
            FROM consulting_reports cr
            JOIN leads l ON cr.lead_id = l.id
            LEFT JOIN users u ON cr.created_by = u.id
            WHERE {where_sql}
            ORDER BY cr.created_at DESC
            LIMIT ? OFFSET ?""",
        tuple(params) + (page_size, offset),
    )

    ok_response(handler, {
        "total": total, "page": page, "page_size": page_size, "items": rows,
    })


@get("/api/leads/{lead_id}/consulting")
def list_lead_reports(handler, token_payload, qs, body, lead_id=None):
    """列出某个线索的所有报告（不含完整 report_json）"""
    role = token_payload["role"]
    if not can(role, "consulting:view"):
        error_response(handler, "无权访问", 403)
        return

    rows = query(
        """SELECT cr.id, cr.target_country, cr.target_school, cr.target_major,
                  cr.target_level, cr.risk_level, cr.summary, cr.status, cr.progress,
                  cr.report_type, cr.program_url,
                  cr.created_at, cr.updated_at,
                  u.display_name as creator_name
           FROM consulting_reports cr
           LEFT JOIN users u ON cr.created_by = u.id
           WHERE cr.lead_id=?
           ORDER BY cr.created_at DESC""",
        (int(lead_id),),
    )
    ok_response(handler, rows)


@post("/api/leads/{lead_id}/consulting")
def create_report(handler, token_payload, qs, body, lead_id=None):
    """创建草稿报告"""
    role = token_payload["role"]
    if not can(role, "consulting:create"):
        error_response(handler, "无权操作", 403)
        return

    target_country = (body.get("target_country") or "").strip()
    target_school = (body.get("target_school") or "").strip()
    target_major = (body.get("target_major") or "").strip()
    report_type = (body.get("report_type") or "risk").strip()
    target_level = (body.get("target_level") or "").strip()

    if report_type not in ("risk", "preparation", "unified"):
        error_response(handler, "报告类型无效（risk / preparation）")
        return

    if not target_country or not target_school or not target_major:
        error_response(handler, "目标国家、院校和专业不能为空")
        return

    rid = execute_lastrowid(
        """INSERT INTO consulting_reports
           (lead_id, target_country, target_school, target_major,
            current_school, current_grade, gpa, language_scores,
            prerequisite_courses, additional_info, created_by,
            report_type, program_url, target_level)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (int(lead_id), target_country, target_school, target_major,
         (body.get("current_school") or "").strip(),
         (body.get("current_grade") or "").strip(),
         (body.get("gpa") or "").strip(),
         (body.get("language_scores") or "").strip(),
         (body.get("prerequisite_courses") or "").strip(),
         (body.get("additional_info") or "").strip(),
         token_payload["sub"],
         report_type,
         (body.get("program_url") or "").strip(),
         target_level),
    )

    report_type_label = "行前准备规划" if report_type == "preparation" else "学业分析报告"
    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "create", "consulting_report", rid,
              f"创建{report_type_label}: {target_school} {target_major}")

    report = query_one("SELECT * FROM consulting_reports WHERE id=?", (rid,))
    ok_response(handler, report, 201)


@post("/api/leads/{lead_id}/consulting/{report_id}/generate")
def trigger_generate(handler, token_payload, qs, body, lead_id=None, report_id=None):
    """触发 AI 生成"""
    role = token_payload["role"]
    if not can(role, "consulting:generate"):
        error_response(handler, "无权操作", 403)
        return

    report = query_one(
        "SELECT * FROM consulting_reports WHERE id=? AND lead_id=?",
        (int(report_id), int(lead_id)),
    )
    if not report:
        error_response(handler, "报告不存在", 404)
        return

    if report["status"] == "generating":
        error_response(handler, "该报告正在生成中", 409)
        return

    if report["status"] == "completed":
        error_response(handler, "该报告已生成完成，如需重新生成请先删除", 409)
        return

    rid = int(report_id)
    report_type = report.get("report_type", "risk")
    force = qs.get("force", [None])[0]

    # ── 行前准备规划：检查课程数据（缓存/已有） ──
    if report_type == "preparation" and force != "1":
        program_courses = report.get("program_courses") or ""
        if not program_courses:
            # 尝试从缓存读取
            school = report.get("target_school", "")
            major = report.get("target_major", "")
            cached = None
            if school and major:
                cached = query_one(
                    "SELECT courses_json, source_url FROM curriculum_cache WHERE school=? AND major=?",
                    (school, major),
                )
            if cached and cached.get("courses_json"):
                # 命中缓存 → 自动填入报告的 program_courses
                program_courses = cached["courses_json"]
                execute(
                    "UPDATE consulting_reports SET program_courses=?, program_url=?, updated_at=datetime('now','localtime') WHERE id=?",
                    (program_courses, cached.get("source_url", "") or "", rid),
                )
            else:
                # 无缓存 → 返回 researching 状态，让 Claude 去抓取
                _gen_progress[rid] = {"progress": 5, "step": "正在搜索学校官网...", "status": "researching"}
                execute(
                    "UPDATE consulting_reports SET status='researching', progress=5, updated_at=datetime('now','localtime') WHERE id=?",
                    (rid,),
                )
                ok_response(handler, {
                    "status": "researching", "progress": 5,
                    "step": "正在搜索学校官网...",
                    "message": "正在联网获取课程信息，获取后即可生成规划",
                })
                return

    # ── 学业风险分析：联网搜索院校录取要求 ──
    if report_type in ("risk", "unified") and force != "1":
        _gen_progress[rid] = {"progress": 5, "step": "正在联网搜索院校录取要求...", "status": "researching"}
        execute(
            "UPDATE consulting_reports SET status='researching', progress=5, updated_at=datetime('now','localtime') WHERE id=?",
            (rid,),
        )
        # 线程立即启动，内部先联网搜索再生成报告
        t = threading.Thread(target=_run_generation, args=(rid, int(lead_id)), daemon=True)
        t.start()
        ok_response(handler, {
            "status": "researching", "progress": 5,
            "step": "正在联网搜索院校录取要求...",
            "message": "正在在线搜索目标院校的录取要求信息，搜索完成后自动生成分析报告",
        })
        return

    # ── 启动生成线程 ──
    execute(
        "UPDATE consulting_reports SET status='generating', progress=0, updated_at=datetime('now','localtime') WHERE id=?",
        (rid,),
    )

    step_label = "启动分析引擎..."
    _gen_progress[rid] = {"progress": 0, "step": step_label, "status": "generating"}

    # force=1 时跳过联网搜索
    skip_research = (force == "1")
    t = threading.Thread(target=_run_generation, args=(rid, int(lead_id)),
                         kwargs={"skip_research": skip_research}, daemon=True)
    msg = "AI 分析已启动"
    t.start()

    ok_response(handler, {"status": "processing", "progress": 0, "step": step_label, "message": msg})


@get("/api/leads/{lead_id}/consulting/{report_id}/progress")
def get_generate_progress(handler, token_payload, qs, body, lead_id=None, report_id=None):
    """查询 AI 生成进度"""
    role = token_payload["role"]
    if not can(role, "consulting:view"):
        error_response(handler, "无权访问", 403)
        return
    rid = int(report_id)

    # 先从内存查
    task = _gen_progress.get(rid)
    if task:
        ok_response(handler, {
            "status": task.get("status", "unknown"),
            "progress": task.get("progress", 0),
            "step": task.get("step", ""),
            "error": task.get("error"),
            "result": task.get("result"),
        })
        return

    # 内存没有，从 DB 查
    report = query_one(
        "SELECT status, progress, report_json, error_message FROM consulting_reports WHERE id=?",
        (rid,),
    )
    if not report:
        ok_response(handler, {"status": "idle", "progress": 0, "step": "报告不存在"})
        return

    if report["status"] == "completed" and report["report_json"]:
        try:
            parsed = json.loads(report["report_json"])
            # 内部查看时，从 program_courses 合并 consultant_tips
            role = token_payload["role"]
            if role in ("admin", "supervisor", "consultant", "cs", "academic"):
                full_raw = report.get("program_courses") or ""
                if full_raw:
                    try:
                        full = json.loads(full_raw)
                        if "consultant_tips" in full:
                            parsed["consultant_tips"] = full["consultant_tips"]
                    except json.JSONDecodeError:
                        pass
        except json.JSONDecodeError:
            parsed = None
        ok_response(handler, {
            "status": "done", "progress": 100, "step": "报告已生成",
            "result": parsed,
        })
    elif report["status"] == "error":
        ok_response(handler, {
            "status": "error", "progress": 0,
            "step": f"❌ {report['error_message']}",
            "error": report["error_message"],
        })
    else:
        ok_response(handler, {
            "status": report["status"], "progress": report["progress"],
            "step": report["status"],
        })


@post("/api/leads/{lead_id}/consulting/{report_id}/curriculum")
def submit_curriculum(handler, token_payload, qs, body, lead_id=None, report_id=None):
    """
    提交 Claude 从学校官网抓取的课程数据
    仅 preparation 类型可使用
    """
    role = token_payload["role"]
    if not can(role, "consulting:manage"):
        error_response(handler, "无权操作", 403)
        return

    report = query_one(
        "SELECT * FROM consulting_reports WHERE id=? AND lead_id=?",
        (int(report_id), int(lead_id)),
    )
    if not report:
        error_response(handler, "报告不存在", 404)
        return

    if report.get("report_type") != "preparation":
        error_response(handler, "仅行前准备规划类型可提交课程数据", 400)
        return

    if report["status"] == "generating":
        error_response(handler, "该报告正在生成中", 409)
        return

    if report["status"] == "completed":
        error_response(handler, "该报告已生成完成，如需重新生成请先删除", 409)
        return

    program_courses = body.get("program_courses", "")
    if not program_courses:
        error_response(handler, "课程数据不能为空")
        return

    # 如果是 JSON 数组，格式化为可读文本
    if isinstance(program_courses, str):
        try:
            parsed = json.loads(program_courses)
            if isinstance(parsed, list):
                program_courses = json.dumps(parsed, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, TypeError):
            pass  # 保持原样

    execute(
        "UPDATE consulting_reports SET program_courses=?, updated_at=datetime('now','localtime') WHERE id=?",
        (program_courses, int(report_id)),
    )

    # 更新 researching 进度（前端能实时看到进展）
    rid = int(report_id)
    _gen_progress[rid] = {
        "progress": 40, "step": "课程数据已获取，可点击生成规划", "status": "researching",
    }

    # 同步保存到课程缓存（下次同学校+专业直接复用）
    school = report.get("target_school", "")
    major = report.get("target_major", "")
    if school and major:
        existing = query_one(
            "SELECT id FROM curriculum_cache WHERE school=? AND major=?",
            (school, major),
        )
        if existing:
            execute(
                "UPDATE curriculum_cache SET courses_json=?, source_url=?, created_at=datetime('now','localtime') WHERE id=?",
                (program_courses, report.get("program_url", "") or "", existing["id"]),
            )
        else:
            execute(
                "INSERT INTO curriculum_cache (school, major, courses_json, source_url) VALUES (?,?,?,?)",
                (school, major, program_courses, report.get("program_url", "") or ""),
            )

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "update", "consulting_report", int(report_id),
              "提交课程数据")

    ok_response(handler, {"message": "课程数据已提交", "program_courses": program_courses[:200] + "..." if len(program_courses) > 200 else program_courses})


@get("/api/leads/{lead_id}/consulting/{report_id}")
def get_report(handler, token_payload, qs, body, lead_id=None, report_id=None):
    """获取完整报告内容"""
    role = token_payload["role"]
    if not can(role, "consulting:view"):
        error_response(handler, "无权访问", 403)
        return

    report = query_one(
        """SELECT cr.*, l.name as lead_name, l.phone as lead_phone,
                  u.display_name as creator_name
           FROM consulting_reports cr
           JOIN leads l ON cr.lead_id = l.id
           LEFT JOIN users u ON cr.created_by = u.id
           WHERE cr.id=? AND cr.lead_id=?""",
        (int(report_id), int(lead_id)),
    )
    if not report:
        error_response(handler, "报告不存在", 404)
        return

    if report["report_json"]:
        try:
            report["report_data"] = json.loads(report["report_json"])
        except json.JSONDecodeError:
            report["report_data"] = None
    else:
        report["report_data"] = None

    ok_response(handler, report)


@put("/api/leads/{lead_id}/consulting/{report_id}")
def update_report(handler, token_payload, qs, body, lead_id=None, report_id=None):
    """更新报告信息"""
    role = token_payload["role"]
    if not can(role, "consulting:manage"):
        error_response(handler, "无权操作", 403)
        return

    report = query_one(
        "SELECT * FROM consulting_reports WHERE id=? AND lead_id=?",
        (int(report_id), int(lead_id)),
    )
    if not report:
        error_response(handler, "报告不存在", 404)
        return

    allowed = ["target_country", "target_school", "target_major",
               "current_school", "current_grade", "gpa", "language_scores",
               "prerequisite_courses", "additional_info", "target_level"]
    updates = []
    params = []
    for field in allowed:
        if field in body:
            updates.append(f"{field}=?")
            params.append((body[field] or "").strip())

    if updates:
        params.append(int(report_id))
        execute(
            f"UPDATE consulting_reports SET {','.join(updates)}, updated_at=datetime('now','localtime') WHERE id=?",
            params,
        )

    updated = query_one("SELECT * FROM consulting_reports WHERE id=?", (int(report_id),))
    ok_response(handler, updated)


@delete("/api/leads/{lead_id}/consulting/{report_id}")
def delete_report(handler, token_payload, qs, body, lead_id=None, report_id=None):
    """删除报告"""
    role = token_payload["role"]
    if not can(role, "consulting:manage"):
        error_response(handler, "无权操作", 403)
        return

    report = query_one(
        "SELECT id FROM consulting_reports WHERE id=? AND lead_id=?",
        (int(report_id), int(lead_id)),
    )
    if not report:
        error_response(handler, "报告不存在", 404)
        return

    execute("DELETE FROM consulting_reports WHERE id=?", (int(report_id),))
    _gen_progress.pop(int(report_id), None)

    report_type_label = report.get("report_type", "report") if report else "report"
    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "delete", "consulting_report", int(report_id), f"删除{report_type_label}")
    ok_response(handler, {"message": "已删除"})


@get("/api/leads/{lead_id}/consulting/{report_id}/download")
def download_report(handler, token_payload, qs, body, lead_id=None, report_id=None):
    """下载报告（Word / PDF）"""
    role = token_payload["role"]
    if not can(role, "consulting:view"):
        error_response(handler, "无权访问", 403)
        return

    fmt = qs.get("format", ["docx"])[0]
    if fmt not in ("docx", "pdf"):
        error_response(handler, "格式无效（docx / pdf）")
        return

    report = query_one(
        "SELECT * FROM consulting_reports WHERE id=? AND lead_id=?",
        (int(report_id), int(lead_id)),
    )
    if not report:
        error_response(handler, "报告不存在", 404)
        return

    if report["status"] != "completed":
        error_response(handler, "报告尚未生成完成", 400)
        return

    if not report.get("report_json"):
        error_response(handler, "报告数据为空", 400)
        return

    # 获取学生信息
    lead = query_one("SELECT * FROM leads WHERE id=?", (int(lead_id),))

    report_type = report.get("report_type", "risk")

    try:
        if fmt == "docx":
            content = generate_docx(report, lead, report_type)
            ctype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ascii_filename = "report.docx"
        else:
            content = generate_pdf(report, lead, report_type)
            ctype = "application/pdf"
            ascii_filename = "report.pdf"

        handler.send_response(200)
        handler.send_header("Content-Type", ctype)
        handler.send_header("Content-Length", str(len(content)))
        handler.send_header("Content-Disposition", f'attachment; filename="{ascii_filename}"')
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(content)
    except Exception as e:
        error_response(handler, f"文档生成失败: {e}", 500)
