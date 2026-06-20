#!/usr/bin/env bash
# ============================================================
# ITSM 数据库迁移脚本
# 由 update.sh 自动调用
# 行为：加载 .env 后调 init_db()（内部跑 flask db upgrade 同步 schema + seed）
#       init_db 内部幂等，可重复执行；SQLite/PG 通用。
# ============================================================
set -euo pipefail

APP_DIR="${1:-/opt/itsm}"
VENV="${APP_DIR}/venv"
ENV_FILE="${APP_DIR}/.env"

echo "[migrate] 加载 .env 并调 init_db() 同步 schema + seed"
cd "${APP_DIR}"

# 从 .env 读必要环境变量（systemd 也通过 EnvironmentFile 注入，这里脚本直跑时补齐）
SECRET_KEY_VAL=""
DB_URI_VAL=""
if [ -f "${ENV_FILE}" ]; then
    SECRET_KEY_VAL=$(grep -E '^ITSM_SECRET_KEY=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)
    DB_URI_VAL=$(grep -E '^ITSM_DATABASE_URI=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)
fi

# SQLite：迁移前对 db 文件做快照兜底；PG：跳过（备份走 backup.sh 的 pg_dump）
if [ -n "${DB_URI_VAL}" ] && [[ "${DB_URI_VAL}" == sqlite* ]]; then
    DB_PATH="${DB_URI_VAL#sqlite:///}"
    if [ -f "${DB_PATH}" ]; then
        TS=$(date +%Y%m%d_%H%M%S)
        cp "${DB_PATH}" "${APP_DIR}/backups/itsm.db.pre_migrate_${TS}" 2>/dev/null && \
            echo "[migrate] SQLite 快照: backups/itsm.db.pre_migrate_${TS}" || true
    fi
fi

export ITSM_SECRET_KEY="${SECRET_KEY_VAL}"
export ITSM_ENV=production
export FLASK_ENV=production
[ -n "${DB_URI_VAL}" ] && export ITSM_DATABASE_URI="${DB_URI_VAL}"

"${VENV}/bin/python" -c "from app import init_db; init_db(); print('[migrate] OK schema + seed 已同步')"
