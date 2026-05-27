#!/usr/bin/env python3
"""生成分类映射文件，用于将知识条目的分类和标签更新到服务器。

用法: python3 deploy/gen_category_mapping.py
输出: deploy/category_mapping.json
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from deploy.import_server_data import auto_categorize, auto_tag

def main():
    src = "/Users/fishdebaobei/Desktop/knowledge.json"
    with open(src, "r", encoding="utf-8") as f:
        raw = json.load(f)
    entries = raw.get("entries", [])

    updates = []
    for e in entries:
        eid = e["id"]
        cat = auto_categorize(e.get("title", ""), e.get("content", ""))
        tags = auto_tag(e.get("title", ""), e.get("content", ""))
        is_test = len(e.get("content", "")) < 50 and (
            "测试" in e.get("title", "") or "test" in e["title"].lower()
        )
        updates.append({
            "id": eid,
            "category": cat,
            "tags": tags,
            "is_active": 0 if is_test else 1,
            "title": e["title"],
            "old_category": e.get("category", "general"),
        })

    changed = [u for u in updates if u["category"] != u["old_category"] or u["is_active"] == 0]
    print(f"Total: {len(updates)}, Need update: {len(changed)}")

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "category_mapping.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(updates, f, ensure_ascii=False, indent=2)
    print(f"Saved {out}")

if __name__ == "__main__":
    main()
