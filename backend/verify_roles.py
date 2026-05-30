#!/usr/bin/env python3
"""验证各角色数据隔离和权限"""
import sqlite3

conn = sqlite3.connect('data/tms.db')
conn.row_factory = sqlite3.Row

def q(sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]

def q1(sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None

print("=== 用户列表 ===")
for u in q("SELECT id,username,display_name,role FROM users ORDER BY id"):
    print("  %3d | %-15s | %-10s | %-12s" % (u["id"], u["username"], u["display_name"], u["role"]))

print("\n=== 线索状态 ===")
for r in q("SELECT status,count(*) as c FROM leads GROUP BY status"):
    print("  %-12s: %d" % (r["status"], r["c"]))

print("\n=== 签约学生 ===")
stmt = """SELECT l.id,l.name,u.display_name as a,uc.display_name as c
    FROM leads l LEFT JOIN users u ON l.assignee_id=u.id
    LEFT JOIN users uc ON l.coordinator_id=uc.id
    WHERE l.status='enrolled' ORDER BY l.id"""
for r in q(stmt):
    print("  #%d %-8s | 顾问=%-6s | 班主任=%s" % (r["id"], r["name"], r["a"] or "-", r["c"] or "未分配"))

print("\n=== 合同+课时 ===")
stmt = """SELECT c.id,l.name,c.status,c.total_amount,
    COALESCE((SELECT SUM(p.total_hours) FROM packages p WHERE p.contract_id=c.id),0) as th,
    COALESCE((SELECT SUM(p.used_hours) FROM packages p WHERE p.contract_id=c.id),0) as uh
    FROM contracts c JOIN leads l ON c.lead_id=l.id ORDER BY c.id"""
for r in q(stmt):
    print("  合同#%d %-8s %-8s ¥%8.0f | %.0fh/%.0fh/剩%.1fh" % (r["id"], r["name"], r["status"], r["total_amount"], r["th"], r["uh"], r["th"]-r["uh"]))

print("\n=== 排课 ===")
stmt = """SELECT s.id,l.name,s.subject,s.start_time,s.status,s.duration_minutes,
    tu.display_name as tn FROM schedules s JOIN leads l ON s.lead_id=l.id
    LEFT JOIN users tu ON s.tutor_id=tu.id ORDER BY s.id"""
for r in q(stmt):
    print("  #%d %-8s %-10s %-16s %-10s %dmin %s" % (r["id"], r["name"], r["subject"] or "-", r["start_time"][:16], r["status"], r["duration_minutes"], r["tn"] or "-"))

print("\n=== 角色数据隔离 ===")

print("consultant(宁老师,id=1):")
print("  我的线索: %d" % q1("SELECT count(*) as c FROM leads WHERE assignee_id=1")["c"])
print("  已签约: %d" % q1("SELECT count(*) as c FROM leads WHERE assignee_id=1 AND status='enrolled'")["c"])

print("coordinator(教务李老师,id=18):")
print("  我的学生: %d" % q1("SELECT count(*) as c FROM leads WHERE coordinator_id=18 AND status='enrolled'")["c"])
stmt = "SELECT count(*) as c FROM schedules s JOIN leads l ON s.lead_id=l.id WHERE l.coordinator_id=18 AND s.status='pending'"
print("  待排课(我的): %d" % q1(stmt)["c"])

print("academic(学管师,id=16):")
print("  我的线索(assignee): %d" % q1("SELECT count(*) as c FROM leads WHERE assignee_id=16")["c"])
print("  已签约: %d" % q1("SELECT count(*) as c FROM leads WHERE assignee_id=16 AND status='enrolled'")["c"])

print("admin:")
print("  全部线索: %d" % q1("SELECT count(*) as c FROM leads")["c"])
print("  签约学生: %d" % q1("SELECT count(*) as c FROM leads WHERE status='enrolled'")["c"])

conn.close()
print("\n验证完成")
