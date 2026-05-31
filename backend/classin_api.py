"""
ClassIn API 直调 — 获取课堂回放字幕，无需浏览器

用法:
    from classin_api import fetch_transcript
    text = fetch_transcript("https://live.eeo.cn/webcast.php?courseKey=xxx&lessonid=yyy")
    text = fetch_transcript("https://live.eeo.cn/pc.html?lessonKey=xxx")
"""
import json
import os
import re
import urllib.request
import urllib.error

# ── API 配置 ──
_RICH_SUMMARY_URL = "https://dynamic.eeo.cn/course-ai-assistant/app/share/richVideoSummary"
_LESSON_INFO_URL = "https://dynamic.eeo.cn/saasajax/webcast.ajax.php?action=getLessonClassInfo"


def _resolve_lesson_key(lesson_key, timeout=10):
    """通过 ClassIn 内部 API 将 lessonKey（十六进制）解析为 courseKey 和 numeric lessonId

    Returns:
        dict: {"courseKey": str, "lessonId": str, "lessonStatus": int}
    """
    payload = f"lessonKey={lesson_key}".encode()
    req = urllib.request.Request(
        _LESSON_INFO_URL,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://live.eeo.cn",
            "Referer": f"https://live.eeo.cn/pc.html?lessonKey={lesson_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        raise RuntimeError(f"ClassIn LessonInfo API HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"ClassIn LessonInfo API 请求失败: {e.reason}")
    except json.JSONDecodeError:
        raise RuntimeError("ClassIn LessonInfo API 返回非 JSON 格式")

    errno = data.get("error_info", {}).get("errno", 0)
    if errno != 1:
        err_msg = data.get("error_info", {}).get("error", f"errno={errno}")
        raise RuntimeError(f"ClassIn LessonInfo API 返回错误: {err_msg}")

    info = data.get("data", {})
    lesson_id = info.get("lessonId")
    course_key = info.get("courseKey")
    lesson_status = info.get("lessonStatus")

    if not lesson_id or not course_key:
        raise RuntimeError(f"ClassIn LessonInfo API 返回数据不完整: {json.dumps(info, ensure_ascii=False)[:200]}")

    return {
        "courseKey": course_key,
        "lessonId": str(lesson_id),
        "lessonStatus": lesson_status,
    }


def parse_classin_url(url):
    """从 ClassIn 回放链接中提取 courseKey/lessonKey 和 lessonid

    支持多种格式：
    - https://live.eeo.cn/webcast.php?courseKey=xxx&lessonid=yyy
    - https://www.eeo.cn/webcast.php?courseKey=xxx&lessonid=yyy
    - https://live.eeo.cn/pc.html?lessonKey=xxx
    - https://live.eeo.cn/pc.html?lessonKey=xxx&lessonid=yyy

    Returns:
        tuple: (course_key_or_lessonKey, lesson_id_or_None, is_new_format)
    """
    if not url:
        raise ValueError("URL 为空")

    # 检测是否为新格式（pc.html?lessonKey=xxx）
    is_new_format = "pc.html" in url

    # 提取课程标识：courseKey / lessonKey 均可
    course_key = re.search(r'(?:courseKey|coursekey|lessonKey)=([^&]+)', url)
    lesson_id = re.search(r'(?:lessonid|lessonId|fileId)=([^&]+)', url)

    if not course_key:
        raise ValueError(f"无法从 URL 中提取课程标识（courseKey/lessonKey）: {url[:80]}")

    ck = course_key.group(1)
    lid = lesson_id.group(1) if lesson_id else None

    return ck, lid, is_new_format


