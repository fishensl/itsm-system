#!/usr/bin/env bash
# ============================================================
# ITSM 备份脚本 — 打包 DB + 密钥
# 用法: sudo bash backup.sh [/path/to/app]
# crontab: 0 3 * * * /home/itsm-system_20260614/scripts/backup.sh /home/itsm-system_20260614
# 行为：按 .env 的 ITSM_DATABASE_URI 自动选择备份方式：
#   - SQLite：tar 打包 instance/itsm.db + .secret.key + .env
#   - PostgreSQL：pg_dump -Fc 自定义格式 + 打包 .secret.key + .env
# ============================================================
set -euo pipefail

APP_DIR="${1:-/opt/itsm}"
ENV_FILE="${APP_DIR}/.env"
BACKUP_DIR="${APP_DIR}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
KEEP_COUNT=30

mkdir -p "${BACKUP_DIR}"

# 从 .env 读 DB URI（systemd 也注入，这里直跑时补齐）
DB_URI_VAL=""
if [ -f "${ENV_FILE}" ]; then
    DB_URI_VAL=$(grep -E '^ITSM_DATABASE_URI=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)
fi

if [ -n "${DB_URI_VAL}" ] && [[ "${DB_URI_VAL}" == postgresql* ]]; then
    # ---- PostgreSQL：pg_dump ----
    BACKUP_FILE="${BACKUP_DIR}/itsm_pg_${TIMESTAMP}.dump"
    echo "[backup] PostgreSQL 模式，pg_dump 自定义格式..."
    # 从 URI 解析库/用户/主机/端口
    # postgresql://user:pass@host:port/dbname
    PG_USER=$(echo "${DB_URI_VAL}" | sed -E 's#^postgresql://([^:]+):.*#\1#')
    PG_DB=$(echo "${DB_URI_VAL}" | sed -E 's#.*/([^/?]+)$#\1#')
    PG_HOST=$(echo "${DB_URI_VAL}" | sed -E 's#^postgresql://[^@]+@([^:/]+).*#\1#')
    PG_PORT=$(echo "${DB_URI_VAL}" | sed -E 's#.*:([0-9]+)/.*#\1#')
    [ "${PG_PORT}" = "${DB_URI_VAL}" ] && PG_PORT="5432"
    # 用 .pgpass 或 URI 内联密码；此处用 PGPASSWORD 环境变量
    export PGPASSWORD=$(echo "${DB_URI_VAL}" | sed -E 's#^postgresql://[^:]+:([^@]+)@.*#\1#')
    pg_dump -Fc -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${PG_DB}" -f "${BACKUP_FILE}"
    # 密钥 + .env 一并 tar（DB 已单独 dump）
    EXTRA="${BACKUP_DIR}/itsm_meta_${TIMESTAMP}.tar.gz"
    tar -czf "${EXTRA}" -C "${APP_DIR}" .secret.key .env 2>/dev/null || true
    echo "[backup] 完成: ${BACKUP_FILE} (+ ${EXTRA})"
elif [ -n "${DB_URI_VAL}" ] && [[ "${DB_URI_VAL}" == sqlite* ]]; then
    # ---- SQLite：文件级 tar ----
    BACKUP_FILE="${BACKUP_DIR}/itsm_full_${TIMESTAMP}.tar.gz"
    DB_PATH="${DB_URI_VAL#sqlite:///}"
    tar -czf "${BACKUP_FILE}" \
        -C "${APP_DIR}" \
        instance/itsm.db \
        .secret.key \
        .env 2>/dev/null || true
    echo "[backup] 完成: ${BACKUP_FILE}"
else
    # ---- 未知/未配置 URI：按旧逻辑默认 SQLite 文件 ----
    BACKUP_FILE="${BACKUP_DIR}/itsm_full_${TIMESTAMP}.tar.gz"
    tar -czf "${BACKUP_FILE}" \
        -C "${APP_DIR}" \
        instance/itsm.db \
        .secret.key \
        .env 2>/dev/null || true
    echo "[backup] 完成: ${BACKUP_FILE}（未在 .env 检测到 URI，按默认 SQLite 处理）"
fi

# 保留最近 KEEP_COUNT 份（按时间倒序）
OLD_COUNT=$(ls -1 "${BACKUP_DIR}"/itsm_full_*.tar.gz "${BACKUP_DIR}"/itsm_pg_*.dump 2>/dev/null | wc -l)
if [ "${OLD_COUNT}" -gt "${KEEP_COUNT}" ]; then
    ls -1t "${BACKUP_DIR}"/itsm_full_*.tar.gz "${BACKUP_DIR}"/itsm_pg_*.dump 2>/dev/null | tail -n +$((KEEP_COUNT + 1)) | xargs rm -f
    echo "已清理旧备份"
fi
