#!/bin/bash
# TMS — 数据库备份脚本
# 用法: ./scripts/backup.sh [备份目录(可选)]
# 默认备份到: ./backups/

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${1:-$SCRIPT_DIR/backups}"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_PATH="$SCRIPT_DIR/sm_system/sm.db"

if [ ! -f "$DB_PATH" ]; then
    echo "[ERROR] 数据库文件不存在: $DB_PATH"
    exit 1
fi

# 使用 sqlite3 的 .backup 命令进行安全备份（热备份，不影响正在运行的 TMS）
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/sm_$TIMESTAMP.db'"

# 压缩旧备份（保留最近30天）
find "$BACKUP_DIR" -name "sm_*.db" -mtime +30 -exec gzip {} \;

# 清理超过90天的压缩包
find "$BACKUP_DIR" -name "sm_*.db.gz" -mtime +90 -delete

echo "[OK] 备份完成: $BACKUP_DIR/sm_$TIMESTAMP.db"
echo "     当前备份数: $(find "$BACKUP_DIR" -name 'sm_*.db' | wc -l | tr -d ' ') 个"
