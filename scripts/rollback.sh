#!/usr/bin/env bash
# ============================================================
# ITSM 紧急回滚脚本
# 用法: sudo bash rollback.sh [/path/to/app] [备份文件]
#
# 按 .env 的 ITSM_DATABASE_URI 自动选择恢复方式：
#   - PostgreSQL（.dump）：pg_restore 整库恢复（--clean 重建，含 schema+数据），
#     同时间戳 itsm_meta_*.tar.gz（.secret.key/.env）存在则一并还原
#   - SQLite（.db / .pre_update_*）：cp 回 instance/itsm.db
#   - backup.sh 的 itsm_full_*.tar.gz：解包（SQLite 模式整包）
#
# 注意：本脚本只回滚「数据/密钥」，不自动回滚代码。PG 模式下恢复后
# 库结构回到备份时刻，需管理员将代码切到对应版本（git checkout <tag>）
# 并还原前端 static/app.bak，再重启，否则 schema/代码不匹配。
# ============================================================
set -euo pipefail

APP_DIR="${1:-/opt/itsm}"
BACKUP="${2:-}"

if [ -z "${BACKUP}" ]; then
    echo "可用备份:"
    ls -1t "${APP_DIR}"/backups/itsm_pg_*.dump \
           "${APP_DIR}"/backups/itsm_full_*.tar.gz \
           "${APP_DIR}"/backups/itsm.db.pre_update_* \
           "${APP_DIR}"/backups/itsm.db.* 2>/dev/null | sort -u | head -20 || echo "  (无)"
    echo ""
    echo "用法: $0 [应用目录] [备份文件]"
    echo "示例: $0 /opt/itsm backups/itsm_pg_20260808_120000.dump"
    echo "      $0 /opt/itsm backups/itsm.db.pre_update_20260808_120000"
    exit 1
fi

if [ ! -f "${BACKUP}" ]; then
    echo "[FATAL] 备份文件不存在: ${BACKUP}"
    exit 1
fi

echo "即将回滚到: ${BACKUP}"
read -rp "确认? (输入 yes 继续): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    echo "已取消"
    exit 0
fi

# 从 .env 读 DB URI（与 backup.sh 同源判定）
ENV_FILE="${APP_DIR}/.env"
DB_URI_VAL=""
if [ -f "${ENV_FILE}" ]; then
    DB_URI_VAL=$(grep -E '^ITSM_DATABASE_URI=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)
fi

echo "停止服务..."
systemctl stop itsm

# ---- PostgreSQL 分支：pg_dump 自定义格式 .dump ----
if [ -n "${DB_URI_VAL}" ] && [[ "${DB_URI_VAL}" == postgresql* ]] && [[ "${BACKUP}" == *.dump ]]; then
    # postgresql://user:pass@host:port/dbname
    PG_USER=$(echo "${DB_URI_VAL}" | sed -E 's#^postgresql://([^:]+):.*#\1#')
    PG_DB=$(echo "${DB_URI_VAL}" | sed -E 's#.*/([^/?]+)$#\1#')
    PG_HOST=$(echo "${DB_URI_VAL}" | sed -E 's#^postgresql://[^@]+@([^:/]+).*#\1#')
    PG_PORT=$(echo "${DB_URI_VAL}" | sed -E 's#.*:([0-9]+)/.*#\1#')
    [ "${PG_PORT}" = "${DB_URI_VAL}" ] && PG_PORT="5432"
    export PGPASSWORD=$(echo "${DB_URI_VAL}" | sed -E 's#^postgresql://[^:]+:([^@]+)@.*#\1#')

    echo "恢复 PostgreSQL 库 ${PG_DB}（pg_restore --clean，整库重建到备份时刻）..."
    pg_restore --clean --if-exists --no-owner \
        -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${PG_DB}" "${BACKUP}"

    # 同时间戳 meta 包（.secret.key/.env）存在则还原
    META="${BACKUP//itsm_pg_/itsm_meta_}"
    META="${META%.dump}.tar.gz"
    if [ -f "${META}" ]; then
        echo "还原密钥与配置: ${META}"
        tar -xzf "${META}" -C "${APP_DIR}"
        chown itsm:itsm "${APP_DIR}/.secret.key" "${APP_DIR}/.env" 2>/dev/null || true
    else
        echo "  [WARN] 未找到同时间戳 meta 包（${META}），密钥/.env 未还原"
    fi
    echo "PostgreSQL 回滚完成"

# ---- SQLite / 旧式 .pre_update_ 文件 ----
elif [ -n "${DB_URI_VAL}" ] && [[ "${DB_URI_VAL}" == sqlite* ]] && [[ "${BACKUP}" == *.db* ]]; then
    cp "${BACKUP}" "${APP_DIR}/instance/itsm.db"
    chown itsm:itsm "${APP_DIR}/instance/itsm.db" 2>/dev/null || true
    echo "SQLite 回滚完成"

# ---- backup.sh 的 full 整包（SQLite 模式 tar，含 db+密钥+.env）----
elif [[ "${BACKUP}" == *.tar.gz ]]; then
    tar -xzf "${BACKUP}" -C "${APP_DIR}"
    chown itsm:itsm "${APP_DIR}/instance/itsm.db" "${APP_DIR}/.secret.key" "${APP_DIR}/.env" 2>/dev/null || true
    echo "整包回滚完成"

# ---- 兜底：按 SQLite 文件恢复 ----
else
    echo "  [WARN] 备份类型与当前数据库模式不匹配，按 SQLite 文件方式尝试..."
    cp "${BACKUP}" "${APP_DIR}/instance/itsm.db"
    chown itsm:itsm "${APP_DIR}/instance/itsm.db" 2>/dev/null || true
    echo "已按 SQLite 文件恢复"
fi

echo "启动服务..."
systemctl start itsm

echo ""
echo "============================================"
echo "  回滚完成（数据/密钥层面）"
if [ -n "${DB_URI_VAL}" ] && [[ "${DB_URI_VAL}" == postgresql* ]]; then
    echo "  ⚠ PG 模式：库结构与数据已回到备份时刻。"
    echo "  若代码/前端仍是最新版本，请将代码切回对应版本"
    echo "  （git checkout <旧tag>）并还原 static/app.bak 后重启，再验证。"
fi
echo "============================================"
systemctl status itsm --no-pager -l || true
