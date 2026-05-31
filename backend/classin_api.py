"""
ClassIn API 直调 — 获取课堂回放字幕，无需浏览器

用法:
    from classin_api import fetch_transcript
    text = fetch_transcript("https://live.eeo.cn/webcast.php?courseKey=xxx&lessonid=yyy")
    text = fetch_transcript("https://live.eeo.cn/pc.html?lessonKey=xxx")

策略：
- 旧格式 URL（含 lessonid=19位数字）→ 直接用 fileId 调 richVideoSummary API
- 新格式 URL（仅 lessonKey）→ 用 Playwright 加载页面提取视频 src 中的 fileId
"""
import json
import os
import re
import urllib.request
import urllib.error

# ── API 配置 ──
_RICH_SUMMARY_URL = "https://dynamic.eeo.cn/course-ai-assistant/app/share/richVideoSummary"
_LESSON_INFO_URL = "https://dynamic.eeo.cn/saasajax/webcast.ajax.php?action=getLessonClassInfo"


# ── 视频路径 → fileId 提取 ──
_VIDEO_FILEID_RE = re.compile(r'/([a-f0-9]{8})(\d{19})/')


def _extract_fileid_from_src(video_src):
    """从 ClassIn 视频播放 URL 中提取 19 位 fileId

    ClassIn 视频 URL 格式:
    https://playback.eeo.cn/{bucket}/{hex_prefix_8chars}{19_digit_fileid}/f0.mp4
    """
    m = _VIDEO_FILEID_RE.search(video_src)
    if m:
        return m.group(2)
    return None


def _fetch_fileid_via_playwright(lesson_key, timeout=30):
    """用 Playwright 加载 ClassIn 页面，从视频元素中提取 fileId

    新格式 URL (pc.html?lessonKey=xxx) 不含 fileId 参数。
    但页面的 video 元素的 src URL 中编码了 19 位 fileId。
    Playwright 加载页面后，video.src 自动填充，无需登录。
    """
    from playwright.sync_api import sync_playwright

    url = f"https://live.eeo.cn/pc.html?lessonKey={lesson_key}"
    with sync_playwright() as p:
        # 先尝试 Playwright 默认浏览器，若失败则用系统安装的 chromium
        launch_kwargs = {"headless": True}
        try:
            browser = p.chromium.launch(**launch_kwargs)
        except Exception:
            # 尝试系统路径
            for path in ("/usr/bin/chromium-browser", "/usr/bin/chromium", "/snap/bin/chromium"):
                import os as _os
                if _os.path.exists(path):
                    launch_kwargs["executable_path"] = path
                    break
            browser = p.chromium.launch(**launch_kwargs)
        try:
            context = browser.new_context(locale="zh-CN")
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)

            # 等待 video 元素出现并获取 src
            import time as _time
            deadline = _time.time() + timeout
            file_id = None
            while _time.time() < deadline:
                video_src = page.evaluate("""() => {
                    const v = document.querySelector('video');
                    return v ? (v.src || v.currentSrc || '') : '';
                }""")
                if video_src:
                    file_id = _extract_fileid_from_src(video_src)
                    if file_id:
                        break
                _time.sleep(1)

            if not file_id:
                raise RuntimeError(
                    f"无法从页面中提取视频 fileId（lessonKey={lesson_key}）。"
                    f"请确认该课程有回放录制，或使用旧格式链接。"
                )
            return file_id
        finally:
            browser.close()


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


def _call_rich_summary_api(class_key, file_id, timeout=15):
    """调用 ClassIn richVideoSummary API 获取字幕数据"""
    payload = json.dumps({
        "classKey": class_key,
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

    errno = data.get("error_info", {}).get("errno", 0)
    if errno != 1:
        err_msg = data.get("error_info", {}).get("error", f"errno={errno}")
        details = data.get("error_info", {}).get("details", {})
        detail_msg = details.get("msg", "")

        friendly_msg = err_msg
        if "视频总结生成失败" in err_msg:
            if "lmsActivity" in detail_msg:
                friendly_msg = (
                    "ClassIn AI 字幕提取失败：该链接中的录制文件 ID 可能不匹配或已过期。\n"
                    "建议：1) 确认在浏览器中能正常播放该回放并看到字幕\n"
                    "      2) 重新从 ClassIn 复制课程回放链接\n"
                    "      3) 或关闭 AI 生成后手动填写反馈"
                )
            else:
                friendly_msg = (
                    "该回放暂无 AI 字幕（视频总结生成失败）。\n"
                    "可能原因：AI 教师功能未对该课程开放，或录制时间过久已不支持 AI 处理。\n"
                    "建议：关闭 AI 生成后手动填写反馈。"
                )
        elif detail_msg and "fileId" in detail_msg:
            friendly_msg = f"链接解析异常，请确认链接格式是否正确。{detail_msg}"
        raise RuntimeError(f"ClassIn API 返回错误: {friendly_msg}")

    return data


def _parse_subtitles(data):
    """从 API 返回数据中提取字幕文本"""
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


def fetch_transcript(classin_url, timeout=15):
    """调 ClassIn API 获取字幕文本，返回完整转录字符串"""
    ck_or_lk, lid, is_new = parse_classin_url(classin_url)

    # ── 解析最终的 courseKey 和 fileId ──
    if lid:
        # 旧格式：URL 中直接包含 19 位录制 fileId
        class_key = ck_or_lk
        file_id = lid
    else:
        # 先解析 lessonKey 验证课程是否存在及状态
        resolved = _resolve_lesson_key(ck_or_lk, timeout=timeout)
        if resolved["lessonStatus"] != 1:
            status_names = {1: "已结束（有回放）", 2: "未开始/无回放", 10: "等待中", 11: "直播中"}
            hint = status_names.get(resolved["lessonStatus"], f"status={resolved['lessonStatus']}")
            raise RuntimeError(
                f"该课程暂无回放（状态: {hint}），"
                f"无法获取 AI 字幕。如需手动填写反馈，请关闭 AI 生成后直接编辑。"
            )
        # 新格式：用 Playwright 加载页面，从 video.src 中提取 fileId
        class_key = ck_or_lk
        file_id = _fetch_fileid_via_playwright(ck_or_lk, timeout=timeout)

    # ── 调用字幕 API ──
    data = _call_rich_summary_api(class_key, file_id, timeout=timeout)
    return _parse_subtitles(data)
