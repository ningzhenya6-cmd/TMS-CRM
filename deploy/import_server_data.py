#!/usr/bin/env python3
"""导入线上服务器导出的 knowledge.json 到本地数据库。
同时自动对条目进行分类和打标签。

用法: python3 deploy/import_server_data.py /path/to/knowledge.json
"""
import json
import os
import re
import sys
import time
import sqlite3

# 添加项目根到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "knowledge.db")

# ============ 分类规则 ============

CATEGORY_RULES = [
    # 法律
    (r"法学|LLB|LLM|法律|law|Law|IRAC|OSCOLA|判例|普通法|大陆法|contract|tort", "uk-law"),
    (r"刑法|宪法|Constitutional|constitutional", "uk-law"),
    # 计算机
    (r"计算机|CS\b|编程|coding|Python|Java|算法|数据结构|Machine Learning|深度学习|AI\b|人工智能|操作系统|计算机网络|软件工程", "cs-it"),
    # 经济/金融/商科
    (r"经济|Econ|econ|金融|Finance|finance|会计|accounting|Accounting|商科|Business|business|市场营销|marketing|管理|management|MBA", "economics-finance"),
    # 论文/学术写作
    (r"Essay|essay|论文|学术写作|Academic Writing|literature review|Literature Review|方法论|methodology|Methodology|dissertation|Dissertation|thesis|引用|citation|reference|Paraphrasing|paraphrasing|Turnitin|plagiarism|Plagiarism|critical analysis|Critical Analysis", "academic-writing"),
    # 挂科申诉
    (r"挂科|appeal|Appeal|申诉|academic warning|Show Cause|退学|开除|补考|resit|Academic Probation", "appeal"),
    # 心理/健康
    (r"抑郁|焦虑|心理健康|心理|mental health|压力|失眠|冒名顶替|imposter|Imposter", "mental-health"),
    # 家长
    (r"家长|孩子|女儿|儿子|妈妈|爸爸|父母|家校", "parent-guide"),
    # 高中/预科/A-Level
    (r"A-Level|Alevel|alevel|AS\b|IB\b|AP\b|AP\s|OSSD|IGCSE|GCSE|高中|预科|Foundation|foundation|低龄|寄宿", "pre-university"),
    # 面试
    (r"面试|interview|Interview", "career"),
    # 选课/转学
    (r"选课|转学|转专业|选校|课程选择|drop|withdraw|退课", "course-selection"),
    # 签证
    (r"签证|visa|Visa|I-20|SEVIS|移民", "visa"),
    # 新加坡
    (r"NUS\b|NTU\b|新加坡|SMU|新加坡国立", "sg-general"),
    # 香港
    (r"港大|港中文|港科大|香港|HKU|CUHK|HKUST", "hk-general"),
    # 澳洲
    (r"悉尼大学|UNSW|墨尔本大学|莫纳什|昆士兰|澳洲|RMIT|阿德莱德|西澳", "au-general"),
    # 加拿大
    (r"多伦多大学|UBC|滑铁卢|麦吉尔|加拿大|加拿大|OSSD|安省", "ca-general"),
    # 美国
    (r"UCLA|UCSD|UC\b|加州|NYU|USC|OSU\b|美国|美本|美高|社区大学|Top\s?\d+", "us-general"),
    # 英国
    (r"布里斯托|KCL|伦敦|爱丁堡|曼大|曼彻斯特|华威|LSE|帝国理工|牛津|剑桥|UCL|拉夫堡|利物浦|伯明翰|谢菲尔德|格拉斯哥|利兹|萨塞克斯|圣安德鲁斯|杜伦|英国|英本|英高|G5", "uk-general"),
]

def auto_categorize(title, content):
    """根据标题和内容自动判断分类"""
    text = (title + " " + content)[:2000]
    for pattern, category in CATEGORY_RULES:
        if re.search(pattern, text):
            return category
    return "general"


