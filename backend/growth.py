"""
成长档案 API — 课后反馈、考试成绩、录取结果、成长时间线
"""
import json
import logging
import os
import re
import threading
import time
import urllib.request
import urllib.error
from router import get, post, put, delete
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid

logger = logging.getLogger(__name__)

# 统一用 query() 返回列表
from permissions import can, scope_where
from classin_api import fetch_transcript


# ═══════════════════════════════════════════
# 课后反馈
# ═══════════════════════════════════════════

@get("/api/schedules/{schedule_id}/feedback")
def get_feedback(handler, token_payload, qs, body, schedule_id=None):
    """查某节课的课后反馈（含课时包进度）"""
    row = query_one(
        """SELECT lf.*, u.display_name as creator_name
           FROM lesson_feedback lf
           LEFT JOIN users u ON lf.created_by = u.id
           WHERE lf.schedule_id=?""",
        (int(schedule_id),),
    )
    result = {"feedback": row or {}}
    # 附加课时包进度
    sched = query_one("SELECT lead_id FROM schedules WHERE id=?", (int(schedule_id),))
    if sched:
        pkg_info = {"total_hours": 0, "used_hours": 0, "remaining_hours": 0}
        _add_package_info(sched["lead_id"], pkg_info)
        result["package_info"] = pkg_info
    ok_response(handler, result)


@delete("/api/schedules/{schedule_id}/feedback")
def delete_feedback(handler, token_payload, qs, body, schedule_id=None):
    """删除课后反馈（用于重新生成）"""
    role = token_payload["role"]
    if not can(role, "growth:manage"):
        error_response(handler, "无权操作", 403)
        return
    execute("DELETE FROM lesson_feedback WHERE schedule_id=?", (int(schedule_id),))
    ok_response(handler, {"message": "反馈已删除"})


