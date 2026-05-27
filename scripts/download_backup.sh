#!/bin/bash
# TMS 自动备份下载脚本
# 每天从服务器拉取最新的 Excel 备份到桌面
# 配合 macOS launchd 定时运行

URL="https://tms.global1v1.com/api/sm/export-excel"
LOGIN_URL="https://tms.global1v1.com/api/sm/login"
SAVE_DIR="$HOME/Desktop/TMS备份"
mkdir -p "$SAVE_DIR"

# 登录获取 token
LOGIN_RESP=$(curl -s -k "$LOGIN_URL" -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin@2026"}')
TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "[$(date)] ❌ 登录失败" >> "$SAVE_DIR/备份日志.txt"
  exit 1
fi

# 下载 Excel
FILENAME="TMS_数据备份_$(date +%Y%m%d).xlsx"
curl -s -k -o "$SAVE_DIR/$FILENAME" \
  -H "Cookie: sm_session=$TOKEN" \
  "$URL"

# 验证文件有效性
if [ -f "$SAVE_DIR/$FILENAME" ] && [ -s "$SAVE_DIR/$FILENAME" ]; then
  SIZE=$(du -h "$SAVE_DIR/$FILENAME" | cut -f1)
  echo "[$(date)] ✅ 备份成功: $FILENAME ($SIZE)" >> "$SAVE_DIR/备份日志.txt"

  # 清理30天前的旧备份
  find "$SAVE_DIR" -name "TMS_数据备份_*.xlsx" -mtime +30 -delete
else
  echo "[$(date)] ❌ 下载失败" >> "$SAVE_DIR/备份日志.txt"
fi
