#!/bin/bash
# ============================================================
# 服务器自动化配置 - 在阿里云服务器上首次运行一次
# 设置：systemd 服务 + cron 自动拉取 + cron 自动导出数据
# ============================================================
set -e

cd "$(dirname "$0")/.."
PROJECT_DIR=$(pwd)
PROJECT_NAME="study-ai"

echo "========================================"
echo "  留学课业AI引擎 - 服务器自动化配置"
echo "========================================"

# 1. 检查环境
echo ""
echo "[1/5] 检查环境..."
PYTHON=""
for cmd in python3 python; do
    if command -v $cmd &>/dev/null; then
        PYTHON=$cmd
        echo "  ✅ Python: $($PYTHON --version)"
        break
    fi
done
if [ -z "$PYTHON" ]; then echo "  ❌ 需要 Python 3.8+"; exit 1; fi

# 2. 配置 .env
echo ""
echo "[2/5] 配置环境变量..."
ENV_FILE="$PROJECT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "  ⚠️  未找到 .env，请创建并填入 DEEPSEEK_API_KEY"
    echo "     echo 'DEEPSEEK_API_KEY=你的密钥' > $ENV_FILE"
    echo "     echo 'ADMIN_PASSWORD=后台密码' >> $ENV_FILE"
fi

# 读取管理员密码
ADMIN_PWD=""
if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
    ADMIN_PWD="$ADMIN_PASSWORD"
fi

# 3. 安装 systemd 服务
echo ""
echo "[3/5] 安装 systemd 服务..."
cat > /tmp/$PROJECT_NAME.service << EOF
[Unit]
Description=留学课业AI引擎
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR/web
ExecStart=$PYTHON server.py
Environment=ADMIN_PASSWORD=$ADMIN_PWD
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo mv /tmp/$PROJECT_NAME.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable $PROJECT_NAME
sudo systemctl restart $PROJECT_NAME
echo "  ✅ systemd 服务已安装并启动"

# 4. 配置 git 自动拉取（每分钟检查）
echo ""
echo "[4/5] 配置 git 自动拉取..."
GIT_SCRIPT="/usr/local/bin/${PROJECT_NAME}-autopull.sh"
cat > $GIT_SCRIPT << EOF
#!/bin/bash
cd $PROJECT_DIR
git fetch origin 2>/dev/null || exit 0
LOCAL=\$(git rev-parse HEAD)
REMOTE=\$(git rev-parse @{u} 2>/dev/null || echo "\$LOCAL")
if [ "\$LOCAL" != "\$REMOTE" ]; then
    echo "[autopull] \$(date): 检测到更新，拉取中..."
    git pull --ff-only
    sudo systemctl restart $PROJECT_NAME
    echo "[autopull] \$(date): 已更新并重启"
fi
EOF
chmod +x $GIT_SCRIPT

(crontab -l 2>/dev/null | grep -v "$PROJECT_NAME-autopull" ; echo "* * * * * $GIT_SCRIPT >> /var/log/${PROJECT_NAME}-autopull.log 2>&1") | crontab -
echo "  ✅ git 自动拉取已配置（每分钟检查）"

# 5. 配置数据自动导出（每小时 + git push）
echo ""
echo "[5/5] 配置数据自动导出..."
EXPORT_SCRIPT="/usr/local/bin/${PROJECT_NAME}-export.sh"
cat > $EXPORT_SCRIPT << EOF
#!/bin/bash
cd $PROJECT_DIR
TIMESTAMP=\$(date "+%Y-%m-%d %H:%M:%S")
echo "[export] \$TIMESTAMP: 开始导出..."

python3 deploy/export_data.py 2>/dev/null || { echo "[export] 导出失败"; exit 1; }

git add analysis/ 2>/dev/null
if git diff --cached --quiet; then
    echo "[export] 数据无变化，跳过提交"
else
    git commit -m "chore: 自动导出分析数据 \$TIMESTAMP"
    git push origin main 2>/dev/null && echo "[export] ✅ 已推送到仓库" || echo "[export] ⚠️ 推送失败（可能是没有更新）"
fi
EOF
chmod +x $EXPORT_SCRIPT

(crontab -l 2>/dev/null | grep -v "$PROJECT_NAME-export" ; echo "0 * * * * $EXPORT_SCRIPT >> /var/log/${PROJECT_NAME}-export.log 2>&1") | crontab -
echo "  ✅ 数据自动导出已配置（每小时整点运行）"

echo ""
echo "========================================"
echo "  🎉 服务器自动化配置完成！"
echo "========================================"
echo ""
echo "服务状态:"
sudo systemctl status $PROJECT_NAME --no-pager 2>&1 | tail -5
echo ""
echo "日志查看:"
echo "  sudo journalctl -u $PROJECT_NAME -f"
echo "  tail -f /var/log/${PROJECT_NAME}-autopull.log"
echo "  tail -f /var/log/${PROJECT_NAME}-export.log"
echo ""
echo "手动操作:"
echo "  sudo systemctl restart $PROJECT_NAME    # 重启服务"
echo "  sudo systemctl stop $PROJECT_NAME       # 停止"
echo "  sudo systemctl start $PROJECT_NAME      # 启动"