@post("/api/schedules/{schedule_id}/feedback")
def save_feedback(handler, token_payload, qs, body, schedule_id=None):
    """创建或更新课后反馈"""
    role = token_payload["role"]
    if not can(role, "growth:manage"):
        error_response(handler, "无权操作", 403)
        return

    schedule = query_one("SELECT * FROM schedules WHERE id=?", (int(schedule_id),))
    if not schedule:
        error_response(handler, "排课不存在", 404)
        return

    lead_id = schedule["lead_id"]
    uid = token_payload["sub"]

    fields = {
        "classin_link": (body.get("classin_link") or "").strip(),
        "content_covered": (body.get("content_covered") or "").strip(),
        "student_performance": (body.get("student_performance") or "").strip(),
        "difficulties": (body.get("difficulties") or "").strip(),
        "homework_completion": (body.get("homework_completion") or "").strip(),
        "teacher_notes": (body.get("teacher_notes") or "").strip(),
        "next_focus": (body.get("next_focus") or "").strip(),
    }

    existing = query_one("SELECT id FROM lesson_feedback WHERE schedule_id=?", (int(schedule_id),))

    if existing:
        # 更新
        sets = ", ".join(f"{k}=?" for k in fields)
        params = list(fields.values()) + [int(schedule_id)]
        execute(f"UPDATE lesson_feedback SET {sets}, updated_at=datetime('now','localtime') WHERE schedule_id=?", params)
        add_oplog(uid, token_payload.get("name", ""), "update", "lesson_feedback", existing["id"],
                  f"更新课后反馈: schedule#{schedule_id}")
        fb = query_one("SELECT * FROM lesson_feedback WHERE id=?", (existing["id"],))
        ok_response(handler, fb)
    else:
        # 新建
        fid = execute_lastrowid(
            """INSERT INTO lesson_feedback
               (schedule_id, lead_id, classin_link, content_covered, student_performance,
                difficulties, homework_completion, teacher_notes, next_focus, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (int(schedule_id), lead_id, fields["classin_link"], fields["content_covered"],
             fields["student_performance"], fields["difficulties"], fields["homework_completion"],
             fields["teacher_notes"], fields["next_focus"], uid),
        )
        add_oplog(uid, token_payload.get("name", ""), "create", "lesson_feedback", fid,
                  f"创建课后反馈: schedule#{schedule_id}")
        fb = query_one("SELECT * FROM lesson_feedback WHERE id=?", (fid,))
        ok_response(handler, fb, 201)


# ═══════════════════════════════════════════
# AI 生成进度跟踪（内存）
# ═══════════════════════════════════════════
_gen_progress = {}  # schedule_id → {progress, step, status, result, error}


def _add_package_info(lead_id, info):
    """查询学生课时包进度，填入 info 字典"""
    packages = query(
        """SELECT p.* FROM packages p
           JOIN contracts c ON p.contract_id = c.id
           WHERE c.lead_id=? AND c.status='active' AND p.status='active'""",
        (int(lead_id),),
    )
    total = sum(p.get("total_hours", 0) or 0 for p in packages)
    used = sum(p.get("used_hours", 0) or 0 for p in packages)
    remaining = round(total - used, 1) if total else 0
    info["total_hours"] = total
    info["used_hours"] = used
    info["remaining_hours"] = remaining

_GEN_STEPS = {
    "starting":       (0,  "🐣 小书僮准备开工..."),
    "extracting":     (20, "📡 获取 ClassIn 字幕..."),
    "transcribing":   (50, "📝 字幕提取完成，正在分析..."),
    "generating":     (70, "🤖 AI 生成反馈中..."),
    "saving":         (90, "💾 保存反馈..."),
    "done":           (100,"🎉 完成啦！"),
    "error":          (0,  "❌ 生成失败"),
}

def _set_progress(schedule_id, status_key, extra_step=""):
    pct, label = _GEN_STEPS.get(status_key, (0, status_key))
    _gen_progress[schedule_id] = {
        "progress": pct,
        "step": label + (f" ({extra_step})" if extra_step else ""),
        "status": status_key,
    }


def _load_deepseek_key():
    """加载 DeepSeek API Key"""
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return os.environ.get("DEEPSEEK_API_KEY", "")


def _call_deepseek(system_prompt, user_prompt, temperature=0.3, max_tokens=2000):
    """调用 DeepSeek API（自动重试3次）"""
    api_key = _load_deepseek_key()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")

    data = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()

    last_error = ""
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(
                "https://api.deepseek.com/v1/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
                if not body:
                    last_error = "DeepSeek 返回空响应"
                    if attempt < 3: time.sleep(1)
                    continue
                result = json.loads(body)
                content = result["choices"][0]["message"]["content"]
                if content:
                    return content
                last_error = "DeepSeek 返回内容为空"
                if attempt < 3: time.sleep(1)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:200]
            raise RuntimeError(f"DeepSeek API HTTP {e.code}: {body}")
        except urllib.error.URLError as e:
            last_error = f"连接失败: {e.reason}"
            if attempt < 3: time.sleep(2)
        except (json.JSONDecodeError, KeyError) as e:
            last_error = str(e)
            if attempt < 3: time.sleep(1)
    raise RuntimeError(f"DeepSeek API 调用失败（已重试3次）: {last_error}")


def _generate_structured_feedback(transcript, info):
    """将转录文本发送给 DeepSeek，返回结构化反馈"""
    # 截断转录
    max_chars = 6000
    truncated = transcript[:max_chars]
    if len(transcript) > max_chars:
        truncated += "\n\n[...以下内容因长度限制已截断...]"

    system_prompt = """你是一位留学生学科辅导老师，负责根据课堂录音转录写课后反馈。

## 核心原则

1. **绝对客观，不美化学生水平** — 学生实际掌握到什么程度就写什么程度。如果学生回答错误、卡壳、混淆概念，如实描述，不要写"整体基础较好"等美化表述。
2. **英语专业术语必须准确** — 涉及学科英语术语（如 covalent bond, ionic bond, electron configuration, cation/anion 等）拼写和使用必须精确。
3. **标注时间戳** — 在描述具体表现、困难、错误时，标注转录中的时间戳 [mm:ss] 作为参考。

## 输出字段（JSON）

【公开字段 — 发给家长】
- content_covered: 本节课教学内容（2-4句话）。包含准确的学科英语术语。
- student_performance: 学生课堂表现（2-4句话）。客观描述：学生能完成什么、在哪里犯错、老师给了什么建议。标注时间戳。
- difficulties: 课堂中暴露的具体薄弱环节（2-3句话）。标注具体出错点和时间戳，没有则写"无明显难点"。
- homework_completion: 作业完成情况（1-2句话）。未涉及则如实写"本次未检查作业"。

【内部字段 — 供学管/班主任参考】
- teacher_notes: 综合评语（3-5句话）。包含：整体观察、学生反映的困扰和老师建议、AI 观察到的学习模式、给学管的参考建议。标注时间戳。
- suggestions: 后续教学建议（2-3句话）。给顾问和班主任判断是否要同步给家长的内容，包括下次课重点、需要额外关注的点。

输出纯 JSON，不要 markdown 代码块。"""

    user_prompt = f"""学生信息：
姓名：{info.get('student', '未知')}
课程：{info.get('course', '未知')}
日期：{info.get('date', '未知')}
时长：{info.get('duration', '未知')}
教师：{info.get('teacher', '未知')}
课时进度：已报名 {info.get('total_hours', 0)}h，已完成 {info.get('used_hours', 0)}h，剩余 {info.get('remaining_hours', 0)}h

课堂录音转录：
{truncated}

请输出 JSON："""

    content = _call_deepseek(system_prompt, user_prompt)

    # 清理 markdown 代码块标记
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
    if content.endswith("```"):
        content = content.rsplit("```", 1)[0]
    content = content.strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        raise RuntimeError(f"AI 返回非 JSON 格式: {content[:200]}")

    defaults = {
        "content_covered": "",
        "student_performance": "",
        "difficulties": "",
        "homework_completion": "",
        "teacher_notes": "",
        "next_focus": "",
        "suggestions": "",
    }
    for k in defaults:
        if k not in parsed or not parsed[k]:
            parsed[k] = defaults[k]

    # AI 输出 suggestions → DB 兼容 next_focus（suggestions 优先）
    if parsed.get("suggestions"):
        parsed["next_focus"] = parsed["suggestions"]

    return parsed


def _run_generation(schedule_id, classin_link, uid, name, lead_id):
    """后台线程：直接调 ClassIn API → DeepSeek → 保存"""
    try:
        _set_progress(schedule_id, "extracting")

        # Step 1: 从 ClassIn API 获取字幕（秒级）
        try:
            result = fetch_transcript(classin_link)
            transcript = result["text"] if isinstance(result, dict) else result
            modules = result.get("modules", []) if isinstance(result, dict) else []
        except Exception as e:
            _gen_progress[schedule_id] = {
                "progress": 0, "step": f"❌ 获取字幕失败: {e}",
                "status": "error", "error": str(e),
            }
            return

        transcript_len = len(transcript)
        lines = transcript.strip().split("\n")

        # 提前查询排课信息（供覆盖率检测使用）
        sched = query_one(
            """SELECT s.*, t.name as teacher_name, l.name as student_name
               FROM schedules s
               LEFT JOIN teachers t ON s.teacher_id = t.id
               LEFT JOIN leads l ON s.lead_id = l.id
               WHERE s.id=?""",
            (schedule_id,),
        )
        info = {"student": "", "teacher": "", "course": "", "date": "", "duration": "",
                "total_hours": "", "used_hours": "", "remaining_hours": ""}
        if sched:
            info["student"] = sched.get("student_name", "") or ""
            info["teacher"] = sched.get("teacher_name", "") or ""
            info["course"] = sched.get("subject", "") or ""
            info["date"] = (sched.get("start_time") or "")[:10]
            dur = sched.get("actual_duration_minutes") or sched.get("duration_minutes") or 0
            if dur:
                info["duration"] = f"{int(dur)}min"

        # 提取时间范围: 扫描所有字幕取最小和最大时间戳（按秒数，解决多模块合并顺序问题）
        def _ts_sec(t):
            p = t.split(":")
            return int(p[0])*3600 + int(p[1])*60 + (int(p[2]) if len(p)>2 else 0)
        first_ts = last_ts = None
        first_sec = last_sec = None
        for line in lines:
            m = re.search(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]", line)
            if m:
                sec = _ts_sec(m.group(1))
                if first_sec is None or sec < first_sec:
                    first_sec = sec; first_ts = m.group(1)
                if last_sec is None or sec > last_sec:
                    last_sec = sec; last_ts = m.group(1)
        time_range = f"{first_ts}~{last_ts}" if first_ts and last_ts else ""
        time_hint = f" {time_range}" if time_range else ""

        # 字幕太短时拦截（少于3行/50字无法生成任何内容）
        if transcript_len < 50 or len(lines) < 3:
            _gen_progress[schedule_id] = {
                "progress": 0, "step": f"❌ 字幕数据过短（{transcript_len}字/{len(lines)}行），"
                                       f"无法生成。请手动填写。",
                "status": "error",
                "error": "字幕数据不足",
            }
            return

        # Step 2: 课时包进度
        if sched:
            _add_package_info(lead_id, info)

        # Step 3: DeepSeek 生成结构化反馈（显示每个模块的字幕信息）
        mod_parts = []
        for m in modules:
            r = m.get("range", "")
            mod_parts.append(f"模块{m['fid'][-4:]}={m['lines']}行" + (f"[{r}]" if r else ""))
        mod_str = " | ".join(mod_parts) if mod_parts else ""
        total_info = f"共{len(lines)}段" + (f"，时间 {time_range}" if time_range else "")
        sub_info = f"{total_info}" + (f" ({mod_str})" if mod_str else "")
        _set_progress(schedule_id, "generating", extra_step=sub_info)
        try:
            feedback = _generate_structured_feedback(transcript, info)
        except Exception as e:
            _gen_progress[schedule_id] = {
                "progress": 0, "step": f"❌ AI 生成失败: {e}",
                "status": "error", "error": str(e),
            }
            return

        # Step 4: 保存到数据库
        _set_progress(schedule_id, "saving")
        _save_feedback(schedule_id, classin_link, feedback, lead_id, uid, name)

        # Step 5: 返回结果
        fb = query_one(
            """SELECT lf.*, u.display_name as creator_name
               FROM lesson_feedback lf
               LEFT JOIN users u ON lf.created_by = u.id
               WHERE lf.schedule_id=?""",
            (schedule_id,),
        )

        done_step = f"✅ 完成（{len(lines)}段{time_hint}）" + (f" ({mod_str})" if mod_str else "")
        _gen_progress[schedule_id] = {
            "progress": 100,
            "step": done_step,
            "status": "done",
            "result": {
                "feedback": fb,
                "transcript_length": transcript_len,
                "time_range": time_range,
                "line_count": len(lines),
            },
        }

        # 5 分钟后清理
        def _cleanup():
            time.sleep(300)
            _gen_progress.pop(schedule_id, None)
        threading.Thread(target=_cleanup, daemon=True).start()

    except Exception as e:
        _gen_progress[schedule_id] = {
            "progress": 0, "step": f"❌ {e}", "status": "error", "error": str(e),
        }


def _save_feedback(schedule_id, classin_link, feedback, lead_id, uid, name):
    """保存反馈到数据库"""
    existing = query_one("SELECT id FROM lesson_feedback WHERE schedule_id=?", (schedule_id,))

    if existing:
        execute(
            """UPDATE lesson_feedback SET
               classin_link=?, content_covered=?, student_performance=?,
               difficulties=?, homework_completion=?, teacher_notes=?,
               next_focus=?, ai_generated=1, updated_at=datetime('now','localtime')
               WHERE schedule_id=?""",
            (classin_link,
             feedback.get("content_covered", ""),
             feedback.get("student_performance", ""),
             feedback.get("difficulties", ""),
             feedback.get("homework_completion", ""),
             feedback.get("teacher_notes", ""),
             feedback.get("next_focus", ""),
             schedule_id),
        )
    else:
        execute_lastrowid(
            """INSERT INTO lesson_feedback
               (schedule_id, lead_id, classin_link, content_covered, student_performance,
                difficulties, homework_completion, teacher_notes, next_focus, ai_generated, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,1,?)""",
            (schedule_id, lead_id, classin_link,
             feedback.get("content_covered", ""),
             feedback.get("student_performance", ""),
             feedback.get("difficulties", ""),
             feedback.get("homework_completion", ""),
             feedback.get("teacher_notes", ""),
             feedback.get("next_focus", ""),
             uid),
        )

    add_oplog(uid, name,
              "ai_generate", "lesson_feedback", schedule_id,
              f"AI 生成课后反馈: schedule#{schedule_id}")


@post("/api/schedules/{schedule_id}/feedback/generate")
def generate_feedback(handler, token_payload, qs, body, schedule_id=None):
    """
    调用 feedback_generator 生成课后反馈（异步）
    立即返回，前端通过 progress 端点轮询进度
    """
    role = token_payload["role"]
    if not can(role, "growth:manage"):
        error_response(handler, "无权操作", 403)
        return

    classin_link = (body.get("classin_link") or "").strip()
    if not classin_link:
        error_response(handler, "请提供 ClassIn 链接")
        return

    schedule = query_one("SELECT * FROM schedules WHERE id=?", (int(schedule_id),))
    if not schedule:
        error_response(handler, "排课不存在", 404)
        return

    # ── 重复链接检测 ──
    dup = query_one(
        "SELECT id FROM lesson_feedback WHERE classin_link=? AND schedule_id=?",
        (classin_link, int(schedule_id)),
    )
    if dup:
        error_response(handler, "该 ClassIn 链接已生成过反馈，无需重复处理", 409)
        return

    # ── 已经在生成中？ ──
    existing_task = _gen_progress.get(int(schedule_id), {})
    if existing_task.get("status") in ("extracting", "transcribing", "generating", "saving"):
        error_response(handler, "该排课已有生成任务在进行中", 409)
        return

    uid = token_payload["sub"]
    name = token_payload.get("name", "")
    lead_id = schedule["lead_id"]

    _gen_progress[int(schedule_id)] = {
        "progress": 0, "step": "启动生成任务...", "status": "starting",
    }

    t = threading.Thread(
        target=_run_generation,
        args=(int(schedule_id), classin_link, uid, name, lead_id),
        daemon=True,
    )
    t.start()

    ok_response(handler, {"status": "processing", "message": "AI 生成已启动"})


@get("/api/schedules/{schedule_id}/feedback/generate/progress")
def get_generate_progress(handler, token_payload, qs, body, schedule_id=None):
    """查询 AI 生成进度"""
    sid = int(schedule_id)
    task = _gen_progress.get(sid)

    if not task:
        ok_response(handler, {"status": "idle", "progress": 0, "step": "暂无生成任务"})
        return

    ok_response(handler, {
        "status": task.get("status", "unknown"),
        "progress": task.get("progress", 0),
        "step": task.get("step", ""),
        "error": task.get("error"),
        "result": task.get("result"),
    })

# ═══════════════════════════════════════════
# 成长时间线
# ═══════════════════════════════════════════

@get("/api/growth/{lead_id}")
def get_growth_timeline(handler, token_payload, qs, body, lead_id=None):
    """获取学生完整成长时间线"""
    role = token_payload["role"]
    if not can(role, "growth:view"):
        error_response(handler, "无权访问", 403)
        return

    lead = query_one("SELECT * FROM leads WHERE id=?", (int(lead_id),))
    if not lead:
        error_response(handler, "学生不存在", 404)
        return

    # 课后反馈
    feedbacks = query(
        """SELECT lf.*, u.display_name as creator_name,
                  s.subject, s.start_time, s.tutoring_form
           FROM lesson_feedback lf
           LEFT JOIN users u ON lf.created_by = u.id
           LEFT JOIN schedules s ON lf.schedule_id = s.id
           WHERE lf.lead_id=?
           ORDER BY s.start_time DESC""",
        (int(lead_id),),
    )

    # 排课（含是否已有反馈）
    schedules = query(
        """SELECT s.*, t.name as teacher_name,
                  (SELECT id FROM lesson_feedback WHERE schedule_id=s.id) as feedback_id
           FROM schedules s
           LEFT JOIN teachers t ON s.teacher_id = t.id
           WHERE s.lead_id=?
           ORDER BY s.start_time DESC""",
        (int(lead_id),),
    )

    # 考试成绩
    exams = query(
        """SELECT er.*, u.display_name as creator_name
           FROM exam_results er
           LEFT JOIN users u ON er.created_by = u.id
           WHERE er.lead_id=?
           ORDER BY er.exam_date DESC""",
        (int(lead_id),),
    )

    # 录取结果
    admissions = query(
        """SELECT ar.*, u.display_name as creator_name
           FROM admission_results ar
           LEFT JOIN users u ON ar.created_by = u.id
           WHERE ar.lead_id=?
           ORDER BY ar.application_date DESC""",
        (int(lead_id),),
    )

    # 合同信息
    contracts = query(
        "SELECT * FROM contracts WHERE lead_id=? ORDER BY created_at DESC",
        (int(lead_id),),
    )

    # 课时包进度
    pkg_info = {"total_hours": 0, "used_hours": 0, "remaining_hours": 0}
    _add_package_info(int(lead_id), pkg_info)

    ok_response(handler, {
        "lead": lead,
        "contracts": contracts,
        "feedbacks": feedbacks,
        "schedules": schedules,
        "exams": exams,
        "admissions": admissions,
        "total_feedbacks": len(feedbacks),
        "total_schedules": len(schedules),
        "total_exams": len(exams),
        "package_info": pkg_info,
    })


# ═══════════════════════════════════════════
# 考试成绩
# ═══════════════════════════════════════════

@get("/api/growth/{lead_id}/exams")
def list_exams(handler, token_payload, qs, body, lead_id=None):
    rows = query(
        "SELECT * FROM exam_results WHERE lead_id=? ORDER BY exam_date DESC",
        (int(lead_id),),
    )
    ok_response(handler, rows)


@post("/api/growth/{lead_id}/exams")
def create_exam(handler, token_payload, qs, body, lead_id=None):
    role = token_payload["role"]
    if not can(role, "exam:manage"):
        error_response(handler, "无权操作", 403)
        return

    exam_date = (body.get("exam_date") or "").strip()
    exam_type = (body.get("exam_type") or "").strip()
    if not exam_date or not exam_type:
        error_response(handler, "考试日期和类型不能为空")
        return

    eid = execute_lastrowid(
        """INSERT INTO exam_results
           (lead_id, exam_date, exam_type, subject, score, total_score, notes, created_by)
           VALUES (?,?,?,?,?,?,?,?)""",
        (int(lead_id), exam_date, exam_type,
         (body.get("subject") or "").strip(),
         body.get("score"), body.get("total_score"),
         (body.get("notes") or "").strip(),
         token_payload["sub"]),
    )
    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "create", "exam_result", eid, f"录入考试成绩: {exam_type} {body.get('score','')}")
    row = query_one("SELECT * FROM exam_results WHERE id=?", (eid,))
    ok_response(handler, row, 201)


@put("/api/growth/{lead_id}/exams/{exam_id}")
def update_exam(handler, token_payload, qs, body, lead_id=None, exam_id=None):
    role = token_payload["role"]
    if not can(role, "exam:manage"):
        error_response(handler, "无权操作", 403)
        return

    fields = {}
    for k in ("exam_date", "exam_type", "subject", "score", "total_score", "notes"):
        if k in body:
            fields[k] = body[k]
    if not fields:
        error_response(handler, "没有要更新的字段")
        return

    sets = ", ".join(f"{k}=?" for k in fields)
    params = list(fields.values()) + [int(exam_id), int(lead_id)]
    execute(f"UPDATE exam_results SET {sets} WHERE id=? AND lead_id=?", params)

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "update", "exam_result", int(exam_id), "更新考试成绩")
    row = query_one("SELECT * FROM exam_results WHERE id=?", (int(exam_id),))
    ok_response(handler, row)


@delete("/api/growth/{lead_id}/exams/{exam_id}")
def delete_exam(handler, token_payload, qs, body, lead_id=None, exam_id=None):
    role = token_payload["role"]
    if not can(role, "exam:manage"):
        error_response(handler, "无权操作", 403)
        return

    execute("DELETE FROM exam_results WHERE id=? AND lead_id=?", (int(exam_id), int(lead_id)))
    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "delete", "exam_result", int(exam_id), "删除考试成绩")
    ok_response(handler, {"deleted": True})


# ═══════════════════════════════════════════
# 录取结果
# ═══════════════════════════════════════════

@get("/api/growth/{lead_id}/admissions")
def list_admissions(handler, token_payload, qs, body, lead_id=None):
    rows = query(
        "SELECT * FROM admission_results WHERE lead_id=? ORDER BY application_date DESC",
        (int(lead_id),),
    )
    ok_response(handler, rows)


@post("/api/growth/{lead_id}/admissions")
def create_admission(handler, token_payload, qs, body, lead_id=None):
    role = token_payload["role"]
    if not can(role, "admission:manage"):
        error_response(handler, "无权操作", 403)
        return

    aid = execute_lastrowid(
        """INSERT INTO admission_results
           (lead_id, target_school, target_major, application_date,
            admission_status, admitted_school, admitted_major,
            final_score, decision_date, notes, created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (int(lead_id),
         (body.get("target_school") or "").strip(),
         (body.get("target_major") or "").strip(),
         (body.get("application_date") or "").strip(),
         (body.get("admission_status") or "pending"),
         (body.get("admitted_school") or "").strip(),
         (body.get("admitted_major") or "").strip(),
         (body.get("final_score") or "").strip(),
         (body.get("decision_date") or "").strip(),
         (body.get("notes") or "").strip(),
         token_payload["sub"]),
    )
    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "create", "admission_result", aid, "创建录取结果")
    row = query_one("SELECT * FROM admission_results WHERE id=?", (aid,))
    ok_response(handler, row, 201)


