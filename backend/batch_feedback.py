"""
批量反馈 — 一次性粘贴多个 ClassIn 链接，自动创建排课 + AI 生成反馈
每个链接在后台线程中串行处理，前端轮询进度
"""
import datetime
import threading
from router import get, post
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid
from permissions import can
from classin_api import fetch_transcript, parse_classin_url
from growth import _generate_structured_feedback, _add_package_info

# 批次进度存储: batch_id → {total, completed, current_step, results: [...]}
_batch_progress = {}
_batch_lock = threading.Lock()


def _auto_create_schedule(lead_id, link, transcript_result, uid):
    """从 ClassIn 提取信息，自动创建一条排课记录"""
    # 尝试从 ClassIn URL 提取课程名称和日期
    course_name = "ClassIn 课程"
    course_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    modules = transcript_result.get("modules", []) if isinstance(transcript_result, dict) else []
    if modules:
        # 取第一个模块的名称
        first_module = modules[0]
        if isinstance(first_module, dict):
            course_name = first_module.get("module_name", first_module.get("title", "ClassIn 课程"))

    # 尝试从 URL 解析课程 key
    try:
        parsed = parse_classin_url(link)
        if parsed:
            course_key = parsed[0] or ""
            if course_key:
                course_name = f"ClassIn-{course_key[:12]}"
    except Exception:
        pass

    end_time = (datetime.datetime.strptime(course_date, "%Y-%m-%d %H:%M") + datetime.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")

    sid = execute_lastrowid(
        """INSERT INTO schedules (lead_id, subject, start_time, end_time, status, created_by, remark)
           VALUES (?,?,?,?,?,?,?)""",
        (
            int(lead_id),
            course_name,
            course_date,
            end_time,
            "completed",
            uid,
            f"批量反馈自动创建 - {link[:60]}",
        ),
    )
    return sid


def _save_batch_feedback(schedule_id, lead_id, classin_link, parsed_feedback, uid):
    """保存反馈到 lesson_feedback 表"""
    existing = query_one("SELECT id FROM lesson_feedback WHERE schedule_id=?", (schedule_id,))
    if existing:
        execute(
            """UPDATE lesson_feedback SET
               classin_link=?, content_covered=?, student_performance=?,
               difficulties=?, homework_completion=?, teacher_notes=?,
               next_focus=?, ai_generated=1, updated_at=datetime('now','localtime')
               WHERE schedule_id=?""",
            (
                classin_link,
                parsed_feedback.get("content_covered", ""),
                parsed_feedback.get("student_performance", ""),
                parsed_feedback.get("difficulties", ""),
                parsed_feedback.get("homework_completion", ""),
                parsed_feedback.get("teacher_notes", ""),
                parsed_feedback.get("next_focus", ""),
                schedule_id,
            ),
        )
        return existing["id"]
    else:
        fid = execute_lastrowid(
            """INSERT INTO lesson_feedback
               (schedule_id, lead_id, classin_link, content_covered, student_performance,
                difficulties, homework_completion, teacher_notes, next_focus,
                ai_generated, created_by)
               VALUES (?,?,?,?,?,?,?,?,?,1,?)""",
            (
                schedule_id,
                int(lead_id),
                classin_link,
                parsed_feedback.get("content_covered", ""),
                parsed_feedback.get("student_performance", ""),
                parsed_feedback.get("difficulties", ""),
                parsed_feedback.get("homework_completion", ""),
                parsed_feedback.get("teacher_notes", ""),
                parsed_feedback.get("next_focus", ""),
                uid,
            ),
        )
        return fid


def _run_batch(batch_id, lead_id, links, uid, uname):
    """后台线程：依次处理每个链接"""
    total = len(links)
    results = [None] * total

    with _batch_lock:
        _batch_progress[batch_id] = {
            "total": total,
            "completed": 0,
            "current_step": f"准备处理 {total} 个链接...",
            "results": [],
        }

    lead = query_one("SELECT id, name FROM leads WHERE id=?", (int(lead_id),))
    student_name = lead["name"] if lead else "未知学生"

    for i, link in enumerate(links):
        link = link.strip()
        if not link:
            continue

        # 更新进度
        with _batch_lock:
            _batch_progress[batch_id]["current_step"] = f"正在生成第 {i+1}/{total} 节课..."
            _batch_progress[batch_id].setdefault("current_idx", i)

        result_entry = {"idx": i, "link": link[:80], "status": "processing"}
        results[i] = result_entry

        try:
            # Step 1: 提取字幕
            _update_batch_progress(batch_id, f"📡 [{i+1}/{total}] 获取 ClassIn 字幕...", i)
            transcript_result = fetch_transcript(link)
            transcript = transcript_result["text"] if isinstance(transcript_result, dict) else transcript_result

            if not transcript or len(transcript.strip()) < 50:
                raise RuntimeError("字幕内容过短，无法生成反馈")

            # Step 2: 自动创建排课
            _update_batch_progress(batch_id, f"📋 [{i+1}/{total}] 创建排课记录...", i)
            schedule_id = _auto_create_schedule(lead_id, link, transcript_result, uid)

            # Step 3: AI 生成反馈
            _update_batch_progress(batch_id, f"🤖 [{i+1}/{total}] AI 生成反馈中...", i)
            info = {
                "student": student_name,
                "course": "ClassIn 课程",
                "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "duration": "60 分钟",
                "teacher": "待补充",
            }
            try:
                _add_package_info(lead_id, info)
            except Exception:
                info["total_hours"] = 0
                info["used_hours"] = 0
                info["remaining_hours"] = 0

            parsed = _generate_structured_feedback(transcript, info)

            # Step 4: 保存反馈
            _update_batch_progress(batch_id, f"💾 [{i+1}/{total}] 保存反馈...", i)
            feedback_id = _save_batch_feedback(schedule_id, lead_id, link, parsed, uid)

            result_entry["status"] = "done"
            result_entry["schedule_id"] = schedule_id
            result_entry["feedback_id"] = feedback_id
            result_entry["progress"] = 100

        except Exception as e:
            result_entry["status"] = "error"
            result_entry["error"] = str(e)
            result_entry["progress"] = 0

        with _batch_lock:
            _batch_progress[batch_id]["completed"] = i + 1

    # 完成
    with _batch_lock:
        done = sum(1 for r in results if r and r.get("status") == "done")
        _batch_progress[batch_id]["current_step"] = f"🎉 完成！成功 {done}/{total}"
        _batch_progress[batch_id]["results"] = results
        _batch_progress[batch_id]["status"] = "done"

    add_oplog(uid, uname, "batch_feedback", "lead", lead_id,
              f"批量生成课后反馈: {done}/{total} 成功")


def _update_batch_progress(batch_id, step, idx):
    with _batch_lock:
        if batch_id in _batch_progress:
            _batch_progress[batch_id]["current_step"] = step
            _batch_progress[batch_id]["current_idx"] = idx


@post("/api/batch-feedback/generate")
def start_batch_generate(handler, token_payload, qs, body):
    """启动批量反馈生成"""
    if not can(token_payload["role"], "growth:manage"):
        error_response(handler, "无权操作", 403)
        return

    lead_id = body.get("lead_id")
    links = body.get("links", [])

    if not lead_id:
        error_response(handler, "请选择学生")
        return
    if not links or not isinstance(links, list) or len(links) == 0:
        error_response(handler, "请提供至少一个 ClassIn 链接")
        return

    # 检查是否有正在进行的批次
    lead = query_one("SELECT id FROM leads WHERE id=?", (int(lead_id),))
    if not lead:
        error_response(handler, "学生不存在")
        return

    batch_id = f"batch_{lead_id}_{datetime.datetime.now().strftime('%H%M%S')}"
    uid = token_payload["sub"]
    uname = token_payload.get("name", "")

    thread = threading.Thread(
        target=_run_batch,
        args=(batch_id, lead_id, links, uid, uname),
        daemon=True,
    )
    thread.start()

    ok_response(handler, {"batch_id": batch_id, "total": len(links)})


@get("/api/batch-feedback/progress")
def get_batch_progress(handler, token_payload, qs, body):
    """查询批量反馈生成进度"""
    batch_id = qs.get("batch_id", [None])[0]
    if not batch_id:
        error_response(handler, "缺少 batch_id")
        return

    with _batch_lock:
        data = _batch_progress.get(batch_id)

    if not data:
        error_response(handler, "批次不存在或已过期", 404)
        return

    ok_response(handler, data)
