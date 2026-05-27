#!/bin/bash
# ============================================================
# 一键推送部署 - 在本地 Mac 上执行
# 用法: bash deploy/push.sh "本次改动的说明"
# ============================================================
set -e

cd "$(dirname "$0")/.."

MSG="$1"
if [ -z "$MSG" ]; then
    MSG="chore: AI引擎优化 $(date +%Y%m%d-%H%M)"
fi

echo "========================================"
echo "  一键推送部署"
echo "========================================"

# 检查是否有改动
if git diff --quiet && git diff --cached --quiet; then
    echo "⚠️  没有检测到改动，跳过"
    exit 0
fi

# 显示改动了什么
echo ""
echo "📝 改动的文件:"
git status -s

# 提交
echo ""
echo "📤 提交中..."
git add -A
git commit -m "$MSG

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"

# 推送
echo ""
echo "🚀 推送到远程..."
git push origin main

echo ""
echo "========================================"
echo "  ✅ 已推送！服务器将自动拉取更新"
echo "========================================"