@put("/api/growth/{lead_id}/admissions/{admission_id}")
def update_admission(handler, token_payload, qs, body, lead_id=None, admission_id=None):
    role = token_payload["role"]
    if not can(role, "admission:manage"):
        error_response(handler, "无权操作", 403)
        return

    fields = {}
    for k in ("target_school", "target_major", "application_date", "admission_status",
              "admitted_school", "admitted_major", "final_score", "decision_date", "notes"):
        if k in body:
            fields[k] = body[k]
    if not fields:
        error_response(handler, "没有要更新的字段")
        return

    sets = ", ".join(f"{k}=?" for k in fields)
    params = list(fields.values()) + [int(admission_id), int(lead_id)]
    execute(f"UPDATE admission_results SET {sets}, updated_at=datetime('now','localtime') WHERE id=? AND lead_id=?", params)

    add_oplog(token_payload["sub"], token_payload.get("name", ""),
              "update", "admission_result", int(admission_id), "更新录取结果")
    row = query_one("SELECT * FROM admission_results WHERE id=?", (int(admission_id),))
    ok_response(handler, row)

# ═══════════════════════════════════════════
# 整体学情报告（一键生成）v2 — 系统化深度分析
# ═══════════════════════════════════════════

_growth_report_progress = {}

@post("/api/growth/{lead_id}/overall-report")
def generate_overall_report(handler, token_payload, qs, body, lead_id=None):
    """一键生成学生整体学情报告 v2"""
    role = token_payload["role"]
    if not can(role, "growth:view"):
        error_response(handler, "无权访问", 403)
        return

    lid = int(lead_id)
    lead = query_one("SELECT * FROM leads WHERE id=?", (lid,))
    if not lead:
        error_response(handler, "学生不存在", 404)
        return

    # ═══ v2 数据收集 ═══
    feedbacks = query(
        "SELECT * FROM lesson_feedback WHERE lead_id=? ORDER BY created_at", (lid,))
    consulting_reports = query(
        "SELECT * FROM consulting_reports WHERE lead_id=? ORDER BY created_at DESC LIMIT 1", (lid,))
    followups = query(
        """SELECT f.*, u.display_name as creator_name
           FROM followups f LEFT JOIN users u ON f.created_by = u.id
           WHERE f.lead_id=? ORDER BY f.created_at""", (lid,))
    exams = query(
        "SELECT * FROM exam_results WHERE lead_id=? ORDER BY exam_date", (lid,))
    # v2新增：排课（含老师名）、课时包
    schedules = query("""SELECT s.*, t.name as teacher_name
       FROM schedules s LEFT JOIN teachers t ON s.teacher_id = t.id
       WHERE s.lead_id=? ORDER BY s.start_time DESC""", (lid,))
    contracts = query("""SELECT c.*,
       (SELECT COALESCE(SUM(p.total_hours),0) FROM packages p WHERE p.contract_id=c.id AND p.status='active') as total_hours,
       (SELECT COALESCE(SUM(p.used_hours),0) FROM packages p WHERE p.contract_id=c.id AND p.status='active') as used_hours
       FROM contracts c WHERE c.lead_id=? AND c.status='active' ORDER BY c.created_at DESC LIMIT 1""", (lid,))

    _growth_report_progress[lid] = {"progress": 10, "step": "正在分析学生数据...", "status": "generating"}

    import json as _json, threading as _threading
    def _run(lid, lead, feedbacks, consulting_reports, followups, exams, schedules, contracts, creator_id):
        try:
            _growth_report_progress[lid] = {"progress": 20, "step": "正在逐学科分析...", "status": "generating"}

            # ── 按学科分组反馈 ──
            fb_by_subject = {}
            for fb in feedbacks:
                sched = next((s for s in schedules if s["id"] == fb.get("schedule_id")), None)
                subj = (sched.get("subject") or "未分类").strip()
                teacher = sched.get("teacher_name") or "未知老师"
                if subj not in fb_by_subject:
                    fb_by_subject[subj] = {"teacher": teacher, "feedbacks": []}
                fb_by_subject[subj]["feedbacks"].append(fb)

            # ── 排课统计 ──
            total_scheduled = len(schedules)
            completed_schedules = sum(1 for s in schedules if s["status"] == "completed")
            pending_schedules = sum(1 for s in schedules if s["status"] == "pending")
            sched_by_month = {}
            for s in schedules:
                mk = (s.get("start_time") or "")[:7]
                if mk:
                    sched_by_month[mk] = sched_by_month.get(mk, 0) + 1
            sched_by_subject = {}
            for s in schedules:
                subj = (s.get("subject") or "未分类").strip()
                if subj not in sched_by_subject:
                    sched_by_subject[subj] = {"total": 0, "completed": 0}
                sched_by_subject[subj]["total"] += 1
                if s["status"] == "completed":
                    sched_by_subject[subj]["completed"] += 1

            # ── 课时包 ──
            total_hours = sum((c.get("total_hours",0) or 0) for c in contracts)
            used_hours = sum((c.get("used_hours",0) or 0) for c in contracts)
            rem_hours = round(total_hours - used_hours, 1) if total_hours else 0
            cons_rate = round(used_hours / (total_hours or 1) * 100, 1)

            # ── 按学科的结构化反馈 ──
            subject_detailed = []
            for subj, data in fb_by_subject.items():
                lines = []
                for fb in data["feedbacks"][-15:]:
                    date = (fb.get("created_at") or "")[:10]
                    parts = []
                    if fb.get("content_covered"):
                        parts.append("内容:" + fb["content_covered"][:120])
                    if fb.get("student_performance"):
                        parts.append("表现:" + fb["student_performance"][:80])
                    if fb.get("difficulties"):
                        parts.append("困难:" + fb["difficulties"][:80])
                    if parts:
                        lines.append("[" + date + "] " + " | ".join(parts))
                fb_text = "\n".join(lines) if lines else ""
                subject_detailed.append({"subject": subj, "teacher": data["teacher"], "feedbacks_text": fb_text})

            # ── 跟进摘要 ──
            fu_summary = "\n".join(["[%s] rank=%s %s" % ((f.get("created_at") or "")[:10], f.get("followup_rank","-"), (f.get("content") or "")[:100]) for f in followups[-15:]]) if followups else ""

            # ── 学业风险报告 ──
            cr_summary = ""
            for cr in consulting_reports:
                rj = cr.get("report_json", "")
                if rj:
                    try:
                        rd = _json.loads(rj)
                        cr_summary += "· %s: %s\n" % (rd.get("report_title","学业风险规划报告"), (rd.get("overall_assessment","") or "")[:200])
                    except Exception:
                        pass

            # ── 排课频次趋势 ──
            month_keys = sorted(sched_by_month.keys())
            freq_trend = "无排课记录"
            if month_keys:
                parts = ["%s:%s节" % (mk, sched_by_month[mk]) for mk in month_keys[-6:]]
                freq_trend = " → ".join(parts)

            system_prompt = """你是一位资深的留学学业规划顾问。根据学生全部数据，生成一份「阶段性学情综合报告」。

报告要求系统化、有深度、数据驱动。面向机构内部顾问和家长双方，既要有专业分析，也要有可执行建议。

## 输出结构

{
  "report_title": "阶段性学情综合报告",
  "student_info": {"name":"","grade":"","country":"","total_classes":0,"completed_classes":0,"total_hours":0,"used_hours":0,"remaining_hours":0,"consumption_rate":0},
  "subject_analysis": [
    {"subject":"学科名","teacher":"老师名","sessions":0,"current_progress":"","performance":"","weak_points":"","trend":"稳定上升/波动/下滑","suggestion":""}
  ],
  "learning_trends": {"class_frequency":"上课频次分析","monthly_schedule_count":"各月排课数","hour_consumption_note":"课时消耗分析"},
  "risk_warnings": [{"type":"课时不足|上课频次下降|长期未跟进|成绩下滑|其他","detail":"","severity":"high/medium/low","action_required":""}],
  "overall_assessment": "综合评估（200-300字）",
  "consultant_actions": [{"action":"具体行动","priority":"high/medium","target":"行动对象","note":"执行要点"}],
  "parent_communication": "家长沟通建议",
  "recommendations": ["后续学习建议3-5条"]
}

## 原则
1. subject_analysis是核心——每个学科单独分析，基于该学科的实际课后反馈
2. risk_warnings必须基于真实数据，没有则不输出
3. consultant_actions要可执行，具体到人和事
4. 没有数据的维度不输出
5. 措辞客观，用数据说话"""

            user_parts = ["学生: " + (lead.get("name","?") or "?")]
            if lead.get("grade"): user_parts[0] += " 年级: " + lead["grade"]
            if lead.get("country"): user_parts[0] += " 国家: " + lead["country"]
            if lead.get("remark"):
                user_parts.append("[学生备注]\n" + ((lead["remark"] or "")[:500]))

            # 排课
            sched_text = "总排课%d节 | 已完成%d节 | 待上课%d节" % (total_scheduled, completed_schedules, pending_schedules)
            sched_text += "\n各月趋势: " + freq_trend
            if sched_by_subject:
                sched_text += "\n按学科:"
                for subj, data in sorted(sched_by_subject.items()):
                    sched_text += " %s:%d节(%d完成)" % (subj, data["total"], data["completed"])
            user_parts.append("[排课数据]\n" + sched_text)

            if contracts:
                pkg = "总课时%sh | 已用%sh | 剩余%sh | 消耗率%s%%" % (total_hours, used_hours, rem_hours, cons_rate)
                user_parts.append("[课时使用]\n" + pkg)

            if subject_detailed:
                st = ["学科: " + sd["subject"] + " 老师: " + sd["teacher"] + "\n" + sd["feedbacks_text"] for sd in subject_detailed]
                user_parts.append("[课后反馈（按学科）]\n" + "\n---\n".join(st))

            if cr_summary:
                user_parts.append("[学业风险报告]\n" + cr_summary[:1500])
            if fu_summary:
                user_parts.append("[跟进记录]\n" + fu_summary[:1500])
            if exams:
                el = [{"科目":e.get("subject"),"分数":e.get("score"),"日期":e.get("exam_date")} for e in exams]
                user_parts.append("[考试成绩]\n" + _json.dumps(el, ensure_ascii=False)[:1000])

            user_prompt = "\n\n".join(user_parts)
            _growth_report_progress[lid] = {"progress": 50, "step": "AI 正在逐学科分析...", "status": "generating"}
            result = _call_deepseek(system_prompt, user_prompt, temperature=0.3, max_tokens=4000)
            content_raw = result.strip() if isinstance(result, str) else str(result)
            if not content_raw:
                err_msg = "AI 返回内容为空，请稍后重试"
                _growth_report_progress[lid] = {"progress": 0, "step": "❌ " + err_msg, "status": "error"}
                return
            content_raw = re.sub(r"^```(?:json)?\s*", "", content_raw)
            content_raw = re.sub(r"\s*```$", "", content_raw)
            parsed = _json.loads(content_raw)
            report_json = _json.dumps(parsed, ensure_ascii=False)
            existing = query_one("SELECT id FROM consulting_reports WHERE lead_id=? AND report_type='growth_overall'", (lid,))
            if existing:
                execute("UPDATE consulting_reports SET report_json=?, updated_at=datetime('now','localtime') WHERE id=?", (report_json, existing["id"]))
            else:
                execute("INSERT INTO consulting_reports (lead_id, target_country, target_school, target_major, report_type, report_json, status, created_by, created_at, updated_at) VALUES (?,'','','','growth_overall',?,'completed',?,datetime('now','localtime'),datetime('now','localtime'))", (lid, report_json, creator_id))
            _growth_report_progress[lid] = {"progress": 100, "step": "✅ 报告生成完成！", "status": "done", "result": parsed}
        except Exception as e:
            _growth_report_progress[lid] = {"progress": 0, "step": "❌ 生成失败: " + str(e), "status": "error"}

    _growth_report_progress[lid] = {"progress": 5, "step": "正在收集数据...", "status": "generating"}
    creator_id = token_payload["sub"]
    t = _threading.Thread(target=_run, args=(lid, lead, feedbacks, consulting_reports, followups, exams, schedules, contracts, creator_id), daemon=True)
    t.start()

    ok_response(handler, {"status": "generating", "progress": 5, "step": "正在收集数据..."})

