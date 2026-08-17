#!/usr/bin/env bash
# ============================================================
# ITSM 备份脚本 — 打包 DB + 密钥
# 用法: sudo bash backup.sh [/path/to/app]
# 生产定时任务由 itsm-backup.timer 调用，时间与开关从 system_settings 读取。
# 行为：按 .env 的 ITSM_DATABASE_URI 自动选择备份方式：
#   - SQLite：tar 打包 instance/itsm.db + .secret.key + .env
#   - PostgreSQL：pg_dump -Fc 自定义格式 + 打包 .secret.key + .env
# ============================================================
set -euo pipefail
umask 077

APP_DIR="${1:-/opt/itsm}"
ENV_FILE="${APP_DIR}/.env"
BACKUP_DIR="${APP_DIR}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
# 保留份数：Web 备份管理可经 ITSM_BACKUP_KEEP 覆盖（默认 30）
KEEP_COUNT="${ITSM_BACKUP_KEEP:-30}"
PARTIAL_FILES=()

on_error() {
    local exit_code="$1"
    local line_no="$2"
    trap - ERR
    for partial in "${PARTIAL_FILES[@]}"; do
        [ -n "${partial}" ] && rm -f -- "${partial}"
    done
    local message="ITSM backup failed at line ${line_no} (exit ${exit_code})"
    echo "[backup][ERROR] ${message}" >&2
    if command -v logger >/dev/null 2>&1; then
        logger -p user.err -t itsm-backup "${message}"
    fi
    exit "${exit_code}"
}
trap 'on_error $? $LINENO' ERR

if ! [[ "${KEEP_COUNT}" =~ ^[1-9][0-9]*$ ]]; then
    echo "[backup][FATAL] ITSM_BACKUP_KEEP 必须是正整数" >&2
    exit 2
fi

mkdir -p "${BACKUP_DIR}"

# Web 调度、systemd timer 与人工备份可能重叠；同一时刻只允许一套备份写入。
LOCK_FILE="${APP_DIR}/instance/backup.lock"
mkdir -p "${APP_DIR}/instance"
exec 9>"${LOCK_FILE}"
if command -v flock >/dev/null 2>&1 && ! flock -n 9; then
    echo "[backup][FATAL] 已有备份任务运行中" >&2
    exit 3
fi

if [ ! -f "${ENV_FILE}" ]; then
    echo "[backup][FATAL] 缺少 ${ENV_FILE}" >&2
    exit 2
fi

KEY_ITEMS=()
shopt -s nullglob
KEY_PATHS=("${APP_DIR}"/.secret.key*)
for key_path in "${KEY_PATHS[@]}"; do
    [ -f "${key_path}" ] || continue
    key_mode=$(stat -c '%a' "${key_path}")
    if [ "${key_mode}" != "600" ]; then
        chmod 600 "${key_path}" || {
            echo "[backup][FATAL] 无法将 ${key_path} 权限修正为 600（当前 ${key_mode}）" >&2
            exit 2
        }
        key_mode=$(stat -c '%a' "${key_path}")
        if [ "${key_mode}" != "600" ]; then
            echo "[backup][FATAL] ${key_path} 权限必须为 600，当前为 ${key_mode}" >&2
            exit 2
        fi
    fi
done
# 备份集合只携带当前活动密钥；历史 .bak 文件仅断言权限，不再次扩散。
for key_name in .secret.key .secret.key.locked; do
    [ -f "${APP_DIR}/${key_name}" ] && KEY_ITEMS+=("${key_name}")
done
if [ "${#KEY_ITEMS[@]}" -eq 0 ]; then
    echo "[backup][FATAL] 未找到 .secret.key 或 .secret.key.locked" >&2
    exit 2
fi

for required_dir in reports uploads static/uploads; do
    if [ ! -d "${APP_DIR}/${required_dir}" ]; then
        echo "[backup][FATAL] 缺少业务文件目录 ${APP_DIR}/${required_dir}" >&2
        exit 2
    fi
