#!/usr/bin/env python3
"""AI知识引擎专用入口 - 与网站版本隔离，使用独立端口和配置"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load API key from .env
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                os.environ["DEEPSEEK_API_KEY"] = line.split("=", 1)[1].strip()
                break

# AI引擎固定使用4567端口，与网站版本完全隔离
os.environ['AI_ENGINE_MODE'] = '1'
port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get('PORT', 4567))

from web.server import run_server

if __name__ == '__main__':
    run_server(port=port)