@get("/api/growth/{lead_id}/overall-report/progress")
def get_overall_report_progress(handler, token_payload, qs, body, lead_id=None):
    lid = int(lead_id)
    task = _growth_report_progress.get(lid, {})
    if not task:
        ok_response(handler, {"status": "idle", "progress": 0})
        return
    ok_response(handler, task)

@get("/api/growth/{lead_id}/overall-report")
def get_overall_report(handler, token_payload, qs, body, lead_id=None):
    lid = int(lead_id)
    # 从 DB 到读取
    row = query_one("SELECT * FROM consulting_reports WHERE lead_id=? AND report_type='growth_overall' ORDER BY created_at DESC LIMIT 1", (lid,))
    if row and row.get("report_json"):
        try:
            data = json.loads(row["report_json"])
            data["_report_id"] = row["id"]
            ok_response(handler, data)
            return
        except Exception as e:
            logger.error('Failed to parse overall report JSON from DB', extra={'error': str(e), 'lead_id': lid})
    ok_response(handler, {"status": "not_found"})

@put("/api/growth/{lead_id}/overall-report")
def save_overall_report(handler, token_payload, qs, body, lead_id=None):
    """保存编辑后的报告"""
    lid = int(lead_id)
    row = query_one("SELECT id FROM consulting_reports WHERE lead_id=? AND report_type='growth_overall'", (lid,))
    if not row:
        error_response(handler, "报告不存在", 404)
        return
    report_json = json.dumps(body.get("data", body), ensure_ascii=False)
    execute("UPDATE consulting_reports SET report_json=?, updated_at=datetime('now','localtime') WHERE id=?", (report_json, row["id"]))
    ok_response(handler, {"message": "已保存"})


