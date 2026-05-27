#!/bin/bash
# ============================================================
# Git 初始化脚本 - 在本地 Mac 上运行一次
# 用法: bash deploy/init.sh https://gitee.com/你的用户名/study-ai.git
# ============================================================
set -e

if [ -z "$1" ]; then
    echo "用法: bash deploy/init.sh https://gitee.com/你的用户名/study-ai.git"
    echo ""
    echo "先在 Gitee 建一个空仓库（不要勾选初始化 README）"
    exit 1
fi

GITEE_URL="$1"
cd "$(dirname "$0")/.."

echo "========================================"
echo "  初始化 Git 仓库并推送到 Gitee"
echo "========================================"

# 初始化 git
if [ ! -d ".git" ]; then
    git init
    git checkout -b main
    echo "✅ git 仓库已初始化"
else
    echo "✅ git 仓库已存在"
fi

# 写入 .gitignore
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
.DS_Store
.env
data/knowledge.db
data/knowledge.db-shm
data/knowledge.db-wal
data/kb.json
config/ai_endpoint.json
.claude/
$TMPDIR/
*.tgz
*.tar.gz
EOF
echo "✅ .gitignore 已配置"

# 首次提交
git add -A
git commit -m "init: 留学课业AI知识引擎

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"

# 推送到 Gitee
git remote add origin "$GITEE_URL"
git push -u origin main

echo ""
echo "========================================"
echo "  ✅ 初始化完成！后续全自动"
echo "========================================"
echo ""
echo "我/龙虾 改完代码 → git push → 服务器自动拉取重启"
echo "服务器数据 → 每小时自动导出 → git push → 我/龙虾可以读取分析"
echo ""
echo "👉 现在去服务器执行:"
echo "  ssh root@你的服务器IP"
echo "  bash deploy/server-setup.sh"
