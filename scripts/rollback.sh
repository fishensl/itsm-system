#!/usr/bin/env bash
# ============================================================
# ITSM 紧急回滚脚本
# 用法: sudo bash rollback.sh [/path/to/app] [备份文件]
# ============================================================
set -euo pipefail

APP_DIR="${1:-/opt/itsm}"
BACKUP="${2:-}"

if [ -z "${BACKUP}" ]; then
    echo "可用备份:"
    ls -1t "${APP_DIR}/backups/itsm.db."* 2>/dev/null || echo "  (无)"
    echo ""
    echo "用法: $0 [应用目录] [备份文件]"
    echo "示例: $0 /opt/itsm backups/itsm.db.pre_update_20260615_120000"
    exit 1
fi

if [ ! -f "${BACKUP}" ]; then
    echo "[FATAL] 备份文件不存在: ${BACKUP}"
    exit 1
fi

echo "即将回滚数据库到: ${BACKUP}"
read -rp "确认? (输入 yes 继续): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    echo "已取消"
    exit 0
fi

echo "停止服务..."
systemctl stop itsm

echo "恢复数据库..."
cp "${BACKUP}" "${APP_DIR}/instance/itsm.db"
chown itsm:itsm "${APP_DIR}/instance/itsm.db" 2>/dev/null || true

echo "启动服务..."
systemctl start itsm

echo "回滚完成"
systemctl status itsm --no-pager -l || true