done

# 从 .env 读 DB URI（systemd 也注入，这里直跑时补齐）
DB_URI_VAL=$(awk -F= '$1 == "ITSM_DATABASE_URI" {sub(/^[^=]*=/, ""); print; exit}' "${ENV_FILE}")

if [ -n "${DB_URI_VAL}" ] && [[ "${DB_URI_VAL}" == postgresql* ]]; then
    # ---- PostgreSQL：pg_dump ----
    BACKUP_FILE="${BACKUP_DIR}/itsm_pg_${TIMESTAMP}.dump"
    DUMP_PARTIAL="${BACKUP_FILE}.partial"
    META_PARTIAL="${BACKUP_DIR}/itsm_meta_${TIMESTAMP}.tar.gz.partial"
    PARTIAL_FILES+=("${DUMP_PARTIAL}" "${META_PARTIAL}")
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
    pg_dump -Fc -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${PG_DB}" -f "${DUMP_PARTIAL}"
    pg_restore --list "${DUMP_PARTIAL}" >/dev/null
    # 密钥 + .env + 业务文件目录（reports/uploads/static/uploads）一并 tar
    # —— 文件目录缺失会导致整机恢复后报告/上传文件丢失，故必须包含
    EXTRA="${BACKUP_DIR}/itsm_meta_${TIMESTAMP}.tar.gz"
    tar -czf "${META_PARTIAL}" -C "${APP_DIR}" \
        "${KEY_ITEMS[@]}" .env reports uploads static/uploads
    tar -tzf "${META_PARTIAL}" >/dev/null
    mv "${DUMP_PARTIAL}" "${BACKUP_FILE}"
    mv "${META_PARTIAL}" "${EXTRA}"
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
    FULL_PARTIAL="${BACKUP_FILE}.partial"
    PARTIAL_FILES+=("${FULL_PARTIAL}")
    tar -czf "${FULL_PARTIAL}" \
        -C "${APP_DIR}" \
        instance/itsm.db \
        "${KEY_ITEMS[@]}" \
        .env \
        reports uploads static/uploads
    tar -tzf "${FULL_PARTIAL}" >/dev/null
    mv "${FULL_PARTIAL}" "${BACKUP_FILE}"
    echo "[backup] 完成: ${BACKUP_FILE}"
else
    echo "[backup][FATAL] ITSM_DATABASE_URI 缺失或不受支持，拒绝猜测数据库类型" >&2
    exit 2
fi

# 按备份集轮转；PostgreSQL dump 与同时间戳 meta 必须一起删除。
shopt -s nullglob
FULL_BACKUPS=("${BACKUP_DIR}"/itsm_full_*.tar.gz)
PG_BACKUPS=("${BACKUP_DIR}"/itsm_pg_*.dump)
BACKUP_SETS=("${FULL_BACKUPS[@]}" "${PG_BACKUPS[@]}")
if [ "${#BACKUP_SETS[@]}" -gt "${KEEP_COUNT}" ]; then
    mapfile -t BACKUP_SETS < <(
        for backup_file in "${BACKUP_SETS[@]}"; do
            printf '%s\t%s\n' "$(stat -c '%Y' "${backup_file}")" "${backup_file}"
        done | sort -rn | cut -f2-
    )
    for backup_file in "${BACKUP_SETS[@]:${KEEP_COUNT}}"; do
        if [[ "${backup_file}" == */itsm_pg_*.dump ]]; then
            backup_stamp="${backup_file##*/itsm_pg_}"
            backup_stamp="${backup_stamp%.dump}"
            meta_file="${BACKUP_DIR}/itsm_meta_${backup_stamp}.tar.gz"
            rm -f -- "${backup_file}" "${meta_file}"
        else
            rm -f -- "${backup_file}"
        fi
    done
    echo "[backup] 已按备份集清理旧备份"
fi
