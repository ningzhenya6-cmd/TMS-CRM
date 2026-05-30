"""
迁移脚本：将生产环境 sm.db 的数据同步到本地新架构 tms.db
处理 UUID → INTEGER ID 映射、测试数据清理
"""
import sqlite3
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BACKEND_DIR, "data")
PROD_DB = os.path.join(DATA_DIR, "production_sm.db")
LOCAL_DB = os.path.join(DATA_DIR, "tms.db")

if not os.path.exists(PROD_DB):
    print("❌ 找不到生产数据库文件:", PROD_DB)
    sys.exit(1)

prod = sqlite3.connect(PROD_DB)
prod.row_factory = sqlite3.Row
local = sqlite3.connect(LOCAL_DB)
local.row_factory = sqlite3.Row

# 读取 local 已有数据
local_users = {row["username"]: dict(row) for row in local.execute("SELECT * FROM users")}
local_leads_map = {}  # (name, phone) -> local id
for row in local.execute("SELECT id, name, phone FROM leads"):
    phone = row["phone"] if row["phone"] else ""
    local_leads_map[(row["name"], phone)] = row["id"]

print(f"📊 本地已有 {len(local_users)} 个用户, {len(local_leads_map)} 条线索")

# ── 1. 用户角色同步 ──
print("\n=== 1. 用户角色同步 ===")
prod_users = {row["username"]: dict(row) for row in prod.execute("SELECT * FROM users")}

# 需要修正角色的本地用户
role_fixes = []
for uname, pu in prod_users.items():
    if uname in local_users:
        lu = local_users[uname]
        old_role = lu["role"]
        new_role = pu["role"]
        if old_role != new_role:
            role_fixes.append((new_role, lu["id"]))
            print(f"  🔄 {uname}: {old_role} → {new_role}")

for new_role, uid in role_fixes:
    local.execute("UPDATE users SET role=? WHERE id=?", (new_role, uid))
local.commit()
print(f"  ✅ {len(role_fixes)} 个用户角色已修正")

# 缺少的用户（生产有本地没有）
missing_users = []
for uname, pu in prod_users.items():
    if uname not in local_users:
        missing_users.append(pu)
        print(f"  ➕ 新增用户: {uname} ({pu['name']}) role={pu['role']}")

for pu in missing_users:
    local.execute(
        """INSERT INTO users (username, password, display_name, role, phone, active)
           VALUES (?,?,?,?,?,?)""",
        (pu["username"], "123456", pu["name"], pu["role"],
         pu["phone"] if pu["phone"] else "", pu["is_active"] if "is_active" in pu.keys() else 1),
    )
local.commit()
print(f"  ✅ {len(missing_users)} 个用户已新增")

# 刷新本地用户缓存
local_users = {row["username"]: dict(row) for row in local.execute("SELECT * FROM users")}

# ── 2. 线索同步（增量导入） ──
print("\n=== 2. 线索增量导入 ===")
# 构建生产用户名 → 本地用户ID 映射
prod_uname_to_local_id = {}
for uname, lu in local_users.items():
    # 通过 username 查找
    if uname in prod_users:
        prod_uname_to_local_id[prod_users[uname]["id"]] = lu["id"]

# 额外通过 display_name 匹配
for pu_id, pu in prod_users.items():
    if pu_id not in prod_uname_to_local_id:
        for _lu_name, lu in local_users.items():
            if lu["display_name"] == pu["name"]:
                prod_uname_to_local_id[pu_id] = lu["id"]
                break

print(f"  用户映射: {len(prod_uname_to_local_id)}/{len(prod_users)} 已匹配")

# 读取生产线索，导入本地没有的
imported_count = 0
lead_id_map = {}  # prod UUID → local INTEGER

