#!/usr/bin/env bash
# ============================================================
# ITSM PostgreSQL → SQLite 紧急回滚（Ubuntu 24）
# 用法: sudo bash pg-rollback.sh [/path/to/app]
# 默认: APP_DIR=/home/itsm-system_20260614
#
# 行为：把 .env 的 ITSM_DATABASE_URI 恢复为迁移前的 SQLite，
#       重启服务即切回 SQLite（迁移前的 SQLite 文件原样保留，数据未动）。
#       PG 库保留不动，需手动清理时见末尾提示。
# ============================================================
set -euo pipefail

APP_DIR="${1:-/home/itsm-system_20260614}"
ENV_FILE="${APP_DIR}/.env"
SQLITE_DB="${APP_DIR}/instance/itsm.db"
VENV="${APP_DIR}/venv"

echo "============================================"
echo "  ITSM PostgreSQL → SQLite 回滚"
echo "  应用目录: ${APP_DIR}"
echo "============================================"

if [ "$(id -u)" -ne 0 ]; then
    echo "[FATAL] 请用 sudo 运行"; exit 1
fi
if [ ! -f "${ENV_FILE}" ]; then
    echo "[FATAL] .env 不存在: ${ENV_FILE}"; exit 1
fi
if [ ! -f "${SQLITE_DB}" ]; then
    echo "[FATAL] SQLite 文件不存在: ${SQLITE_DB}（无法回退）"; exit 1
fi

# 确认当前确实是 PG
if ! grep -qE '^ITSM_DATABASE_URI=postgresql://' "${ENV_FILE}"; then
    echo "[WARN] .env 当前 ITSM_DATABASE_URI 不是 postgresql://，似乎未迁移或已回滚"
    grep -E '^#?ITSM_DATABASE_URI=' "${ENV_FILE}" || true
    read -rp "仍要继续恢复 SQLite URI? (输入 yes 继续): " CONFIRM
    [ "${CONFIRM}" = "yes" ] || { echo "已取消"; exit 0; }
fi

echo ""
echo "即将把数据库切回 SQLite（PG 库保留不动，数据不丢）。"
read -rp "确认回滚? (输入 yes 继续): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
    echo "已取消"; exit 0
fi

echo ""
echo "[1/4] 停止服务..."
systemctl stop itsm || true

echo "[2/4] 恢复 .env 的 ITSM_DATABASE_URI 为 SQLite..."
# 取消注释迁移前的 SQLite 行；若无注释行则写默认
if grep -qE '^# ITSM_DATABASE_URI=' "${ENV_FILE}"; then
    sed -i 's|^# ITSM_DATABASE_URI=|ITSM_DATABASE_URI=|' "${ENV_FILE}"
    # 删掉迁移时追加的 PG 行
    sed -i '/^ITSM_DATABASE_URI=postgresql:\/\//d' "${ENV_FILE}"
else
    # 没有注释行，写默认 SQLite URI
    sed -i '/^ITSM_DATABASE_URI=/d' "${ENV_FILE}"
    echo "ITSM_DATABASE_URI=sqlite:///${APP_DIR}/instance/itsm.db" >> "${ENV_FILE}"
fi
# 清理迁移时写的提示注释行
sed -i '/^# 迁移前 SQLite URI/d' "${ENV_FILE}"
echo "  当前 URI: $(grep -E '^ITSM_DATABASE_URI=' "${ENV_FILE}")"

echo "[3/4] 启动服务..."
systemctl start itsm
sleep 3
if systemctl is-active --quiet itsm; then
    echo "  itsm 服务已运行（SQLite 模式）"
else
    echo "[FAIL] 服务未起来，查日志: journalctl -u itsm -n 50"; exit 1
fi

echo "[4/4] 自检..."
SECRET_KEY_VAL=$(grep -E '^ITSM_SECRET_KEY=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)
ITSM_SECRET_KEY="${SECRET_KEY_VAL}" ITSM_ENV=production FLASK_ENV=production \
  "${VENV}/bin/python" - "${APP_DIR}" <<'PYEOF'
import sys, os
app_dir = sys.argv[1]; os.chdir(app_dir)
from app import app, db
with app.app_context():
    d = db.engine.dialect.name
    print(f"  当前 dialect: {d}")
    assert d == 'sqlite', '仍连 PG！回滚未生效'
    print("  已切回 SQLite")
PYEOF

echo ""
echo "============================================"
echo "  回滚完成，已切回 SQLite"
echo "============================================"
echo ""
echo "  PG 库保留未动。如确认不再需要，可手动清理："
echo "    sudo -u postgres dropdb itsm"
echo "    sudo -u postgres dropuser itsm"
echo "  导出包在 backups/pre_pg_migration_*.zip，确认无误后可删。"
