#!/bin/bash
# ============================================================
# 打包脚本 - 在本地运行，生成可直接部署到服务器的压缩包
# ============================================================
set -e

PROJECT="study-ai"
VERSION=$(date +%Y%m%d)
OUTPUT="/tmp/${PROJECT}-${VERSION}.tar.gz"

echo "📦 打包项目..."
cd "$(dirname "$0")/.."

# 排除不需要的文件
tar --exclude='.git' \
    --exclude='.claude' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='node_modules' \
    -czf "$OUTPUT" \
    config/ \
    data/ \
    knowledge/ \
    web/ \
    deploy/setup.sh \
    .env

echo "✅ 打包完成: $OUTPUT"
echo "   ($(du -h "$OUTPUT" | cut -f1))"
echo ""
echo "👉 上传到服务器:"
echo "   scp $OUTPUT root@你的服务器IP:/opt/"
echo ""
echo "👉 在服务器上执行:"
echo "   cd /opt && tar xzf $(basename $OUTPUT) && bash deploy/setup.sh"
