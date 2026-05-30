"""
HTTP 服务核心 — 路由、CORS、JWT 中间件、静态文件
纯 Python stdlib，模仿类 FastAPI 的路由注册方式
"""
import json
import os
import sys
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 确保 backend 目录在 sys.path 中
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from utils import json_response, error_response, parse_body, decode_token, ok_response, require_role
from router import _ROUTES, get, post
from db import init_db


# ── 静态文件 ──
FRONTEND_DIR = os.path.join(_BACKEND_DIR, "..", "frontend")
FRONTEND_DIR = os.path.realpath(FRONTEND_DIR)


class TMSHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[TMS] {args[0]} {args[1]}")

    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Session-Token")
        self.send_header("Access-Control-Max-Age", "86400")

    def _get_token_payload(self):
        auth_hdr = self.headers.get("Authorization", "")
        if auth_hdr.startswith("Bearer "):
            token = auth_hdr[7:]
        else:
            token = self.headers.get("X-Session-Token", "")
        return decode_token(token) if token else None

    def _handle_request(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query, keep_blank_values=True)

        if method == "OPTIONS":
            self.send_response(204)
            self._send_cors()
            self.end_headers()
            return

        # 初始化数据库
        try:
            init_db()
        except Exception as e:
            error_response(self, f"数据库初始化失败: {e}", 500)
            return

        # 查找路由
        for http_method, pattern, handler_fn, need_auth, allowed_roles in _ROUTES:
            if http_method != method:
                continue
            m = pattern.match(path)
            if m:
                token_payload = None
                if need_auth:
                    token_payload = self._get_token_payload()
                    if not token_payload:
                        error_response(self, "未登录或登录已过期", 401)
                        return
                    if not require_role(token_payload, allowed_roles):
                        error_response(self, "无权访问", 403)
                        return

                kwargs = m.groupdict()
                body = parse_body(self) if method in ("POST", "PUT", "DELETE") else {}
                try:
                    handler_fn(self, token_payload, qs, body, **kwargs)
                except Exception as e:
                    traceback.print_exc()
                    error_response(self, f"服务器错误: {e}", 500)
                return

        # 静态文件
        if method == "GET" and self._serve_static(path):
            return

        error_response(self, "接口不存在", 404)

    def _serve_static(self, path: str) -> bool:
        if path == "/":
            path = "/index.html"
        filepath = os.path.join(FRONTEND_DIR, path.lstrip("/"))
        real = os.path.realpath(filepath)
        if not real.startswith(os.path.realpath(FRONTEND_DIR)):
            return False
        if not os.path.isfile(real):
            return False

        ext_map = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }
        ext = os.path.splitext(real)[1].lower()
        ctype = ext_map.get(ext, "application/octet-stream")
        try:
            with open(real, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self._send_cors()
            self.end_headers()
            self.wfile.write(content)
            return True
        except OSError:
            return False

    def do_GET(self):    self._handle_request("GET")
    def do_POST(self):   self._handle_request("POST")
    def do_PUT(self):    self._handle_request("PUT")
    def do_DELETE(self): self._handle_request("DELETE")
    def do_OPTIONS(self): self._handle_request("OPTIONS")


def run_server(host="0.0.0.0", port=8766):
    init_db()

    # 注册 health 端点
    @get("/api/health", auth=False)
    def health(handler, tp, qs, body):
        json_response(handler, {"status": "ok", "version": "2.0.0"})

    # 导入并注册路由
    import auth  # noqa
    import leads  # noqa
    import users  # noqa
    import dashboard  # noqa
    import followups  # noqa
    import schedules  # noqa
    import contracts  # noqa
    import packages  # noqa
    import finance  # noqa
    import trials  # noqa
    import students  # noqa
    import teachers  # noqa
    import payments  # noqa
    import growth  # noqa
    import consulting  # noqa

    server = HTTPServer((host, port), TMSHandler)
    print(f"[TMS] 🚀 服务启动: http://{host}:{port}")
    print(f"[TMS] 📁 前端: {FRONTEND_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[TMS] 已停止")
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8766))
    run_server(port=port)