TAG_RULES = [
    (r"法学|LLB|LLM|law|Law|legal|IRAC|OSCOLA|判例", "法学"),
    (r"计算机|CS\b|编程|Python|Java|Algorithm|数据结构|Machine Learning|深度学习|AI\b|人工智能|软件", "计算机科学"),
    (r"经济|Econ|econ|经济学", "经济学"),
    (r"金融|Finance|finance", "金融"),
    (r"会计|accounting|Accounting", "会计"),
    (r"商科|Business|business|MBA|management|Management", "商科"),
    (r"市场营销|marketing|Marketing", "市场营销"),
    (r"传媒|media|Media|传播|communication", "传媒"),
    (r"教育|Education|education|教育学", "教育"),
    (r"心理|psychology|Psychology", "心理学"),
    (r"工程|Engineering|engineering|EEE\b|机械|土木|化学工程", "工程"),
    (r"数学|math|Math|微积分|统计|Statistics|统计", "数学/统计"),
    (r"物理|Physics|physics", "物理"),
    (r"化学|Chemistry|chemistry", "化学"),
    (r"生物|Biology|biology|生命科学", "生物"),
    (r"医学|医学|Medicine|medicine|护理|药学", "医学/护理"),
    (r"论文|essay|Essay|dissertation|thesis|学术写作", "学术写作"),
    (r"Literature Review|literature review", "文献综述"),
    (r"方法论|methodology|Methodology", "方法论"),
    (r"引用|citation|reference|Harvard|APA|OSCOLA|Turnitin", "引用规范"),
    (r"挂科|appeal|申诉|Show Cause|学术警告|退学|开除|Academic Probation", "挂科申诉"),
    (r"补考|resit", "补考"),
    (r"面试|interview|Interview", "面试"),
    (r"选课|course selection|退课|drop|withdraw", "选课"),
    (r"转学|转专业|transfer", "转学"),
    (r"预习|衔接|跟不上|同步辅导", "学业衔接"),
    (r"小组作业|group work|Group work|presentation", "小组作业"),
    (r"签证|visa|Visa", "签证"),
    (r"家长|孩子|女儿|儿子", "家长指南"),
    (r"抑郁|焦虑|心理健康|压力|失眠|imposter|冒名顶替", "心理健康"),
    (r"实习|intern|Intern|求职|找工作|就业|Career|career", "职业发展"),
    (r"A-Level|Alevel|AS\b|IB\b|AP\s|IGCSE|GCSE|OSSD", "国际课程"),
    (r"预科|Foundation|foundation", "预科"),
    (r"低龄留学|寄宿|中学", "低龄留学"),
    (r"四个诊断|四维诊断|四维", "四维诊断"),
    (r"学管|顾问|规划|辅导", "学管服务"),
    (r"学术诚信|抄袭|plagiarism|Plagiarism|学术不端", "学术诚信"),
    (r"英国|UK\b|uk\b", "英国留学"),
    (r"美国|US\b|us\b|美本|美高", "美国留学"),
    (r"澳洲|澳大利亚|悉尼|墨尔本", "澳洲留学"),
    (r"加拿大|加拿大|多伦多|UBC|滑铁卢", "加拿大留学"),
    (r"新加坡|NUS|NTU|新加坡国立|南洋理工", "新加坡留学"),
    (r"香港|港大|港中文|港科大", "香港留学"),
    (r"GPA|gpa", "GPA管理"),
    (r"博士|PhD|博士|Research Proposal", "博士申请"),
    (r"硕士|研究生|Master|master|grad", "硕士申请"),
    (r"本科|本科|undergraduate", "本科申请"),
]

def auto_tag(title, content):
    """自动打标签，最多8个"""
    text = (title + " " + content)[:2000]
    tags = []
    for pattern, tag in TAG_RULES:
        if re.search(pattern, text):
            if tag not in tags:
                tags.append(tag)
    return tags[:8]  # 最多8个标签


