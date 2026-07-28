"""
作业上传 API — 上传/查看/下载学生课后作业文件
"""
import logging
import os
import json
import uuid
import re
from router import get, post
from utils import ok_response, error_response, add_oplog
from db import query, query_one, execute, execute_lastrowid

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@get("/api/leads/{lead_id}/homework")
def list_homework(handler, token_payload, qs, body, lead_id=None):
    lid = int(lead_id)
    files = query(
        "SELECT h.*, u.display_name as uploader_name FROM homework_uploads h LEFT JOIN users u ON h.uploaded_by=u.id WHERE h.lead_id=? ORDER BY h.created_at DESC",
        (lid,),
    )
    ok_response(handler, files)


@post("/api/leads/{lead_id}/homework")
def upload_homework(handler, token_payload, qs, body, lead_id=None):
    """上传作业文件（快速模式）"""
    lid = int(lead_id)
    user_id = token_payload["sub"]

    ct = handler.headers.get("Content-Type", "")
    cl = int(handler.headers.get("Content-Length", 0) or 0)
    if cl == 0:
        error_response(handler, "文件内容为空", 400)
        return

    # 读取原始数据
    # 分块读取确保完整获取
    raw = b""
    remaining = cl
    while remaining > 0:
        chunk = handler.rfile.read(min(65536, remaining))
        if not chunk:
            break
        raw += chunk
        remaining -= len(chunk)

    file_name = f"upload_{uuid.uuid4().hex[:12]}.bin"
    file_data = raw

    # 从 multipart 中快速提取文件名和数据
    if "multipart/form-data" in ct:
        try:
            # 提取 boundary
            b = ct.split("boundary=")[1].strip().encode()
            # 找到第一个文件 part
            start = raw.find(b'filename="')
            if start > 0:
                end = raw.find(b'"', start + 10)
                file_name = raw[start + 10:end].decode("utf-8", errors="ignore")
            # 找文件内容：第一个 part 的 \r\n\r\n 之后
            hdr_end = raw.find(b"\r\n\r\n")
            if hdr_end > 0:
                # 数据从 header 之后到 boundary 结束之前
                data_start = hdr_end + 4
                data_end = raw.find(b"\r\n--" + b, data_start)
                if data_end > data_start:
                    file_data = raw[data_start:data_end]
                else:
                    file_data = raw[data_start:]
        except Exception as e:
            logger.error('Multipart parsing failed for homework upload, falling back to raw data', extra={'error': str(e), 'content_type': ct})
            file_data = raw

    # 直接保存
    unique_name = f"{uuid.uuid4().hex}_{file_name}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)
    try:
        with open(file_path, "wb") as f:
            f.write(file_data)
    except Exception as e:
        error_response(handler, f"保存文件失败: {e}", 500)
        return

    file_size = len(file_data)

    file_id = execute_lastrowid(
        "INSERT INTO homework_uploads (lead_id, file_name, file_size, file_path, uploaded_by) VALUES (?,?,?,?,?)",
        (lid, file_name, file_size, file_path, user_id),
    )

    add_oplog(user_id, token_payload.get("name", ""), "upload", "homework", file_id,
              f"上传作业: {file_name}", json.dumps({"lead_id": lid, "size": file_size}, ensure_ascii=False))

    row = query_one("SELECT h.*, u.display_name as uploader_name FROM homework_uploads h LEFT JOIN users u ON h.uploaded_by=u.id WHERE h.id=?", (file_id,))
    ok_response(handler, row, 201)


@get("/api/homework/{file_id}/delete")
def delete_homework(handler, token_payload, qs, body, file_id=None):
    """删除作业文件"""
    row = query_one("SELECT * FROM homework_uploads WHERE id=?", (int(file_id),))
    if not row:
        error_response(handler, "文件不存在", 404)
        return
    # 删除磁盘文件
    fp = row["file_path"]
    if os.path.exists(fp):
        try:
            os.remove(fp)
        except Exception as e:
            logger.error('Failed to delete homework file from disk', extra={'error': str(e), 'file_path': fp})
    execute("DELETE FROM homework_uploads WHERE id=?", (int(file_id),))
    add_oplog(token_payload["sub"], token_payload.get("name",""), "delete", "homework", int(file_id), f"删除作业: {row['file_name']}")
    ok_response(handler, {"message": "已删除"})


@get("/api/homework/{file_id}/download")
def download_homework(handler, token_payload, qs, body, file_id=None):
    row = query_one("SELECT * FROM homework_uploads WHERE id=?", (int(file_id),))
    if not row:
        error_response(handler, "文件不存在", 404)
        return
    file_path = row["file_path"]
    if not os.path.exists(file_path):
        error_response(handler, "文件已被删除", 404)
        return
    with open(file_path, "rb") as f:
        data = f.read()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/octet-stream")
    handler.send_header("Content-Disposition", f'attachment; filename="{row["file_name"]}"')
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)