for prow in prod.execute("SELECT * FROM leads ORDER BY created_at ASC"):
    name = prow["name"]
    phone = prow["phone"] if prow["phone"] else ""
    key = (name, phone)

    if key in local_leads_map:
        # 已存在
        lead_id_map[prow["id"]] = local_leads_map[key]
        continue

    # 新线索，插入本地
    assignee_new = prod_uname_to_local_id.get(prow["assignee_id"]) if prow["assignee_id"] else None
    creator_new = prod_uname_to_local_id.get(prow["created_by_id"]) if prow["created_by_id"] else None

    cur = local.execute(
        """INSERT INTO leads (name, phone, wechat, source, country, grade, status,
                              assignee_id, creator_id, remark, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (name, phone, prow["wechat"] if prow["wechat"] else "", prow["source"] if prow["source"] else "",
         prow["country"] if prow["country"] else "", prow["grade"] if prow["grade"] else "",
         prow["status"] if prow["status"] else "pending",
         assignee_new, creator_new or 1,
         prow["notes"] if prow["notes"] else "",
         prow["created_at"] if prow["created_at"] else "",
         prow["updated_at"] if prow["updated_at"] else ""),
    )
    new_id = cur.lastrowid
    lead_id_map[prow["id"]] = new_id
    local_leads_map[key] = new_id
    imported_count += 1
    if imported_count <= 5:
        print(f"  ➕ 导入线索: {name} (phone={phone}) → id={new_id}")

local.commit()
print(f"  ✅ 导入 {imported_count} 条新线索 (总数: {len(local_leads_map)})")

# ── 3. 跟进记录同步 ──
print("\n=== 3. 跟进记录同步 ===")
# 获取本地已有 followups 的 lead_id 集合
local_followup_leads = set()
for row in local.execute("SELECT DISTINCT lead_id FROM followups"):
    local_followup_leads.add(row["lead_id"])

imported_activities = 0
for arow in prod.execute("SELECT * FROM activities ORDER BY created_at ASC"):
    prod_lead_id = arow["lead_id"]
    if prod_lead_id not in lead_id_map:
        continue  # 线索不在本地
    local_lead_id = lead_id_map[prod_lead_id]

    # 避免重复导入（如果该线索已有跟进记录则跳过）
    if local_lead_id in local_followup_leads:
        continue

    user_new = prod_uname_to_local_id.get(arow["user_id"]) if arow["user_id"] else None
    local.execute(
        """INSERT INTO followups (lead_id, content, next_action, next_date, created_by, created_at)
           VALUES (?,?,?,?,?,?)""",
        (local_lead_id,
         arow["content"] or "",
         arow["next_action"] if arow["next_action"] else "",
         arow["next_action_date"] if arow["next_action_date"] else "",
         user_new or 1,
         arow["created_at"] if arow["created_at"] else ""),
    )
    imported_activities += 1

local.commit()
print(f"  ✅ 导入 {imported_activities} 条跟进记录")

# ── 4. 清理测试数据 ──
print("\n=== 4. 清理测试数据 ===")
# consulting_reports 全部是测试生成的
cr_count = local.execute("SELECT COUNT(*) FROM consulting_reports").fetchone()[0]
if cr_count > 0:
    local.execute("DELETE FROM consulting_reports")
    print(f"  🗑️ 删除 {cr_count} 条 consulting_reports (测试数据)")

# lesson_feedback, exam_results, admission_results 测试数据
for tbl in ["lesson_feedback", "exam_results", "admission_results"]:
    cnt = local.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    if cnt > 0:
        local.execute(f"DELETE FROM {tbl}")
        print(f"  🗑️ 删除 {cnt} 条 {tbl} (测试数据)")

local.commit()

# ── 总结 ──
print("\n" + "=" * 50)
print("📋 迁移总结")
print("=" * 50)
for tbl in ["users", "leads", "followups", "schedules", "contracts", "packages",
            "payment_records", "teachers", "consulting_reports"]:
    cnt = local.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    print(f"  {tbl}: {cnt}")

prod.close()
local.close()
print("\n✅ 迁移完成！")
