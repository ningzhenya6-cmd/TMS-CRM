"""
ClassIn 开放平台集成（预留）

本模块为 ClassIn API 对接提供架构预留，后续需配置 API Key 后方可启用。

=== 架构设计 ===

TMS CRM                  ClassIn
   │                        │
   │  1. 创建排课            │
   │  ──────────────────►   │  自动创建课程
   │                        │
   │  2. 查询课程           │
   │  ◄──────────────────   │  返回课程链接/信息
   │                        │
   │  3. 同步实际上课时长    │
   │  ◄──────────────────   │  课程结束回传时长
   │                        │

=== 配置项 ===

CLASSIN_API_KEY = ""       # 由 ClassIn 开放平台提供
CLASSIN_API_SECRET = ""    # 由 ClassIn 开放平台提供
CLASSIN_BASE_URL = "https://api.example.com/v1"

=== 实现路线 ===

第一阶段（当前）:
  - schedules 表已有 classin_link 字段，支持手动输入链接
  - 本文件提供函数签名和文档

第二阶段:
  - 对接 ClassIn 创建课程 API
  - 排课创建时自动调用 classin.create_class()
  - 存储返回的课程 ID + 链接到 schedules.classin_link

第三阶段:
  - 实现双向同步 Webhook
  - ClassIn → TMS: 课程状态变更、实际上课时长
  - TMS → ClassIn: 排课变更、取消
"""

import json
from typing import Optional


def create_class_session(
    course_name: str,
    start_time: str,
    end_time: str,
    teacher_name: str,
    student_name: str,
) -> Optional[str]:
    """在 ClassIn 创建课程

    返回课程链接（URL），失败返回 None

    参数:
        course_name: 课程名称/科目
        start_time: 开始时间，格式 YYYY-MM-DD HH:mm
        end_time: 结束时间，格式 YYYY-MM-DD HH:mm
        teacher_name: 老师姓名
        student_name: 学生姓名

    返回值:
        课程链接（ClassIn 跳转 URL）或 None
    """
    # TODO: 实现 ClassIn API 调用
    # payload = {
    #     "courseName": course_name,
    #     "startTime": start_time,
    #     "endTime": end_time,
    #     "teacherName": teacher_name,
    #     "studentName": student_name,
    # }
    # headers = {"Authorization": f"Bearer {_get_token()}"}
    # resp = requests.post(f"{CLASSIN_BASE_URL}/course/create", json=payload, headers=headers)
    # if resp.ok:
    #     data = resp.json()
    #     return data.get("courseUrl")
    return None


def get_class_session(classin_course_id: str) -> Optional[dict]:
    """查询 ClassIn 课程信息

    返回课程信息 dict，包含实际时长等

    参数:
        classin_course_id: ClassIn 课程 ID

    返回值:
        课程信息 dict 或 None
    """
    # TODO: 实现查询逻辑
    return None


def sync_actual_duration(classin_course_id: str) -> Optional[int]:
    """从 ClassIn 同步实际上课时长（分钟）

    参数:
        classin_course_id: ClassIn 课程 ID

    返回值:
        实际上课分钟数，或 None（无法获取）
    """
    session = get_class_session(classin_course_id)
    if session:
        return session.get("actual_duration_minutes")
    return None


def cancel_class_session(classin_course_id: str) -> bool:
    """取消 ClassIn 课程

    参数:
        classin_course_id: ClassIn 课程 ID

    返回值:
        是否成功
    """
    # TODO: 实现取消逻辑
    return False
