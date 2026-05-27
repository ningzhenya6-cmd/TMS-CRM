#!/usr/bin/env python3
"""留学课业 AI 知识引擎 - 启动入口"""
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

from web.server import run_server

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get('PORT', 8899))
    run_server(port=port)
