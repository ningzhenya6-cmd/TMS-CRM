#!/usr/bin/env python3
"""SM System — 学管系统 启动入口"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sm_system.server import run_server

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get('PORT', 8766))
    run_server(port=port)
