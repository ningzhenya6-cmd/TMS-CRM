"""
数据迁移脚本 — 从旧 sm_system/sm.db 迁移到新 tms.db
安全：只读读取旧数据库，写入新数据库
用法：python3 migrate.py
"""
import os
import sys
import sqlite3

# ── 路径 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OLD_DB_PATH = os.path.join(BASE_DIR, "..", "sm_system", "sm.db")
NEW_DB_PATH = os.path.join(BASE_DIR, "data", "tms.db")


def connect_old():
    """连接旧数据库（只读）"""
    if not os.path.isfile(OLD_DB_PATH):
        print(f"[错误] 旧数据库不存在: {OLD_DB_PATH}")
        sys.exit(1)
    db = sqlite3.connect(OLD_DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def connect_new():
    """连接新数据库（写入）"""
    db = sqlite3.connect(NEW_DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=OFF")  # 临时关闭外键约束
    return db


def migrate_users(old, new):
    """迁移用户表"""
    print("\n=== 迁移用户 ===")
    old_users = old.execute("SELECT * FROM users").fetchall()
    # 旧用户密码哈希
    password_map = {}
    for u in old_users:
        password_map[u["id"]] = u["password_hash"]

    id_map = {}  # old_id → new_id
    for u in old_users:
        # 检查是否已存在（同名用户）
        existing = new.execute(
            "SELECT id FROM users WHERE username=?", (u["username"],)
        ).fetchone()
        if existing:
            id_map[u["id"]] = existing["id"]
            print(f"  跳过（已存在）: {u['username']} → id={existing['id']}")
            continue

        cur = new.execute(
            """INSERT INTO users (username, password, display_name, role, phone, active, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                u["username"],
                u["password_hash"],  # 保持原密码哈希
                u["name"],
                _map_role(u["role"]),
                        u["phone"] or "",
                1 if u["is_active"] else 0,
                u["created_at"] or "",
            ),
        )
        new.commit()
        new_id = cur.lastrowid
        id_map[u["id"]] = new_id
        print(f"  ✓ {u['username']} ({u['name']}) → id={new_id}")

    print(f"  共迁移 {len(old_users)} 个用户")
    return id_map


def _map_role(old_role):
    """映射旧角色名到新角色名"""
    m = {
        "admin": "admin",
        "supervisor": "supervisor",
        "cs": "cs",
        "consultant": "consultant",
        "coordinator": "coordinator",
        "academic": "academic",
        "tutor": "tutor",
        "staff": "cs",
    }
    return m.get(old_role, "cs")


def migrate_leads(old, new, user_id_map):
    """迁移线索表"""
    print("\n=== 迁移线索 ===")
    old_leads = old.execute("SELECT * FROM leads ORDER BY created_at ASC").fetchall()

    # 获取默认 admin id
    admin_id = user_id_map.get("u_admin", 1)

    lead_id_map = {}  # old_id → new_id
    count = 0
    for l_raw in old_leads:
        l = dict(l_raw)
        assignee_id = user_id_map.get(l.get("assignee_id")) if l.get("assignee_id") else None
        creator_id = user_id_map.get(l.get("created_by_id"), admin_id)

        # 检查是否已存在（同名+手机去重）
        existing = new.execute(
            "SELECT id FROM leads WHERE name=? AND phone=?",
            (l["name"], l.get("phone", "")),
        ).fetchone()
        if existing:
            print(f"  跳过（已存在）: {l['name']}")
            lead_id_map[l["id"]] = existing["id"]
            continue

        status = l["status"] if l["status"] in (
            "pending", "assigned", "following", "trial", "enrolled", "closed", "lost"
        ) else "pending"

        cur = new.execute(
            """INSERT INTO leads (name, phone, wechat, source, country, grade, status,
               assignee_id, creator_id, remark, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                l["name"],
                l.get("phone", ""),
                l.get("wechat", ""),
                l.get("source", "其他"),
                l.get("country", ""),
                l.get("grade", ""),
                status,
                assignee_id,
                creator_id,
                l.get("notes", ""),
                l.get("created_at", ""),
                l.get("updated_at", ""),
            ),
        )
        new.commit()
        new_id = cur.lastrowid
        lead_id_map[l["id"]] = new_id
        count += 1

    print(f"  共迁移 {count} 条线索")
    return lead_id_map


def migrate_followups(old, new, user_id_map, lead_id_map):
    """迁移跟进记录（旧 activities → 新 followups）"""
    print("\n=== 迁移跟进记录 ===")
    old_activities = old.execute(
        "SELECT * FROM activities ORDER BY created_at ASC"
    ).fetchall()

    count = 0
    skipped = 0
    for a_raw in old_activities:
        a = dict(a_raw)
        created_by = user_id_map.get(a.get("user_id"), 1)
        new_lead_id = lead_id_map.get(a.get("lead_id")) if a.get("lead_id") else None

        if not new_lead_id:
            skipped += 1
            print(f"  跳过（线索不存在）: activity {a['id']}")
            continue

        new.execute(
            """INSERT INTO followups (lead_id, content, next_action, next_date, created_by, created_at)
               VALUES (?,?,?,?,?,?)""",
            (
                new_lead_id,
                a.get("content", ""),
                a.get("next_action", ""),
                a.get("next_action_date", ""),
                created_by,
                a.get("created_at", ""),
            ),
        )
        new.commit()
        count += 1

    print(f"  共迁移 {count} 条跟进记录（跳过 {skipped} 条）")


def main():
    print("=" * 50)
    print("TMS 数据迁移工具")
    print(f"旧数据库: {OLD_DB_PATH}")
    print(f"新数据库: {NEW_DB_PATH}")
    print("=" * 50)

    if not os.path.isfile(NEW_DB_PATH):
        print("[错误] 新数据库不存在，请先启动一次新系统以创建数据库")
        sys.exit(1)

    old = connect_old()
    new = connect_new()

    try:
        # 1. 迁移用户
        user_id_map = migrate_users(old, new)

        # 2. 迁移线索
        lead_id_map = migrate_leads(old, new, user_id_map)

        # 3. 迁移跟进记录
        migrate_followups(old, new, user_id_map, lead_id_map)

        print("\n" + "=" * 50)
        print("迁移完成！")
        print("=" * 50)
        print("\n请重启 TMS 服务以查看迁移后的数据。")

    finally:
        old.close()
        new.close()


if __name__ == "__main__":
    main()
