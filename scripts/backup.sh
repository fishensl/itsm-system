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
# 保留份数：Web 备份管理可经 ITSM_BACKUP_KEEP 覆盖（默认 30）
KEEP_COUNT="${ITSM_BACKUP_KEEP:-30}"

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
    # 密钥 + .env + 业务文件目录（reports/uploads/static/uploads）一并 tar
    # —— 文件目录缺失会导致整机恢复后报告/上传文件丢失，故必须包含
    EXTRA="${BACKUP_DIR}/itsm_meta_${TIMESTAMP}.tar.gz"
    tar -czf "${EXTRA}" -C "${APP_DIR}" \
        .secret.key .env \
        reports uploads static/uploads 2>/dev/null || true
    echo "[backup] 完成: ${BACKUP_FILE} (+ ${EXTRA})"
elif [ -n "${DB_URI_VAL}" ] && [[ "${DB_URI_VAL}" == sqlite* ]]; then
    # ---- SQLite：文件级 tar ----
    BACKUP_FILE="${BACKUP_DIR}/itsm_full_${TIMESTAMP}.tar.gz"
    # 解析 DB 相对路径（sqlite:///instance/itsm.db 或绝对路径均兼容）
    DB_PATH="${DB_URI_VAL#sqlite:///}"
    # 绝对路径直接引用；相对路径按 APP_DIR 拼接（供后续恢复校验使用，tar 仍按 APP_DIR 相对打包）
    [ "${DB_PATH#/}" = "${DB_PATH}" ] && DB_ABS="${APP_DIR}/${DB_PATH}" || DB_ABS="${DB_PATH}"
    if [ ! -f "${DB_ABS}" ]; then
        # 常见默认：sqlite:/// 后的路径就是相对于 APP_DIR 的 instance/itsm.db
        DB_ABS="${APP_DIR}/instance/itsm.db"
    fi
    tar -czf "${BACKUP_FILE}" \
        -C "${APP_DIR}" \
        instance/itsm.db \
        .secret.key \
        .env \
        reports uploads static/uploads 2>/dev/null || true
    echo "[backup] 完成: ${BACKUP_FILE}"
else
    # ---- 未知/未配置 URI：按旧逻辑默认 SQLite 文件 ----
    BACKUP_FILE="${BACKUP_DIR}/itsm_full_${TIMESTAMP}.tar.gz"
    tar -czf "${BACKUP_FILE}" \
        -C "${APP_DIR}" \
        instance/itsm.db \
        .secret.key \
        .env \
        reports uploads static/uploads 2>/dev/null || true
    echo "[backup] 完成: ${BACKUP_FILE}（未在 .env 检测到 URI，按默认 SQLite 处理）"
fi

# 保留最近 KEEP_COUNT 份（按时间倒序）
OLD_COUNT=$(ls -1 "${BACKUP_DIR}"/itsm_full_*.tar.gz "${BACKUP_DIR}"/itsm_pg_*.dump 2>/dev/null | wc -l)
if [ "${OLD_COUNT}" -gt "${KEEP_COUNT}" ]; then
    ls -1t "${BACKUP_DIR}"/itsm_full_*.tar.gz "${BACKUP_DIR}"/itsm_pg_*.dump 2>/dev/null | tail -n +$((KEEP_COUNT + 1)) | xargs rm -f
    echo "已清理旧备份"
fi
