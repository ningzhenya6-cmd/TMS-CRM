"""HTTP Server - serves the web UI and API endpoints using Python stdlib."""
import json
import os
import sys
import time
import secrets
import hashlib
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from http import HTTPStatus
from concurrent.futures import ThreadPoolExecutor, TimeoutError

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from knowledge.store import get_store
from knowledge.ai import ask_stream
from knowledge.risk import check_sensitive, BLOCKED_RESPONSES, DEFAULT_BLOCKED
from knowledge.risk import rate_limiter, health
from knowledge.pending_qa import add_pending, list_pending, get_pending
from knowledge.pending_qa import approve_pending, reject_pending
from knowledge.feedback import submit_vote, list_feedback, get_stats as get_feedback_stats, get_quality_analysis
from knowledge.user import get_or_create_user, increment_questions, get_user, update_user, get_stats as get_user_stats
from knowledge.user import register_user, login_user, get_user_by_name, check_daily_limit, increment_daily_usage
from knowledge.user import approve_user, set_user_status, get_pending_users
from knowledge.history import save_conversation, get_recent_messages, get_messages, get_sessions, admin_get_all_sessions, admin_get_session_count, delete_session as delete_chat_session
from knowledge.queries import log_query, get_hot_queries, get_query_stats as get_query_stats_report, get_zero_kb_queries
from knowledge.reports import get_daily_report, get_weekly_report
from knowledge.smart_add import parse_raw_text

_STATIC_BASE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.environ.get('AI_STATIC_DIR',
    os.path.join(_STATIC_BASE, "ai_static" if os.environ.get('AI_ENGINE_MODE') else "static"))

# ===== Admin auth (simple token-based) =====
# Set ADMIN_PASSWORD env var to enable password protection.
# If not set, admin pages are open (local dev mode).
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '').strip()

# In-memory token store: {token: expiry_timestamp}
_admin_tokens = {}

def _generate_admin_token():
    """Generate a random token valid for 24 hours."""
    token = secrets.token_hex(32)
    _admin_tokens[token] = time.time() + 86400  # 24h expiry
    # Clean expired tokens
    now = time.time()
    expired = [t for t, exp in _admin_tokens.items() if exp < now]
    for t in expired:
        _admin_tokens.pop(t, None)
    return token

def _check_admin_token(token):
    """Validate an admin token."""
    if not ADMIN_PASSWORD:
        return True  # No password set = open access
    if not token:
        return False
    expiry = _admin_tokens.get(token)
    if expiry is None:
        return False
    if time.time() > expiry:
        _admin_tokens.pop(token, None)
        return False
    return True

def _extract_token_from_request(handler):
    """Extract admin token from Cookie or Authorization header."""
    cookie = handler.headers.get('Cookie', '')
    for part in cookie.split(';'):
        part = part.strip()
        if part.startswith('admin_token='):
            return part.split('=', 1)[1]
    auth = handler.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    return None

# Admin-only API path prefixes
_ADMIN_API_PATHS = [
    '/api/analytics',
    '/api/knowledge',
    '/api/pending-qa',
    '/api/entries',
    '/api/admin/',
    '/api/quality',
    '/api/feedback/quality',
    '/api/queries/hot',
    '/api/queries/gaps',
    '/api/reports/',
    '/api/consult/list',
    '/api/user/stats',
    '/api/rebuild',
    '/api/stats',
    '/api/health',
    '/api/knowledge/smart-add',
    '/api/export/',
    '/api/import/',
]

def _is_admin_path(path):
    """Check if a path requires admin authentication."""
    for prefix in _ADMIN_API_PATHS:
        if path.startswith(prefix):
            return True
    # GET /api/feedback with ?downvoted=true is admin; POST is public
    if path == '/api/feedback' or path == '/api/categories':
        return True  # Both are admin-only for GET; POST already handled
    if path == '/api/chat/history' or path == '/api/admin/sessions' or path == '/api/admin/session/messages':
        return True
    return False


class KnowledgeHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the knowledge engine web UI."""

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path):
        if not path or path == '/':
            path = '/index.html'
        filepath = os.path.join(STATIC_DIR, path.lstrip('/'))

        # Security: prevent directory traversal
        real_path = os.path.realpath(filepath)
        if not real_path.startswith(os.path.realpath(STATIC_DIR)):
            self._send_json({"error": "Forbidden"}, 403)
            return

        if not os.path.exists(filepath) or os.path.isdir(filepath):
            self._send_json({"error": "Not Found"}, 404)
            return

        ext = os.path.splitext(filepath)[1].lower()
        mime_map = {
            '.html': 'text/html; charset=utf-8',
            '.css': 'text/css; charset=utf-8',
            '.js': 'application/javascript; charset=utf-8',
            '.json': 'application/json; charset=utf-8',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.svg': 'image/svg+xml',
        }
        content_type = mime_map.get(ext, 'application/octet-stream')

        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except:
            self._send_json({"error": "Internal Server Error"}, 500)

    def do_GET(self):
        import time as _time
        self._request_start = _time.time()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        # Admin auth check
        if ADMIN_PASSWORD and _is_admin_path(path):
            token = _extract_token_from_request(self)
            if not _check_admin_token(token):
                self._send_json({"error": "unauthorized", "message": "需要管理员权限，请先登录"}, 401)
                return

        # API routes
        if path == '/api/search':
            query = params.get('q', [''])[0]
            if not query:
                self._send_json({"results": []})
                return
            store = get_store()
            results = store.search(query, top_k=5)
            self._send_json({
                "results": [
                    {"title": e['title'], "content": e['content'][:300],
                     "category": e.get('category', ''), "tags": e.get('tags', []),
                     "score": round(s, 4)}
                    for e, s in results
                ]
            })

        elif path == '/api/knowledge':
            store = get_store()
            cat = params.get('category', [None])[0]
            search_q = params.get('q', [None])[0]
            page = int(params.get('page', ['1'])[0])
            page_size = int(params.get('page_size', ['50'])[0])
            entries = store.get_all_entries()
            if cat:
                entries = [e for e in entries if e.get('category') == cat]
            if search_q:
                sq = search_q.lower()
                entries = [e for e in entries if sq in e.get('title', '').lower() or sq in e.get('content', '').lower() or sq in ' '.join(e.get('tags', [])).lower()]
            total = len(entries)
            # Paginate
            start = (page - 1) * page_size
            entries = entries[start:start + page_size]
            self._send_json({
                "entries": entries,
                "total": total,
                "page": page,
                "page_size": page_size,
                "stats": store.get_stats()
            })

        elif path == '/api/categories':
            store = get_store()
            self._send_json({"categories": store.get_categories()})

        elif path == '/api/export/entries':
            """导出全部知识条目为JSON（管理员用）"""
            store = get_store()
            entries = store.get_all_entries()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Disposition', 'attachment; filename="knowledge-export.json"')
            self.end_headers()
            export_data = {
                "total": len(entries),
                "active": sum(1 for e in entries if e.get("is_active", True)),
                "stats": store.get_stats(),
                "entries": entries,
                "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            body = json.dumps(export_data, ensure_ascii=False, indent=2).encode('utf-8')
            self.wfile.write(body)

        elif path == '/api/stats':
            store = get_store()
            self._send_json(store.get_stats())

        elif path == '/api/health':
            stats = health.status()
            try:
                from knowledge.store import get_db as get_kb_db
                db = get_kb_db()
                has_hist = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'").fetchone()
                msg_count = db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] if has_hist else 0
                has_users = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
                user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] if has_users else 0
            except Exception:
                msg_count = user_count = 0
            stats.update({"messages_total": msg_count, "users_total": user_count})
            self._send_json(stats)

        elif path == '/api/chat/history':
            token = params.get('token', [None])[0]
            session_id = params.get('session_id', [None])[0]
            if not token:
                self._send_json({"messages": [], "sessions": []})
                return
            user, _ = get_or_create_user(token)
            sessions = get_sessions(user['id'], limit=20)
            if session_id:
                messages = get_messages(session_id, limit=200)
            else:
                messages = get_recent_messages(user['id'], max_messages=50)
            self._send_json({"messages": messages, "sessions": sessions})

        elif path == '/api/auth/check':
            """检查 token 是否有效，返回用户信息"""
            token = params.get('token', [None])[0]
            if not token:
                self._send_json({"valid": False})
                return
            user, _ = get_or_create_user(token)
            self._send_json({
                "valid": True,
                "user": {
                    "id": user["id"],
                    "name": user.get("name", ""),
                    "role": user.get("role", "student"),
                    "status": user.get("status", "active"),
                },
                "token": token,
            })

        elif path == '/api/user/sessions':
            """获取用户的会话列表"""
            token = params.get('token', [None])[0]
            if not token:
                self._send_json({"sessions": []})
                return
            user, _ = get_or_create_user(token)
            sessions = get_sessions(user['id'], limit=50)
            self._send_json({"sessions": sessions})

        elif path == '/api/user/session/messages':
            """获取指定会话的消息"""
            token = params.get('token', [None])[0]
            session_id = params.get('session_id', [None])[0]
            if not token or not session_id:
                self._send_json({"messages": []})
                return
            messages = get_messages(session_id, limit=200)
            self._send_json({"messages": messages})

        elif path == '/api/admin/pending-users':
            """管理员：获取待审核用户列表"""
            users = get_pending_users()
            self._send_json({"users": users})

        elif path == '/api/chat' or path == '/api/ask':
            query = params.get('q', [''])[0]
            if not query:
                self._send_json({"answer": "请输入您的问题"})
                return
            store = get_store()
            kb_results = store.search(query, top_k=5)

            # Web search for school/program queries
            from knowledge.ai import _query_needs_web_search
            web_results = None
            if _query_needs_web_search(query) or not kb_results:
                try:
                    from knowledge.web_search import search_web
                    web_results = search_web(query, max_results=3)
                except Exception:
                    web_results = None

            from knowledge.ai import ask_deepseek
            # Build context with KB + Web
            context_parts = []
            for e, _ in kb_results:
                context_parts.append(f"[案例库] {e['title']}: {e['content'][:300]}")
            if web_results:
                for r in web_results:
                    context_parts.append(f"[网络搜索] {r['title']}: {r['snippet'][:300]}")
            context = "\n".join(context_parts)

            messages = [
                {"role": "system", "content": "你是一位资深的留学生课业规划顾问。请在回答中标注信息来源：【案例库】或【网络搜索】。"},
                {"role": "user", "content": f"参考信息：\n{context}\n\n用户问题：{query}"}
            ]
            answer = ask_deepseek(messages)
            all_sources = [e['title'] for e, _ in kb_results]
            if web_results:
                all_sources.extend([f"[网络] {r['title'][:40]}" for r in web_results])
            self._send_json({"answer": answer, "sources": all_sources})

        elif path == '/api/consult/list':
            from knowledge.store import get_db as get_kb_db
            db = get_kb_db()
            try:
                rows = db.execute("SELECT * FROM consultations ORDER BY created_at DESC").fetchall()
                submissions = [dict(r) for r in rows]
            except Exception:
                submissions = []
            self._send_json({"submissions": submissions})

        elif path == '/api/pending-qa':
            pqa_id = params.get('id', [None])[0]
            if pqa_id:
                entry = get_pending(pqa_id)
                if entry:
                    self._send_json({"entry": entry})
                else:
                    self._send_json({"error": "not found"}, 404)
            else:
                entries = list_pending()
                self._send_json({"entries": entries, "count": len(entries)})

        elif path == '/api/user/stats':
            self._send_json(get_user_stats())

        elif path == '/api/feedback':
            only_downvoted = params.get('downvoted', [None])[0] == 'true'
            entries = list_feedback(only_downvoted=only_downvoted)
            self._send_json({"entries": entries, "count": len(entries)})

        elif path == '/api/feedback/quality':
            analysis = get_quality_analysis()
            self._send_json(analysis)

        elif path == '/api/admin/sessions':
            limit = int(params.get('limit', ['100'])[0])
            sessions = admin_get_all_sessions(limit=limit)
            total = admin_get_session_count()
            self._send_json({"sessions": sessions, "total": total})

        elif path == '/api/admin/session/messages':
            session_id = params.get('id', [''])[0]
            if not session_id:
                self._send_json({"error": "no session id"}, 400)
                return
            msg_list = get_messages(session_id, limit=200)
            self._send_json({"messages": msg_list, "count": len(msg_list)})

        elif path == '/api/analytics':
            store = get_store()
            store_stats = store.get_stats() if hasattr(store, 'get_stats') else {}
            try:
                from knowledge.store import get_db as get_kb_db
                db = get_kb_db()
                has_table = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='consultations'").fetchone()
                con_count = db.execute("SELECT COUNT(*) FROM consultations").fetchone()[0] if has_table else 0
                has_hist = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'").fetchone()
                history_count = db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] if has_hist else 0
                has_users = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
                user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] if has_users else 0
            except Exception:
                con_count = history_count = user_count = 0
            pending_list = list_pending()
            pending_count = len(pending_list) if pending_list else 0
            user_stats_raw = get_user_stats()
            feedback_stats = get_feedback_stats()
            query_stats = get_query_stats_report(7)
            hot_questions = get_hot_queries(10, 7)
            gap_count = len(get_zero_kb_queries(9999))
            self._send_json({
                "knowledge": store_stats,
                "pending_qa": {"count": pending_count},
                "users": user_stats_raw,
                "consultations": {"count": con_count},
                "chat_messages": {"total": history_count},
                "feedback": feedback_stats,
                "queries": query_stats,
                "hot_questions": hot_questions,
                "knowledge_gaps": {"count": gap_count},
            })

        elif path == '/api/queries/hot':
            days = int(params.get('days', ['7'])[0])
            limit = int(params.get('limit', ['20'])[0])
            hot = get_hot_queries(limit, days)
            stats = get_query_stats_report(days)
            self._send_json({"hot": hot, "stats": stats})

        elif path == '/api/queries/gaps':
            limit = int(params.get('limit', ['50'])[0])
            gaps = get_zero_kb_queries(limit)
            self._send_json({"gaps": gaps, "count": len(gaps)})

        elif path == '/api/reports/daily':
            report = get_daily_report()
            self._send_json(report)

        elif path == '/api/reports/weekly':
            report = get_weekly_report()
            self._send_json(report)

        elif path == '/api/admin/login':
            """Check if user is logged in (GET). Returns status."""
            if not ADMIN_PASSWORD:
                self._send_json({"authenticated": True, "message": "无需密码（本地模式）"})
                return
            token = _extract_token_from_request(self)
            ok = _check_admin_token(token)
            self._send_json({"authenticated": ok})

        elif path == '/api/leads/list':
            import json as _json_leads2
            try:
                leads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'leads')
                os.makedirs(leads_dir, exist_ok=True)
                all_leads = []
                for fname in sorted(os.listdir(leads_dir)):
                    if fname.endswith('.jsonl'):
                        fpath = os.path.join(leads_dir, fname)
                        try:
                            with open(fpath, 'r', encoding='utf-8') as f:
                                for line in f:
                                    line = line.strip()
                                    if line:
                                        try:
                                            all_leads.append(_json_leads2.loads(line))
                                        except:
                                            pass
                        except:
                            pass
                self._send_json({'leads': all_leads, 'count': len(all_leads)})
            except Exception as e:
                self._send_json({'error': str(e)}, 500)
        else:
            # Serve static files (including index.html for all unmatched routes)
            self._serve_static(path)

    def do_POST(self):
        import time as _time
        self._request_start = _time.time()
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'

        try:
            data = json.loads(body)
        except:
            data = {}

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Admin login is always public
        if path == '/api/admin/login':
            if not ADMIN_PASSWORD:
                self._send_json({"authenticated": True, "token": "", "message": "无需密码（本地模式）"})
                return
            pwd = data.get('password', '')
            if pwd == ADMIN_PASSWORD:
                token = _generate_admin_token()
                self._send_json({"authenticated": True, "token": token})
            else:
                self._send_json({"authenticated": False, "error": "密码错误"}, 401)
            return

        # Admin auth check for protected POST endpoints
        if ADMIN_PASSWORD and _is_admin_path(path):
            token = _extract_token_from_request(self)
            if not _check_admin_token(token):
                self._send_json({"error": "unauthorized", "message": "需要管理员权限，请先登录"}, 401)
                return

        # ===== Auth & Session Management =====
        if path == '/api/auth/register':
            name = data.get('name', '').strip()
            password = data.get('password', '').strip()
            if not name or not password:
                self._send_json({"error": "用户名和密码不能为空"}, 400)
                return
            result = register_user(name, password)
            if "error" in result:
                self._send_json(result, 409)
            else:
                self._send_json(result)

        elif path == '/api/auth/login':
            name = data.get('name', '').strip()
            password = data.get('password', '').strip()
            if not name or not password:
                self._send_json({"error": "用户名和密码不能为空"}, 400)
                return
            result = login_user(name, password)
            if "error" in result:
                self._send_json(result, 401)
            else:
                self._send_json(result)

        elif path == '/api/user/sessions':
            """创建新会话"""
            token = data.get('token', '')
            title = data.get('title', '新对话')
            if not token:
                self._send_json({"error": "需要登录"}, 401)
                return
            user, _ = get_or_create_user(token)
            from knowledge.history import create_session
            session_id = create_session(user["id"])
            # 设置标题
            if title != '新对话':
                from knowledge.store import get_db as get_kb_db
                db = get_kb_db()
                db.execute("UPDATE chat_sessions SET title = ? WHERE id = ?", (title, session_id))
                db.commit()
            self._send_json({"session_id": session_id})

        elif path == '/api/user/session/delete':
            """用户删除自己的会话"""
            token = data.get('token', '')
            session_id = data.get('id', '')
            if not token or not session_id:
                self._send_json({"error": "参数不完整"}, 400)
                return
            user, _ = get_or_create_user(token)
            if not user:
                self._send_json({"error": "用户未找到"}, 401)
                return
            from knowledge.store import get_db as get_kb_db
            db = get_kb_db()
            row = db.execute("SELECT user_id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                self._send_json({"error": "会话不存在"}, 404)
                return
            if row["user_id"] != user["id"]:
                self._send_json({"error": "无权删除此会话"}, 403)
                return
            delete_chat_session(session_id)
            self._send_json({"status": "ok"})

        elif path == '/api/admin/user/approve':
            """管理员审核通过用户"""
            user_id = data.get('user_id', '')
            daily_limit = int(data.get('daily_limit', 50))
            if not user_id:
                self._send_json({"error": "缺少 user_id"}, 400)
                return
            approve_user(user_id, daily_limit)
            self._send_json({"status": "ok"})

        elif path == '/api/admin/user/disable':
            """管理员禁用/启用用户"""
            user_id = data.get('user_id', '')
            status = data.get('status', 'disabled')
            daily_limit = data.get('daily_limit', None)
            if not user_id:
                self._send_json({"error": "缺少 user_id"}, 400)
                return
            set_user_status(user_id, status, daily_limit)
            self._send_json({"status": "ok"})

        # ===== Chat Endpoint =====
        elif path == '/api/chat':
            query = data.get('question', '').strip()
            if not query:
                self._send_json({"answer": "请输入您的问题"})
                return

            # --- 用户识别 ---
            user_token = data.get('user_token', '')
            user, token = get_or_create_user(user_token)
            user_role = user.get('role', 'student')
            user_status = user.get('status', 'active')
            session_id = data.get('session_id', '')

            # --- 状态检查：被禁用用户 ---
            if user_status == 'disabled':
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                err_msg = "您的账号已被禁用，请联系管理员。"
                self.wfile.write(f"data: {json.dumps({'type':'blocked','data':{'reason':'disabled','message':err_msg}})}\n\n".encode('utf-8'))
                self.wfile.write(f"data: {json.dumps({'type':'done'})}\n\n".encode('utf-8'))
                self.wfile.flush()
                return

            # --- 每日限额检查 ---
            limit_check = check_daily_limit(user['id'])
            if not limit_check['allowed']:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                err_msg = f"您今天的提问次数已达上限（{limit_check['limit']}次），明天再来吧！"
                self.wfile.write(f"data: {json.dumps({'type':'blocked','data':{'reason':'daily_limit','message':err_msg}})}\n\n".encode('utf-8'))
                self.wfile.write(f"data: {json.dumps({'type':'done'})}\n\n".encode('utf-8'))
                self.wfile.flush()
                return

            # --- 风险控制：速率限制 ---
            client_ip = self.client_address[0]
            allowed, remaining, reset_sec = rate_limiter.check(client_ip)
            if not allowed:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                err_msg = f"请求过于频繁，请在 {reset_sec} 秒后重试。"
                self.wfile.write(f"data: {json.dumps({'type':'blocked','data':{'reason':'rate_limit','message':err_msg}})}\n\n".encode('utf-8'))
                self.wfile.write(f"data: {json.dumps({'type':'done'})}\n\n".encode('utf-8'))
                self.wfile.flush()
                health.record_request(blocked=True)
                return

            # --- 风险控制：敏感内容检测 ---
            is_sensitive, category, matched = check_sensitive(query)
            # Also check conversation history
            if not is_sensitive:
                history_text = data.get('messages', [])
                if isinstance(history_text, list):
                    for m in history_text[-3:]:  # check recent 3
                        if isinstance(m, dict):
                            c = m.get('content', '')
                            if c and check_sensitive(c)[0]:
                                is_sensitive, category = True, 'harassment'
                                break

            if is_sensitive:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                reply_msg = BLOCKED_RESPONSES.get(category, DEFAULT_BLOCKED)
                self.wfile.write(f"data: {json.dumps({'type':'blocked','data':{'reason':category,'message':reply_msg}})}\n\n".encode('utf-8'))
                self.wfile.write(f"data: {json.dumps({'type':'done'})}\n\n".encode('utf-8'))
                self.wfile.flush()
                health.record_request(blocked=True)
                return

            health.record_request()

            # Start streaming response
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('X-Accel-Buffering', 'no')
            self.end_headers()

            # Phase 1: Search knowledge base
            store = get_store()
            kb_results = store.search(query, top_k=5)
            kb_sources = [e['title'] for e, _ in kb_results]

            # Phase 2: Check if web search is needed (school/program specific query)
            from knowledge.ai import _query_needs_web_search
            web_results = None
            if _query_needs_web_search(query) or not kb_results:
                # Run web search concurrently with a 3s timeout — never block the AI response
                try:
                    from knowledge.web_search import search_web
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        fut = pool.submit(search_web, query, 5)
                        web_results = fut.result(timeout=3)
                except TimeoutError:
                    web_results = None  # Proceed without web results
                except Exception:
                    web_results = None

            # Send user info
            limit_check = check_daily_limit(user['id'])
            user_msg = json.dumps({
                "type": "user",
                "data": {
                    "token": token,
                    "role": user_role,
                    "status": user_status,
                    "daily_used": limit_check['used'],
                    "daily_limit": limit_check['limit'],
                }
            }, ensure_ascii=False)
            self.wfile.write(f"data: {user_msg}\n\n".encode('utf-8'))
            self.wfile.flush()

            # Send sources (KB + Web) with content snippets
            source_info = []
            follow_ups = []
            for e, _ in kb_results:
                source_info.append({
                    "title": e['title'],
                    "category": e.get('category', ''),
                    "snippet": e.get('content', '')[:400],
                    "type": "kb",
                    "tags": e.get('tags', []),
                })
                # Collect related questions from top 2 results
                if len(follow_ups) < 6:
                    for rq in e.get('related_questions', []):
                        if rq and len(follow_ups) < 6:
                            follow_ups.append(rq)
            if web_results:
                for r in web_results:
                    source_info.append({
                        "title": r.get('title', ''),
                        "snippet": r.get('snippet', '')[:400],
                        "url": r.get('url', ''),
                        "type": "web"
                    })
            source_msg = json.dumps({
                "type": "sources",
                "data": source_info,
                "follow_ups": follow_ups,
            }, ensure_ascii=False)
            self.wfile.write(f"data: {source_msg}\n\n".encode('utf-8'))
            self.wfile.flush()

            # Phase 3: Generate answer with hybrid context
            _answer_buffer = []

            def on_chunk(text):
                _answer_buffer.append(text)
                msg = json.dumps({"type": "chunk", "data": text}, ensure_ascii=False)
                self.wfile.write(f"data: {msg}\n\n".encode('utf-8'))
                self.wfile.flush()

            # Collect conversation history for multi-turn support
            history = data.get('messages', [])
            if not isinstance(history, list):
                history = []

            if history:
                from knowledge.ai import ask_stream_with_history
                ask_stream_with_history(query, [{'entry': e} for e, _ in kb_results],
                                        web_results=web_results, history=history,
                                        on_chunk=on_chunk, user_role=user_role)
            else:
                ask_stream(query, [{'entry': e} for e, _ in kb_results],
                           web_results=web_results, on_chunk=on_chunk, user_role=user_role)

            # End stream
            end_msg = json.dumps({"type": "done"}, ensure_ascii=False)
            self.wfile.write(f"data: {end_msg}\n\n".encode('utf-8'))
            self.wfile.flush()

            # Phase 4: Track user activity + auto-log Q&A + save history
            if _answer_buffer:
                try:
                    increment_questions(user['id'])
                    add_pending(query, ''.join(_answer_buffer), source_info)
                    full_history = data.get('messages', [])
                    if not isinstance(full_history, list):
                        full_history = []
                    full_history.append({"role": "user", "content": query})
                    full_history.append({"role": "assistant", "content": ''.join(_answer_buffer)})
                    # 如果指定了 session_id，使用指定会话；否则用默认的
                    if session_id:
                        from knowledge.history import add_message, get_messages
                        add_message(session_id, "user", query)
                        add_message(session_id, "assistant", ''.join(_answer_buffer))
                    else:
                        save_conversation(user['id'], full_history)
                    increment_daily_usage(user['id'])
                    log_query(query, kb_count=len(kb_results), web_search=web_results is not None, user_token=token)
                except Exception:
                    pass  # Silent fail - never break chat for logging

        elif path == '/api/knowledge/add':
            entry = {
                'title': data.get('title', ''),
                'content': data.get('content', ''),
                'category': data.get('category', 'general'),
                'tags': data.get('tags', []),
                'related_questions': data.get('related_questions', []),
            }
            store = get_store()
            eid = store.add_entry(entry)
            store.save()
            self._send_json({"id": eid, "status": "ok"})

        elif path == '/api/knowledge/update':
            eid = data.get('id', '')
            if not eid:
                self._send_json({"error": "no id"}, 400)
                return
            store = get_store()
            entry = store.get_entry(eid)
            if not entry:
                self._send_json({"error": "not found"}, 404)
                return
            updates = {}
            for key in ('title', 'content', 'category', 'tags', 'related_questions', 'is_active'):
                if key in data:
                    updates[key] = data[key]
            if updates:
                store.update_entry(eid, updates)
                store.save()
            self._send_json({"status": "ok"})

        elif path == '/api/knowledge/batch-import':
            entries = data.get('entries', [])
            if not entries:
                self._send_json({"error": "no entries"}, 400)
                return
            store = get_store()
            count_before = len(store.entries)
            for e in entries:
                if e.get('title') or e.get('content'):
                    store.add_entry({
                        'title': e.get('title', ''),
                        'content': e.get('content', ''),
                        'category': e.get('category', 'general'),
                        'tags': e.get('tags', []),
                        'related_questions': e.get('related_questions', []),
                    })
            store.save()
            count_after = len(store.entries)
            self._send_json({"status": "ok", "added": count_after - count_before, "total": count_after})

        elif path == '/api/knowledge/smart-add':
            action = data.get('action', 'parse')
            raw_text = data.get('text', '').strip()
            if not raw_text:
                self._send_json({"error": "请输入辅导记录文本"}, 400)
                return

            if action == 'parse':
                # AI parse the raw text
                result = parse_raw_text(raw_text)
                if 'error' in result:
                    self._send_json({"error": result['error']}, 500)
                    return
                self._send_json({"status": "ok", "preview": result})

            elif action == 'save':
                # Save the confirmed entry
                entry = {
                    'title': data.get('title', ''),
                    'content': data.get('content', ''),
                    'category': data.get('category', 'general'),
                    'tags': data.get('tags', []),
                    'related_questions': data.get('related_questions', []),
                }
                if not entry.get('title') or not entry.get('content'):
                    self._send_json({"error": "标题和内容不能为空"}, 400)
                    return
                store = get_store()
                eid = store.add_entry(entry)
                store.save()
                self._send_json({"status": "ok", "id": eid, "message": "已入库"})
            else:
                self._send_json({"error": "未知操作"}, 400)

        elif path == '/api/knowledge/delete':
            eid = data.get('id', '')
            if eid:
                store = get_store()
                store.delete_entry(eid)
                store.save()
                self._send_json({"status": "ok"})
            else:
                self._send_json({"error": "no id"}, 400)

        elif path == '/api/rebuild':
            store = get_store()
            store._build_index()
            store.save()
            self._send_json({"status": "ok", "stats": store.get_stats()})

        elif path == '/api/import/categories':
            """导入分类映射：更新知识条目的分类、标签和活跃状态"""
            updates = data
            if not isinstance(updates, list):
                self._send_json({"status": "error", "message": "需要提供更新列表"}, 400)
                return
            from knowledge.store import get_db as get_kb_db, _rebuild_fts5
            db = get_kb_db()
            updated = 0
            for item in updates:
                eid = item.get("id", "")
                if not eid:
                    continue
                category = item.get("category", "general")
                tags = json.dumps(item.get("tags", []), ensure_ascii=False)
                is_active = item.get("is_active", 1)
                db.execute(
                    "UPDATE entries SET category=?, tags=?, is_active=? WHERE id=?",
                    (category, tags, is_active, eid)
                )
                updated += 1
            db.commit()
            # 刷新 store 缓存（重置全局store）
            import knowledge.store as ks
            ks._store = None
            # 重建FTS索引
            fresh = ks.get_store()
            fresh._build_index()
            ks._rebuild_fts5(fresh.entries)
            self._send_json({"status": "ok", "updated": updated, "stats": fresh.get_stats()})

        elif path == '/api/import/apply-mapping':
            """从本地 deploy/category_mapping.json 读取并应用分类映射"""
            mapping_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "category_mapping.json")
            if not os.path.exists(mapping_path):
                self._send_json({"status": "error", "message": "映射文件不存在"})
                return
            with open(mapping_path, "r", encoding="utf-8") as f:
                updates = json.load(f)
            from knowledge.store import get_db as get_kb_db, _rebuild_fts5
            db = get_kb_db()
            updated = 0
            for item in updates:
                eid = item.get("id", "")
                if not eid:
                    continue
                category = item.get("category", "general")
                tags = json.dumps(item.get("tags", []), ensure_ascii=False)
                is_active = item.get("is_active", 1)
                db.execute(
                    "UPDATE entries SET category=?, tags=?, is_active=? WHERE id=?",
                    (category, tags, is_active, eid)
                )
                updated += 1
            db.commit()
            import knowledge.store as ks
            ks._store = None
            fresh = ks.get_store()
            fresh._build_index()
            ks._rebuild_fts5(fresh.entries)
            self._send_json({"status": "ok", "updated": updated, "stats": fresh.get_stats()})

        elif path == '/api/consult':
            name = data.get('name', '').strip()
            wechat = data.get('wechat', '').strip()
            if not name or not wechat:
                self._send_json({"status": "error", "message": "姓名和微信号为必填"}, 400)
                return
            from knowledge.store import get_db as get_kb_db
            from datetime import datetime
            db = get_kb_db()
            try:
                db.execute(
                    "INSERT INTO consultations (id, name, wechat, role, question, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"c{int(time.time())}",
                        name, wechat,
                        data.get('role', ''),
                        data.get('question', ''),
                        'new',
                        datetime.now().strftime('%Y-%m-%d %H:%M'),
                    ),
                )
                db.commit()
            except Exception:
                db.rollback()
                # Create table if not exists and retry
                db.execute("""
                    CREATE TABLE IF NOT EXISTS consultations (
                        id TEXT PRIMARY KEY, name TEXT, wechat TEXT,
                        role TEXT, question TEXT, status TEXT, created_at TEXT
                    )
                """)
                db.execute(
                    "INSERT INTO consultations VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f"c{int(time.time())}", name, wechat,
                     data.get('role', ''), data.get('question', ''), 'new',
                     datetime.now().strftime('%Y-%m-%d %H:%M')),
                )
                db.commit()
            self._send_json({"status": "ok"})

        elif path == '/api/pending-qa/approve':
            pqa_id = data.get('id', '')
            if not pqa_id:
                self._send_json({"error": "no id"}, 400)
                return
            edits = {
                'title': data.get('title', ''),
                'category': data.get('category', 'user-qa'),
                'tags': data.get('tags', []),
                'content': data.get('content', ''),
            }
            if approve_pending(pqa_id, edits):
                self._send_json({"status": "ok"})
            else:
                self._send_json({"error": "not found"}, 404)

        elif path == '/api/pending-qa/reject':
            pqa_id = data.get('id', '')
            if not pqa_id:
                self._send_json({"error": "no id"}, 400)
                return
            if reject_pending(pqa_id):
                self._send_json({"status": "ok"})
            else:
                self._send_json({"error": "not found"}, 404)

        elif path == '/api/pending-qa/add':
            question = data.get('question', '')
            answer = data.get('answer', '')
            sources = data.get('sources', [])
            if not question or not answer:
                self._send_json({"error": "missing question or answer"}, 400)
            else:
                eid, status = add_pending(question, answer, sources)
                self._send_json({"status": "ok" if status != "skipped" else "skipped", "entry_id": eid, "entry_status": status})

        elif path == '/api/user/session':
            token = data.get('token', '')
            user, new_token = get_or_create_user(token)
            self._send_json({
                "user": {"id": user["id"], "name": user.get("name", ""), "role": user.get("role", "student")},
                "token": new_token,
            })

        elif path == '/api/user/update':
            token = data.get('token', '')
            user, _ = get_or_create_user(token)
            updates = {}
            if 'name' in data:
                updates['name'] = data['name']
            if 'role' in data:
                updates['role'] = data['role']
            if updates:
                update_user(user['id'], updates)
            self._send_json({"status": "ok"})

        elif path == '/api/feedback':
            message_id = data.get('message_id', '')
            question = data.get('question', '')
            answer = data.get('answer', '')
            vote = data.get('vote', '')
            user_token = data.get('user_token', '')
            if not message_id or vote not in ('up', 'down'):
                self._send_json({"error": "invalid parameters"}, 400)
            else:
                result = submit_vote(message_id, question, answer, vote, user_token)
                self._send_json({"status": "ok", "result": result})

        elif path == '/api/admin/session/delete':
            session_id = data.get('id', '')
            if not session_id:
                self._send_json({"error": "no id"}, 400)
            else:
                delete_chat_session(session_id)
                self._send_json({"status": "ok"})

        elif path == '/api/trigger-export':
            """手动触发数据导出（管理员用）"""
            try:
                import subprocess
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                result = subprocess.run(
                    [sys.executable, os.path.join(project_root, 'deploy', 'export_data.py')],
                    capture_output=True, text=True, timeout=30
                )
                self._send_json({
                    "status": "ok",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                })
            except Exception as e:
                self._send_json({"status": "error", "error": str(e)}, 500)

        elif path == '/api/leads':
            import json as _json_leads
            try:
                # data is already parsed by do_POST at the top
                lead = dict(data) if isinstance(data, dict) else {}
                lead['_server_time'] = __import__('time').strftime('%Y-%m-%d %H:%M:%S')
                leads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'leads')
                os.makedirs(leads_dir, exist_ok=True)
                date_str = __import__('time').strftime('%Y-%m-%d')
                filepath = os.path.join(leads_dir, f'{date_str}.jsonl')
                with open(filepath, 'a', encoding='utf-8') as f:
                    f.write(_json_leads.dumps(lead, ensure_ascii=False) + '\n')
                self._send_json({"status": "ok", "id": lead.get("id", "")})
            except Exception as e:
                try:
                    self._send_json({"error": str(e)}, 500)
                except:
                    pass

        else:
            self._send_json({"error": "Not Found"}, 404)

    def log_message(self, format, *args):
        """Quiet logging with request duration."""
        if '/api/' in str(args[0]):
            import time as _time
            duration = _time.time() - getattr(self, '_request_start', _time.time())
            print(f"[API] {args[0]} - {args[1]} {args[2]} ({duration:.2f}s)")


def run_server(host='0.0.0.0', port=8765):
    server = HTTPServer((host, port), KnowledgeHandler)
    print(f"\n{'='*50}")
    print(f"  留学课业AI知识引擎 已启动")
    print(f"  访问地址: http://localhost:{port}")
    print(f"  API 文档: http://localhost:{port}/api/chat")
    if ADMIN_PASSWORD:
        print(f"  管理员密码: 已开启 (通过 ADMIN_PASSWORD 环境变量设置)")
    else:
        print(f"  管理员密码: 未设置（公网部署建议设置 ADMIN_PASSWORD）")
    print(f"{'='*50}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8899))
    run_server(port=port)
