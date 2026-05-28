"""
路由注册模块 — 与 server.py 分离，避免循环导入
各 API 模块从此处导入 get/post/put/delete 装饰器
"""
import re

_ROUTES = []


def route(method: str, path: str, auth: bool = True, roles: list = None):
    if roles is None:
        roles = ["*"]
    def decorator(fn):
        pattern_str = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", path)
        pattern_str = "^" + pattern_str + "$"
        _ROUTES.append((method.upper(), re.compile(pattern_str), fn, auth, roles))
        return fn
    return decorator


def get(path: str, auth: bool = True, roles: list = None):
    return route("GET", path, auth, roles)


def post(path: str, auth: bool = True, roles: list = None):
    return route("POST", path, auth, roles)


def put(path: str, auth: bool = True, roles: list = None):
    return route("PUT", path, auth, roles)


def delete(path: str, auth: bool = True, roles: list = None):
    return route("DELETE", path, auth, roles)
