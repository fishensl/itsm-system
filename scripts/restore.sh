#!/usr/bin/env bash
# ============================================================
# ITSM 整机恢复脚本（新服务器/灾难恢复）
# 用法: sudo bash restore.sh [/path/to/app] [备份产物]
#
# 从 backup.sh 产物一键恢复数据库 + 密钥 + 业务文件：
#   - PostgreSQL：itsm_pg_<ts>.dump + itsm_meta_<ts>.tar.gz（库 + 密钥/.env + 文件目录）
#   - SQLite：    itsm_full_<ts>.tar.gz（整包含 db + 密钥/.env + 文件目录）
#
# 前置条件：
#   1. 新服务器已安装代码（git pull 或 bundle）+ venv + .env（DB URI 指向目标库）
#   2. 备份产物已放到服务器（如 backups/ 或 scp 传入）
#   3. PG 模式目标库已创建（createdb）且用户有权限
#
# 行为：停服 → 恢复 DB → 还原密钥/.env → 还原文件目录 → 启动。
# 数据/密钥恢复后如需代码回滚请另行 git checkout。
# ============================================================
set -euo pipefail

APP_DIR="${1:-/opt/itsm}"
BACKUP="${2:-}"

if [ -z "${BACKUP}" ]; then
    echo "可用备份:"
    ls -1t "${APP_DIR}"/backups/itsm_pg_*.dump \
           "${APP_DIR}"/backups/itsm_full_*.tar.gz 2>/dev/null | head -20 || echo "  (无)"
    echo ""
    echo "用法: $0 [应用目录] [备份文件]"
    echo "示例: $0 /opt/itsm backups/itsm_pg_20260808_060732.dump"
    echo "      $0 /opt/itsm backups/itsm_full_20260808_060732.tar.gz"
    exit 1
fi

if [ ! -f "${BACKUP}" ]; then
    echo "[FATAL] 备份文件不存在: ${BACKUP}"
    exit 1
fi

echo "即将整机恢复（覆盖当前数据）: ${BACKUP}"
read -rp "确认? (输入 yes 继续): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    echo "已取消"
    exit 0
fi

# 从 .env 读 DB URI
ENV_FILE="${APP_DIR}/.env"
DB_URI_VAL=""
if [ -f "${ENV_FILE}" ]; then
    DB_URI_VAL=$(grep -E '^ITSM_DATABASE_URI=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)
fi
[ -z "${DB_URI_VAL}" ] && echo "[FATAL] .env 未配置 ITSM_DATABASE_URI" && exit 1

echo "停止服务..."
systemctl stop itsm 2>/dev/null || true

# ==================== PostgreSQL 分支 ====================
if [[ "${DB_URI_VAL}" == postgresql* ]]; then
    if [[ "${BACKUP}" != *.dump ]]; then
        echo "[FATAL] 当前 .env 为 PostgreSQL，需要 itsm_pg_*.dump 备份"
        systemctl start itsm 2>/dev/null || true
        exit 1
    fi
    PG_USER=$(echo "${DB_URI_VAL}" | sed -E 's#^postgresql://([^:]+):.*#\1#')
    PG_DB=$(echo "${DB_URI_VAL}" | sed -E 's#.*/([^/?]+)$#\1#')
    PG_HOST=$(echo "${DB_URI_VAL}" | sed -E 's#^postgresql://[^@]+@([^:/]+).*#\1#')
    PG_PORT=$(echo "${DB_URI_VAL}" | sed -E 's#.*:([0-9]+)/.*#\1#')
    [ "${PG_PORT}" = "${DB_URI_VAL}" ] && PG_PORT="5432"
    export PGPASSWORD=$(echo "${DB_URI_VAL}" | sed -E 's#^postgresql://[^:]+:([^@]+)@.*#\1#')

    echo "[1/3] 恢复 PostgreSQL 库 ${PG_DB}（pg_restore --clean，整库重建）..."
    pg_restore --clean --if-exists --no-owner \
        -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${PG_DB}" "${BACKUP}"

    META="${BACKUP//itsm_pg_/itsm_meta_}"
    META="${META%.dump}.tar.gz"
    if [ -f "${META}" ]; then
        echo "[2/3] 还原密钥/.env 与业务文件目录: ${META}"
        tar -xzf "${META}" -C "${APP_DIR}"
        chown -R itsm:itsm "${APP_DIR}/.secret.key" "${APP_DIR}/.env" \
            "${APP_DIR}/reports" "${APP_DIR}/uploads" "${APP_DIR}/static/uploads" 2>/dev/null || true
    else
        echo "  [WARN] 未找到同时间戳 meta 包（${META}），密钥/文件目录未还原"
    fi

# ==================== SQLite 分支 ====================
elif [[ "${DB_URI_VAL}" == sqlite* ]]; then
    if [[ "${BACKUP}" != *.tar.gz ]]; then
        echo "[FATAL] 当前 .env 为 SQLite，需要 itsm_full_*.tar.gz 整包备份"
        systemctl start itsm 2>/dev/null || true
        exit 1
    fi
    echo "[1/3] 还原 SQLite 库 + 密钥 + 文件目录（整包解压）..."
    tar -xzf "${BACKUP}" -C "${APP_DIR}"
    chown -R itsm:itsm "${APP_DIR}/instance" "${APP_DIR}/.secret.key" "${APP_DIR}/.env" \
        "${APP_DIR}/reports" "${APP_DIR}/uploads" "${APP_DIR}/static/uploads" 2>/dev/null || true

else
    echo "[FATAL] 不支持的 ITSM_DATABASE_URI: ${DB_URI_VAL}"
    systemctl start itsm 2>/dev/null || true
    exit 1
fi

echo "[3/3] 启动服务..."
systemctl start itsm
systemctl status itsm --no-pager -l || true

echo ""
echo "============================================"
echo "  整机恢复完成（DB + 密钥/.env + 业务文件）"
echo "  如代码版本与备份不匹配，请 git checkout 对应版本后重启再验证。"
echo "============================================"