def main():
    src_path = sys.argv[1] if len(sys.argv) > 1 else "/Users/fishdebaobei/Desktop/knowledge.json"

    print(f"读取数据: {src_path}")
    with open(src_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", data.get("results", []))
    print(f"共 {len(entries)} 条待导入")

    # 分析内容
    cat_stats = {}
    tag_stats = {}
    test_ids = []

    # 先分析分类
    for e in entries:
        cat = auto_categorize(e.get("title", ""), e.get("content", ""))
        e["_auto_category"] = cat
        cat_stats[cat] = cat_stats.get(cat, 0) + 1

    print("\n=== 自动分类结果 ===")
    for cat, cnt in sorted(cat_stats.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}条")

    # 再打标签
    for e in entries:
        tags = auto_tag(e.get("title", ""), e.get("content", ""))
        e["_auto_tags"] = tags
        for t in tags:
            tag_stats[t] = tag_stats.get(t, 0) + 1

    print(f"\n=== 标签统计 (共{len(tag_stats)}种) ===")
    for tag, cnt in sorted(tag_stats.items(), key=lambda x: -x[1])[:20]:
        print(f"  {tag}: {cnt}条")

    # 识别测试条目
    test_entries = [e for e in entries if
                    re.search(r'测试|test', e.get('title',''), re.I) and
                    len(e.get('content','')) < 50]
    print(f"\n识别到 {len(test_entries)} 条测试数据（将标记为不活跃）")

    # ===== 写入数据库 =====
    print("\n=== 导入数据库 ===")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")

    # 清空旧数据
    db.execute("DELETE FROM entries")
    db.execute("DELETE FROM fts5_entries")
    print("已清空旧数据")

    now = time.strftime("%Y-%m-%d %H:%M")
    imported = 0
    skipped = 0

    for e in entries:
        eid = e.get("id", "")
        title = e.get("title", "")
        content = e.get("content", "")
        category = e.get("_auto_category", "general")
        tags = json.dumps(e.get("_auto_tags", []), ensure_ascii=False)
        related_q = json.dumps(e.get("related_questions", []), ensure_ascii=False)
        created_at = e.get("created_at", "2026-05-24")

        # 测试条目标记为不活跃
        is_active = 1
        if e in test_entries:
            is_active = 0
            skipped += 1

        try:
            db.execute(
                "INSERT OR REPLACE INTO entries (id, title, content, category, tags, related_questions, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (eid, title, content, category, tags, related_q, is_active, created_at, now)
            )
            imported += 1
        except Exception as ex:
            print(f"  导入失败 [{eid}]: {ex}")

    db.commit()
    print(f"导入完成: {imported} 条 (其中{skipped}条测试数据已禁用)")

    # 重建 FTS5 索引
    print("\n=== 重建FTS5全文搜索索引 ===")
    db.execute("DELETE FROM fts5_entries")

    # 获取所有活跃条目
    rows = db.execute(
        "SELECT id, title, content, category, tags FROM entries WHERE is_active=1"
    ).fetchall()

    fts_count = 0
    for row in rows:
        eid = row["id"]
        tags_list = json.loads(row["tags"]) if row["tags"] else []
        # 构建搜索文本：标题 + 内容 + 分类 + 标签
        search_parts = [row["title"], row["content"], row["category"]] + tags_list
        search_text = " ".join(search_parts)
        # CJK 空格处理
        search_text = re.sub(r"(?<=[一-鿿])(?=[一-鿿])", " ", search_text)

        db.execute(
            "INSERT OR REPLACE INTO fts5_entries(entry_id, search_text) VALUES (?, ?)",
            (eid, search_text)
        )
        fts_count += 1

    db.commit()
    print(f"FTS5索引重建完成: {fts_count} 条")

    # 验证
    print("\n=== 验证 ===")
    total = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    active = db.execute("SELECT COUNT(*) FROM entries WHERE is_active=1").fetchone()[0]
    print(f"数据库总计: {total} 条 (活跃: {active} 条)")

    cats = db.execute("SELECT category, COUNT(*) as cnt FROM entries WHERE is_active=1 GROUP BY category ORDER BY cnt DESC").fetchall()
    print(f"\n分类统计:")
    for c in cats:
        print(f"  {c['category']}: {c['cnt']}条")

    db.close()
    print("\n✅ 导入完成！")


if __name__ == "__main__":
    main()
