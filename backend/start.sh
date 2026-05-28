#!/bin/bash
# TMS v2 — 启动脚本
cd "$(dirname "$0")" || exit 1
exec python3 -u server.py "$@"
