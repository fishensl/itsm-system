#!/usr/bin/env bash
# ============================================================
# ITSM 备份脚本 — 打包 DB + 密钥
# 建议加入 crontab: 0 3 * * * /opt/itsm/scripts/backup.sh
# ============================================================
set -euo pipefail

APP_DIR="/opt/itsm"
BACKUP_DIR="${APP_DIR}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/itsm_full_${TIMESTAMP}.tar.gz"
KEEP_COUNT=30

mkdir -p "${BACKUP_DIR}"

tar -czf "${BACKUP_FILE}" \
    -C "${APP_DIR}" \
    instance/itsm.db \
    .secret.key \
    .env 2>/dev/null || true

echo "备份完成: ${BACKUP_FILE}"

# 清理旧备份
OLD_COUNT=$(ls -1 "${BACKUP_DIR}"/itsm_full_*.tar.gz 2>/dev/null | wc -l)
if [ "${OLD_COUNT}" -gt "${KEEP_COUNT}" ]; then
    ls -1t "${BACKUP_DIR}"/itsm_full_*.tar.gz | tail -n +$((KEEP_COUNT + 1)) | xargs rm -f
    echo "已清理 $((OLD_COUNT - KEEP_COUNT)) 份旧备份"
fi
