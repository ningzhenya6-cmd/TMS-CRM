"""
成长档案 API — 课后反馈、考试成绩、录取结果、成长时间线
"""
import json
import os
import threading
import time
import urllib.request
import urllib.error
from router import get, post, put, delete
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid

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
    """调用 DeepSeek API"""
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

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        raise RuntimeError(f"DeepSeek API HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"DeepSeek API 请求失败: {e.reason}")
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"DeepSeek API 返回格式异常: {e}")


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
            transcript = fetch_transcript(classin_link)
        except Exception as e:
            _gen_progress[schedule_id] = {
                "progress": 0, "step": f"❌ 获取字幕失败: {e}",
                "status": "error", "error": str(e),
            }
            return

        transcript_len = len(transcript)
        _set_progress(schedule_id, "transcribing", extra_step=f"{transcript_len}字")

        # Step 2: 从链接中提取展示信息 + 课时包进度
        info = {"student": "", "teacher": "", "course": "", "date": "", "duration": "",
                "total_hours": "", "used_hours": "", "remaining_hours": ""}
        # 排课信息
        sched = query_one(
            """SELECT s.*, t.name as teacher_name, l.name as student_name
               FROM schedules s
               LEFT JOIN teachers t ON s.teacher_id = t.id
               LEFT JOIN leads l ON s.lead_id = l.id
               WHERE s.id=?""",
            (schedule_id,),
        )
        if sched:
            info["student"] = sched.get("student_name", "") or ""
            info["teacher"] = sched.get("teacher_name", "") or ""
            info["course"] = sched.get("subject", "") or ""
            info["date"] = (sched.get("start_time") or "")[:10]
            dur = sched.get("actual_duration_minutes") or sched.get("duration_minutes") or 0
            if dur:
                info["duration"] = f"{int(dur)}min"
            # 课时包进度
            _add_package_info(lead_id, info)

        # Step 3: DeepSeek 生成结构化反馈
        _set_progress(schedule_id, "generating")
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

        _gen_progress[schedule_id] = {
            "progress": 100,
            "step": "✅ AI 反馈生成完成！",
            "status": "done",
            "result": {
                "feedback": fb,
                "transcript_length": transcript_len,
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
