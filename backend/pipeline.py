#!/usr/bin/env python3
"""
龙虾6号 v2 — ClassIn 课后反馈自动化
用法: python3 pipeline.py <ClassIn播放链接>
优化: 点击 AI Summary 标签 → 抓取内置字幕，速度提升 10 倍+
"""
import sys, os, json, re, time, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ═══════════════════════════════
# Step 1: 提取课程信息 + AI 字幕
# ═══════════════════════════════
def extract_all(url):
    """Playwright 打开页面 → 点击 AI Summary 标签 → 提取字幕"""
    print("[1/3] 打开 ClassIn 页面...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)

        # —— 提取页面元数据 ——
        page_text = page.evaluate("() => document.body ? document.body.innerText : ''")

        # —— 点击 AI Summary 标签，触发展示 ——
        captions_text = ""
        summary_text = ""
        try:
            ai_tab = page.locator('[class*="ai-tab"]').first
            if ai_tab.count() > 0:
                ai_tab.click()
                page.wait_for_timeout(3000)

            # 从 DOM 的 ai-summary 面板中提取
            ai = page.evaluate("""() => {
                const p = document.querySelector('[class*="ai-summary"]');
                if (!p) return {s:'', c:''};
                const t = p.innerText || '';
                const ci = t.indexOf('Captions');
                if (ci > 0) return {s: t.substring('Summary'.length, ci).trim(), c: t.substring(ci+8).trim()};
                const si = t.indexOf('Summary');
                if (si>=0) return {s: t.substring(si+7).trim(), c:''};
                return {s:'', c:t};
            }""")
            summary_text = ai['s']
            captions_text = ai['c']
            if captions_text:
                print(f"   \u2705 AI \u5b57\u5e55: {len(captions_text)}\u5b57")
            if summary_text:
                print(f"   \u2705 AI \u6458\u8981: {len(summary_text)}\u5b57")
        except Exception as e:
            print(f"   \u26a0\ufe0f \u5b57\u5e55\u6293\u53d6\u5931\u8d25: {e}")

        # —— 视频源（fallback用） ——
        video_url = page.evaluate("""() => {
            const v = document.querySelector('video source, video');
            return v ? (v.src || v.getAttribute('src') || '') : '';
        }""")
        browser.close()

    transcript = captions_text.strip() if captions_text.strip() else page_text
    info = parse_meta(page_text, url)
    info["video_url"] = video_url
    info["has_ai_captions"] = bool(captions_text.strip())
    info["ai_summary"] = summary_text.strip()

    print(f"   \u5b66\u751f: {info['student']}  |  \u6559\u5e08: {info['teacher']}")
    print(f"   \u8bfe\u7a0b: {info['course']}  |  \u65e5\u671f: {info['date']}  |  \u65f6\u957f: {info['duration']}")
    src = 'ClassIn AI \u5b57\u5e55' if info['has_ai_captions'] else '\u9875\u9762\u6587\u672c(\u9700fallback)'
    print(f"   \u5b57\u5e55\u6765\u6e90: {src}")
    return info, transcript


def parse_meta(text, url):
    """解析学生/教师/课程/日期"""
    student = teacher = course = date_str = duration_str = ""
    hours = 1.0

    lines = text.strip().split('\n')
    title_line = ""
    for line in lines[:5]:
        m = re.match(r'^(\w\d+[-—–\s]+)(.+?)\s*$', line)
        if m and ('辅导' in line or '同步' in line or '-' in line):
            title_line = line.strip()
            break
    if title_line:
        parts = title_line.split('-')
        if len(parts) >= 2:
            student = parts[1].strip() if len(parts) > 1 else ""
            course = title_line

    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    if date_match:
        date_str = date_match.group(1)

    dur_match = re.search(r'\((\d+)min\)', text)
    if dur_match:
        mins = int(dur_match.group(1))
        duration_str = f"{mins//60}h{mins%60:02d}min" if mins >= 60 else f"{mins}min"
        hours = round(mins / 60, 1)

    teacher_match = re.search(r'About Teacher\s*\n?\s*\n?\s*(\S+)', text)
    if teacher_match:
        teacher = teacher_match.group(1).strip()

    if not dur_match:
        dur2 = re.search(r'Duration\s*(\d+):(\d+):(\d+)', text)
        if dur2:
            h, m, s = int(dur2.group(1)), int(dur2.group(2)), int(dur2.group(3))
            total_min = h * 60 + m + (1 if s > 0 else 0)
            duration_str = f"{h}h{m:02d}min"
            hours = round(total_min / 60, 1)

    return dict(student=student or "未知", teacher=teacher or "未知",
                course=course or "未知", date=date_str or time.strftime("%Y-%m-%d"),
                duration=duration_str or "未知", hours=hours)


# ═══════════════════════════════
# Step 2: DeepSeek 生成反馈
# ═══════════════════════════════
def call_llm(prompt):
    api_key = _load_api_key()
    if not api_key:
        print("   \u26a0\ufe0f \u672a\u627e\u5230 API Key\uff0c\u8fd4\u56deprompt")
        return None, prompt

    print("[2/3] DeepSeek \u751f\u6210\u53cd\u9988...")
    data = json.dumps(dict(model="deepseek-chat", messages=[
        dict(role="system", content="你是一位经验丰富的留学生学科辅导老师。你的反馈专业、具体、言之有物。"),
        dict(role="user", content=prompt)
    ], temperature=0.7, max_tokens=2000)).encode()

    req = urllib.request.Request("https://api.deepseek.com/v1/chat/completions", data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            feedback = result["choices"][0]["message"]["content"]
            print(f"   \u2705 \u53cd\u9988\u751f\u6210: {len(feedback)}\u5b57")
            return feedback, None
    except Exception as e:
        print(f"   \u274c API\u5931\u8d25: {e}")
        return None, prompt


def _load_api_key():
    """找 DEEPSEEK_API_KEY：先读 CRM 项目 .env，再读外部路径，最后检查环境变量"""
    # 1) CRM 项目根目录 .env
    crm_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if os.path.exists(crm_env):
        with open(crm_env) as f:
            for line in f:
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip()
    # 2) 外部路径
    env_paths = [
        os.path.expanduser("~/study-ai/.env"),
        os.path.join(os.path.dirname(__file__), "..", "..", "study-ai", ".env"),
    ]
    for p in env_paths:
        if os.path.exists(p):
            with open(p) as f:
                for line in f:
                    if line.startswith("DEEPSEEK_API_KEY="):
                        return line.split("=", 1)[1].strip()
    # 3) 环境变量
    return os.environ.get("DEEPSEEK_API_KEY", "")


# ═══════════════════════════════
# Step 3: 构建 prompt + 保存
# ═══════════════════════════════
def build_and_save(info, transcript):
    """构建 prompt → 调 API → 保存"""
    extra = ""
    if info.get("ai_summary"):
        extra = f"\n\nClassIn AI 课程摘要（辅助参考）：\n{info['ai_summary'][:800]}"

    prompt = f"""你是留学生学科辅导老师，刚上完课。请根据课堂内容写课后反馈，直接微信发给家长。

采用**两层结构**：

【第一层：客观描述】严格基于课堂内容，只写事实
📖授课内容 → 用 ▸ 列出本节课讲了哪些知识点
🙋课堂表现 → 只写客观事实：学生能完成什么、在哪里犯错、学生主动说了什么困扰、老师给了什么具体建议
⚠️需要注意 → 课堂中暴露的具体薄弱点
📅后续安排 → 下次课的内容安排

【第二层：分析参考】供学管/班主任内部参考
💡学习建议 → 你的专业分析和建议（写给工作人员的，可以有自己的判断）
  包括：整体情况评估、学生遇到的困难与老师建议的解决方案、值得关注的学习模式、给学管的参考建议

要求：
- 用 ▸ 列出知识点
- 回放列出具体时间戳
- 不要markdown加粗，纯文字
- 长度控制在家长1分钟内能读完

学生：{info['student']}
课程：{info['course']}
日期：{info['date']}
教师：{info['teacher']}
时长：{info['duration']}

课堂内容：
{transcript[:5000]}{extra}

直接输出反馈："""

    feedback, raw = call_llm(prompt)

    safe = info['student'].replace('/', '_').replace(' ', '')
    d = info['date'].replace('-', '')

    # 保存转录
    tf = os.path.join(OUTPUT_DIR, f"transcript_{safe}_{d}.txt")
    with open(tf, "w", encoding="utf-8") as f:
        f.write(f"学生: {info['student']}\n教师: {info['teacher']}\n")
        f.write(f"课程: {info['course']}\n日期: {info['date']}\n时长: {info['duration']}\n")
        f.write(f"字幕来源: {'ClassIn AI' if info.get('has_ai_captions') else '页面文本'}\n")
        f.write("=" * 50 + "\n\n" + transcript)

    # 保存反馈
    if feedback:
        ff = os.path.join(OUTPUT_DIR, f"feedback_{safe}_{d}.md")
        with open(ff, "w", encoding="utf-8") as f:
            f.write(f"---\n学生: {info['student']}\n课程: {info['course']}\n日期: {info['date']}\n教师: {info['teacher']}\n时长: {info['duration']}\n---\n\n{feedback}")
        print(f"\n   \U0001f4c4 反馈: {ff}")

    if raw and not feedback:
        pf = os.path.join(OUTPUT_DIR, f"prompt_{safe}_{d}.txt")
        with open(pf, "w") as f:
            f.write(raw)
        print(f"   \U0001f4dd Prompt备用: {pf}")

    print(f"   \U0001f4dd 转录: {tf}")
    return tf, feedback


# ═══════════════════════════════
# Fallback: ffmpeg + Whisper
# ═══════════════════════════════
def fallback_extract(info):
    import subprocess
    vu = info.get("video_url", "")
    if not vu:
        print("\u274c 无视频源，且无 AI 字幕"); return None
    print("\n[Fallback] \u8d70\u97f3\u9891\u8f6c\u5f55...")
    ap = "/tmp/classin_audio_fb.mp3"
    subprocess.run(["ffmpeg", "-y", "-i", vu, "-vn", "-acodec", "mp3",
                     "-ar", "16000", "-loglevel", "error", ap],
                   capture_output=True, text=True, timeout=300)
    if not os.path.exists(ap):
        print("\u274c \u97f3\u9891\u5931\u8d25"); return None
    import whisper
    model = whisper.load_model("small")
    result = model.transcribe(ap, language="zh")
    t = result["text"]
    print(f"   \u8f6c\u5f55: {len(t)}\u5b57")
    return t


# ═══════════════════════════════
# 主流程
# ═══════════════════════════════
def main(url):
    print("=" * 60)
    print("  \U0001f99e\u867e6\u53f7 v2 \u00b7 \u8bfe\u540e\u53cd\u9988\u81ea\u52a8\u5316")
    print("=" * 60)

    info, transcript = extract_all(url)
    if not info["has_ai_captions"]:
        print("\n\u26a0\ufe0f \u6ca1\u6709AI\u5b57\u5e55\uff0c\u8d70\u97f3\u9891\u8f6c\u5f55(\u8f83\u6162)...")
        transcript = fallback_extract(info)
        if not transcript:
            return None, None, None

    tf, feedback = build_and_save(info, transcript)

    print("\n" + "=" * 60)
    src = "ClassIn AI" if info["has_ai_captions"] else "Whisper\u8f6c\u5f55"
    print(f"  \u5b8c\u6210 \u2705  \u5b57\u5e55\u6765\u6e90: {src}")
    if feedback:
        print(f"  \u53cd\u9988: {len(feedback)}\u5b57")
        print(f"\n{'='*40}\n\u53cd\u9988\u9884\u89c8:\n{'='*40}")
        print(feedback[:400])
        print(f"\n... \u5168\u6587\u5df2\u4fdd\u5b58\u5230 output/")
    print("=" * 60)

    return info, transcript, feedback


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 pipeline.py <ClassIn链接>")
        sys.exit(1)

    info, transcript, feedback = main(sys.argv[1])

    # CRM integration: JSON 输出给 feedback_generator.py 解析
    print("\n__JSON_RESULT__")
    print(json.dumps({
        "info": info,
        "transcript": (transcript or "")[:5000],
        "transcript_length": len(transcript or ""),
        "feedback_text": feedback or "",
    }, ensure_ascii=False))
