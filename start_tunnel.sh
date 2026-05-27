#!/bin/bash
# ============================================================
# 一键启动：本地服务器 + Cloudflare Tunnel 公网映射
# 运行方式：bash start_tunnel.sh
# ============================================================

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  留学课业AI引擎 - 内网穿透启动脚本${NC}"
echo -e "${GREEN}========================================${NC}"

# Step 1: 检查 cloudflared 是否安装
if ! command -v cloudflared &>/dev/null; then
    echo -e "\n${YELLOW}[1/3] 正在安装 cloudflared...${NC}"
    # macOS 推荐方式
    if command -v brew &>/dev/null; then
        brew install cloudflared
    else
        # 直接下载二进制
        echo "正在下载 cloudflared..."
        curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz -o /tmp/cloudflared.tgz
        tar -xzf /tmp/cloudflared.tgz -C /tmp
        sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
        rm /tmp/cloudflared.tgz
    fi
else
    echo -e "${GREEN}[1/3] cloudflared 已安装 ✓${NC}"
fi

# Step 2: 启动 AI 引擎服务器
echo -e "\n${YELLOW}[2/3] 启动 AI 引擎 (端口 8765)...${NC}"

# 检查端口是否被占用
if lsof -i :8765 &>/dev/null 2>&1; then
    echo "端口 8765 已被占用，尝试杀掉旧进程..."
    kill $(lsof -t -i :8765) 2>/dev/null || true
    sleep 1
fi

# 切换到 web 目录并后台启动
cd "$(dirname "$0")/web"
python3 server.py &
SERVER_PID=$!
echo "服务器 PID: $SERVER_PID"
sleep 2

# 检查是否启动成功
if kill -0 $SERVER_PID 2>/dev/null; then
    echo -e "${GREEN}服务器启动成功 ✓${NC}"
else
    echo -e "${RED}服务器启动失败，请检查 server.py 是否有报错${NC}"
    exit 1
fi

# Step 3: 启动 Cloudflare Tunnel
echo -e "\n${YELLOW}[3/3] 启动 Cloudflare Tunnel...${NC}"
echo -e "(首次运行会要求浏览器登录 Cloudflare 账号，按提示操作即可)\n"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  隧道启动中，请稍候...${NC}"
echo -e "${GREEN}  成功后会显示公网 URL${NC}"
echo -e "${GREEN}========================================${NC}\n"

cloudflared tunnel --url http://localhost:8765

# 如果上面的命令退出（按 Ctrl+C），清理服务器进程
echo "正在停止服务器..."
kill $SERVER_PID 2>/dev/null || true
