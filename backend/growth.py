"""
成长档案 API — 课后反馈、考试成绩、录取结果、成长时间线
"""
import json
import os
import subprocess
import threading
import time
from router import get, post, put, delete
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid
from permissions import can, scope_where


# ═══════════════════════════════════════════
# 课后反馈
# ═══════════════════════════════════════════

@get("/api/schedules/{schedule_id}/feedback")
def get_feedback(handler, token_payload, qs, body, schedule_id=None):
    """查某节课的课后反馈"""
    row = query_one(
        """SELECT lf.*, u.display_name as creator_name
           FROM lesson_feedback lf
           LEFT JOIN users u ON lf.created_by = u.id
           WHERE lf.schedule_id=?""",
        (int(schedule_id),),
    )
    ok_response(handler, row or {})


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


from permissions import can, scope_where


# ═══════════════════════════════════════════
# AI 生成进度跟踪（内存）
# ═══════════════════════════════════════════
_gen_progress = {}  # schedule_id → {progress, step, status, result, error}

_GEN_STEPS = {
    "starting":       (0,  "🐣 小书僮准备开工..."),
    "pipeline":       (10, "🔍 打开 ClassIn 提取 AI 字幕..."),
    "transcribed":    (55, "📝 AI 字幕提取完成..."),
    "llm":            (65, "🤖 小脑瓜思考ing..."),
    "generating":     (80, "✍️ 整理报告..."),
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

def _run_generation(schedule_id, classin_link, generator_path, uid, name, lead_id):
    """后台线程：执行 feedback_generator 并更新进度"""
    try:
        _set_progress(schedule_id, "pipeline")

        process = subprocess.Popen(
            ["python3", generator_path, classin_link],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        # 读取 stderr 实时解析进度
        last_line = ""
        stderr_lines = []
        for line in iter(process.stderr.readline, ""):
            stderr_lines.append(line)
            line = line.strip()
            if not line:
                continue
            last_line = line
            if "Step 1/3" in line:
                _set_progress(schedule_id, "pipeline")
            elif "转录" in line and "字" in line:
                _set_progress(schedule_id, "transcribed", extra_step=line.split(":")[-1].strip())
            elif "pipeline 已生成反馈" in line:
                _set_progress(schedule_id, "llm")
            elif "Step 2/3" in line:
                _set_progress(schedule_id, "llm")
            elif "DeepSeek" in line or "结构化" in line:
                _set_progress(schedule_id, "generating")
            elif "Step 3/3" in line:
                _set_progress(schedule_id, "saving")

        stdout, stderr = process.communicate()

        if process.returncode != 0:
            err_msg = stderr.strip()[-200:] if stderr.strip() else last_line[-200:]
            _gen_progress[schedule_id] = {
                "progress": 0, "step": f"❌ {err_msg}", "status": "error", "error": err_msg,
            }
            return

        # 解析 JSON 输出（最后一行）
        lines = stdout.strip().split("\n")
        json_line = None
        for line in reversed(lines):
            try:
                json.loads(line)
                json_line = line
                break
            except json.JSONDecodeError:
                continue

        if not json_line:
            _gen_progress[schedule_id] = {
                "progress": 0, "step": "❌ AI 返回格式异常", "status": "error", "error": "返回格式异常",
            }
            return

        data = json.loads(json_line)

        if "error" in data:
            _gen_progress[schedule_id] = {
                "progress": 0, "step": f"❌ {data['error']}", "status": "error", "error": data["error"],
            }
            return

        feedback = data.get("feedback", {})

        # 保存到数据库
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

        # 返回完整反馈
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
                "info": data.get("info", {}),
                "transcript_length": data.get("transcript_length", 0),
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
    if existing_task.get("status") in ("pipeline", "downloading", "transcribing", "llm", "generating", "saving"):
        error_response(handler, "该排课已有生成任务在进行中", 409)
        return

    # ── 启动后台生成 ──
    generator_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feedback_generator.py")
    if not os.path.exists(generator_path):
        error_response(handler, "feedback_generator.py 未找到", 500)
        return

    uid = token_payload["sub"]
    name = token_payload.get("name", "")
    lead_id = schedule["lead_id"]

    _gen_progress[int(schedule_id)] = {
        "progress": 0, "step": "启动生成任务...", "status": "starting",
    }

    t = threading.Thread(
        target=_run_generation,
        args=(int(schedule_id), classin_link, generator_path, uid, name, lead_id),
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