def fetch_transcript(classin_url, timeout=15):
    """调 ClassIn API 获取字幕文本，返回完整转录字符串"""
    ck_or_lk, lid, is_new = parse_classin_url(classin_url)

    # ── 解析最终的 courseKey 和 fileId ──
    if lid:
        # ✅ 旧格式：URL 中包含录制视频的 fileId（19位数字），直接使用
        course_key = ck_or_lk
        file_id = lid
    else:
        # ❌ 新格式：pc.html?lessonKey=xxx 不含录制视频 fileId
        # lessonKey 解析出的 lessonId（10位）≠ fileId（19位录制文件ID）
        # fileId 只能通过需要 ClassIn 登录权限的 getLessonWebcastData API 获取
        resolved = _resolve_lesson_key(ck_or_lk, timeout=timeout)
        if resolved["lessonStatus"] != 1:
            status_names = {1: "已结束（有回放）", 2: "未开始/无回放", 10: "等待中", 11: "直播中"}
            hint = status_names.get(resolved["lessonStatus"], f"status={resolved['lessonStatus']}")
            raise RuntimeError(
                f"该课程暂无回放（状态: {hint}），"
                f"无法获取 AI 字幕。如需手动填写反馈，请关闭 AI 生成后直接编辑。"
            )
        # 课程有回放但新格式链接缺少录制视频的 fileId
        raise RuntimeError(
            f"当前链接是 ClassIn 新格式（pc.html），不含录制视频的 fileId 参数。\n"
            f"请使用旧格式链接：在浏览器打开该回放后，\n"
            f"从地址栏复制包含 courseKey 和 lessonid 的完整链接（webcast.php 格式），\n"
            f"或联系技术确认如何获取录制视频 ID。"
        )

    # ── 调用字幕 API ──
    payload = json.dumps({
        "classKey": course_key,
        "fileId": file_id,
        "subtitle": 1,
    }).encode()

    req = urllib.request.Request(
        _RICH_SUMMARY_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        raise RuntimeError(f"ClassIn API HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"ClassIn API 请求失败: {e.reason}")
    except json.JSONDecodeError:
        raise RuntimeError("ClassIn API 返回非 JSON 格式")

    # 检查错误
    errno = data.get("error_info", {}).get("errno", 0)
    if errno != 1:
        err_msg = data.get("error_info", {}).get("error", f"errno={errno}")
        details = data.get("error_info", {}).get("details", {})
        # 解析 API 返回的详细信息中是否包含内部 fileId 格式
        detail_msg = details.get("msg", "")
        # 视频总结生成失败 — 可能原因：AI 功能未开启 / 录制过期 / 文件ID不匹配
        friendly_msg = err_msg
        if "视频总结生成失败" in err_msg:
            # 检查内部错误中是否有 compound fileId 格式，说明 fileId 格式对但内容不匹配
            if "lmsActivity" in detail_msg:
                friendly_msg = (
                    "ClassIn AI 字幕提取失败：该链接中的录制文件 ID 可能不匹配或已过期。\n"
                    "建议：1) 确认在浏览器中能正常播放该回放并看到字幕\n"
                    "      2) 重新从 ClassIn 复制课程回放链接（确保链接中包含 lessonid= 参数）\n"
                    "      3) 如仍有问题，可关闭 AI 生成后手动填写反馈"
                )
            else:
                friendly_msg = (
                    "该回放暂无 AI 字幕（视频总结生成失败）。\n"
                    "可能原因：1) AI 教师功能未对该课程开放 2) 录制时间过久已不支持 AI 处理\n"
                    "建议：关闭 AI 生成后手动填写反馈，或联系 ClassIn 确认 AI 字幕功能已开启。"
                )
        elif detail_msg and "fileId" in detail_msg:
            friendly_msg = f"链接解析异常，请确认链接格式是否正确。{detail_msg}"
        raise RuntimeError(f"ClassIn API 返回错误: {friendly_msg}")

    # 提取字幕
    children = data.get("data", {}).get("content", {}).get("children", [])
    if not children:
        raise RuntimeError("ClassIn API 返回空字幕")

    lines = []
    for child in children:
        desc = (child.get("desc") or "").strip()
        times = child.get("metadata", {}).get("times", [])
        if desc:
            time_str = f"[{times[0]}]" if times else ""
            lines.append(f"{time_str} {desc}")

    return "\n".join(lines)