@get("/api/growth/{lead_id}/overall-report/download")
def download_overall_report(handler, token_payload, qs, body, lead_id=None):
    """下载 PDF/Word"""
    from export import generate_pdf, generate_docx
    lid = int(lead_id)
    fmt = qs.get("format", ["pdf"])[0]
    row = query_one("SELECT * FROM consulting_reports WHERE lead_id=? AND report_type='growth_overall' ORDER BY created_at DESC LIMIT 1", (lid,))
    if not row or not row.get("report_json"):
        error_response(handler, "报告不存在", 404)
        return
    lead = query_one("SELECT * FROM leads WHERE id=?", (lid,))
    report_data = json.loads(row["report_json"])
    lead_name = lead["name"] if lead else "student"
    if fmt == "docx":
        content = generate_docx(row, lead, "growth_overall")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        handler.send_header("Content-Disposition", f'attachment; filename="report.docx"')
        handler.send_header("Content-Length", str(len(content)))
        handler.end_headers()
        handler.wfile.write(content)
    else:
        content = generate_pdf(row, lead, "growth_overall")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/pdf")
        handler.send_header("Content-Disposition", f'attachment; filename="report.pdf"')
        handler.send_header("Content-Length", str(len(content)))
        handler.end_headers()
        handler.wfile.write(content)


@delete("/api/growth/{lead_id}/overall-report")
def delete_overall_report(handler, token_payload, qs, body, lead_id=None):
    _growth_report_progress.pop(int(lead_id), None)
    ok_response(handler, {"message": "已清除"})
