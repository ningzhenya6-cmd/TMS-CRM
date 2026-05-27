#!/usr/bin/env python3
"""数据导出脚本 - 在服务器上定时运行，导出分析数据供 Claude/龙虾读取。

用法: python3 deploy/export_data.py
输出: analysis/*.json
"""
import os
import sys
import json
import time

# 添加项目根到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "analysis")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def export_quality():
    """导出回答质量分析：低分回答TOP 20"""
    try:
        from knowledge.feedback import list_feedback, get_quality_analysis
        downvoted = list_feedback(only_downvoted=True)[:20]
        quality = get_quality_analysis()
        return {"downvoted_answers": downvoted, "quality_summary": quality}
    except Exception as e:
        return {"error": str(e)}

def export_gaps():
    """导出知识盲区：零命中问题TOP 20"""
    try:
        from knowledge.queries import get_zero_kb_queries
        gaps = get_zero_kb_queries(20)
        return {"gaps": gaps, "count": len(gaps)}
    except Exception as e:
        return {"error": str(e)}

def export_hot():
    """导出热门问题TOP 20"""
    try:
        from knowledge.queries import get_hot_queries
        hot = get_hot_queries(20, 7)
        return {"hot_questions": hot}
    except Exception as e:
        return {"error": str(e)}

def export_trends():
    """导出7天趋势"""
    try:
        from knowledge.reports import get_weekly_report
        report = get_weekly_report()
        return {
            "daily_trend": report.get("daily_trend", []),
            "total_queries": report.get("total_queries", 0),
            "total_feedback": report.get("total_feedback", 0),
            "total_downvotes": report.get("total_downvotes", 0),
            "new_users": report.get("new_users", 0),
        }
    except Exception as e:
        return {"error": str(e)}

def export_feedback_summary():
    """导出反馈统计"""
    try:
        from knowledge.feedback import get_stats
        return get_stats()
    except Exception as e:
        return {"error": str(e)}

def export_store_stats():
    """导出知识库统计"""
    try:
        from knowledge.store import get_store
        store = get_store()
        return store.get_stats()
    except Exception as e:
        return {"error": str(e)}

def export_all_entries():
    """导出全部知识条目（含完整内容），让总负责人可以审阅和把控内容方向"""
    try:
        from knowledge.store import get_store
        store = get_store()
        entries = store.get_all_entries()
        # 按分类分组
        by_category = {}
        for e in entries:
            cat = e.get("category", "uncategorized")
            by_category.setdefault(cat, []).append({
                "id": e["id"],
                "title": e["title"],
                "content": e["content"][:300],  # 预览前300字
                "tags": e.get("tags", []),
                "is_active": e.get("is_active", True),
                "created_at": e.get("created_at", ""),
            })
        return {
            "total": len(entries),
            "active": sum(1 for e in entries if e.get("is_active", True)),
            "categories": sorted(by_category.keys()),
            "by_category": by_category,
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as e:
        return {"error": str(e)}

def export_recent_queries():
    """导出最近查询样本（脱敏）"""
    try:
        from knowledge.store import get_db
        db = get_db()
        rows = db.execute(
            "SELECT question, kb_count, web_search, created_at FROM query_log ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        return [{
            "question": r["question"][:100],
            "kb_count": r["kb_count"],
            "web_search": r["web_search"],
            "time": r["created_at"],
        } for r in rows]
    except Exception as e:
        return {"error": str(e)}

def main():
    print(f"[export] 导出分析数据到 {OUTPUT_DIR}/")

    exports = [
        ("quality", export_quality),
        ("gaps", export_gaps),
        ("hot", export_hot),
        ("trends", export_trends),
        ("feedback_summary", export_feedback_summary),
        ("store_stats", export_store_stats),
        ("all_entries", export_all_entries),
        ("recent_queries", export_recent_queries),
    ]

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    manifest = {"exported_at": ts, "files": []}

    for name, func in exports:
        try:
            data = func()
            filepath = os.path.join(OUTPUT_DIR, f"{name}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            manifest["files"].append({"name": name, "path": f"analysis/{name}.json"})
            print(f"  ✅ {name}.json")
        except Exception as e:
            print(f"  ❌ {name}.json: {e}")

    # Write manifest
    with open(os.path.join(OUTPUT_DIR, "_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n[export] 完成！共导出 {len(manifest['files'])} 个文件")

if __name__ == "__main__":
    main()
