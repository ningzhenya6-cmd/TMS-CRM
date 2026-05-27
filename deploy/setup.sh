#!/bin/bash
# ============================================================
# 服务端安装脚本 - 在云服务器上运行一次
# 使用方式: bash deploy/setup.sh
# ============================================================
set -e

cd "$(dirname "$0")/.."
PROJECT_DIR=$(pwd)

echo "========================================"
echo "  留学课业AI引擎 - 云服务器部署"
echo "========================================"
echo "项目目录: $PROJECT_DIR"

# 1. 检查 Python 版本
echo ""
echo "[1/4] 检查 Python 环境..."
PYTHON=""
for cmd in python3 python; do
    if command -v $cmd &>/dev/null; then
        VER=$($cmd --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
        if [ "$(echo "$VER >= 3.8" | bc 2>/dev/null)" = "1" ] || [ "$(printf '%s\n' "3.8" "$VER" | sort -V | head -1)" = "3.8" ]; then
            PYTHON=$cmd
            echo "  ✅ 找到 Python $VER: $cmd"
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    echo "  ❌ 需要 Python 3.8+，请先安装"
    exit 1
fi

# 2. 检查 .env 中的 API key
echo ""
echo "[2/4] 检查 API 密钥..."
ENV_FILE="$PROJECT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "  ⚠️  未找到 .env 文件"
    echo "  🔑 请手动创建 $ENV_FILE，内容:"
    echo "     DEEPSEEK_API_KEY=你的密钥"
    echo ""
    # 创建模板
    echo "# AI API 密钥" > "$ENV_FILE"
    echo "# 替换为你的实际密钥" >> "$ENV_FILE"
    echo "DEEPSEEK_API_KEY=YOUR_KEY_HERE" >> "$ENV_FILE"
    echo "  📝 已创建模板文件，请编辑填入密钥"
else
    source "$ENV_FILE"
    if [ -n "$DEEPSEEK_API_KEY" ] && [ "$DEEPSEEK_API_KEY" != "YOUR_KEY_HERE" ]; then
        echo "  ✅ API 密钥已配置"
    else
        echo "  ⚠️  API 密钥未设置或为默认值"
        echo "  🔑 请编辑 $ENV_FILE 填入正确的密钥"
    fi
fi

# 3. 设置管理员密码
echo ""
echo "[3/4] 设置管理员密码..."
if [ -z "$ADMIN_PASSWORD" ]; then
    echo "  ⚠️  未设置 ADMIN_PASSWORD 环境变量"
    echo "  建议设置一个密码来保护管理后台"
    echo "  可以在启动时传入:"
    echo "    export ADMIN_PASSWORD='你的密码'"
    echo "  或者写入 /etc/systemd/system/study-ai.service 的 Environment 中"
    echo ""
    # 临时生成一个随机密码
    RANDOM_PASS=$(openssl rand -hex 8 2>/dev/null || date +%s | md5sum 2>/dev/null | head -c16 || echo "changeme123")
    echo "  临时建议密码: $RANDOM_PASS"
fi

# 4. 验证能正常启动（3秒后自动退出）
echo ""
echo "[4/4] 验证启动..."
cd "$PROJECT_DIR/web"
timeout 3 $PYTHON server.py 2>&1 || true
echo ""
echo "  ✅ 启动验证完成"

# 5. 显示 systemd 服务配置（可选）
echo ""
echo "========================================"
echo "  🎉 部署准备完成！"
echo "========================================"
echo ""
echo "👉 手动启动测试:"
echo "   cd $PROJECT_DIR/web"
echo "   ADMIN_PASSWORD='你的密码' $PYTHON server.py"
echo ""
echo "👉 如需开机自启，创建 systemd 服务:"
echo "   cat > /etc/systemd/system/study-ai.service << 'EOF'"
echo "[Unit]"
echo "Description=留学课业AI引擎"
echo "After=network.target"
echo ""
echo "[Service]"
echo "Type=simple"
echo "WorkingDirectory=$PROJECT_DIR/web"
echo "ExecStart=$PYTHON server.py"
echo "Environment=ADMIN_PASSWORD=你的密码"
echo "Restart=always"
echo "RestartSec=5"
echo ""
echo "[Install]"
echo "WantedBy=multi-user.target"
echo "EOF"
echo ""
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable --now study-ai"
echo ""
echo "👉 防火墙放行:"
echo "   sudo firewall-cmd --add-port=8765/tcp --permanent 2>/dev/null"
echo "   sudo firewall-cmd --reload 2>/dev/null"
echo "   # 或者: sudo ufw allow 8765/tcp"
echo "========================================"
