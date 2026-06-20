#!/usr/bin/env bash
# ============================================================
# ITSM 在线更新脚本
# 用法: sudo bash update.sh [/path/to/app]
# 默认: /opt/itsm
# ============================================================
set -euo pipefail

APP_DIR="${1:-/opt/itsm}"
VENV="${APP_DIR}/venv"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "============================================"
echo "  ITSM 在线更新  ${TIMESTAMP}"
echo "============================================"

# 记录更新前版本
OLD_VERSION="(未知)"
if [ -f "${APP_DIR}/VERSION" ]; then
    OLD_VERSION=$(cat "${APP_DIR}/VERSION")
fi
echo "当前版本: ${OLD_VERSION}"

# ---- 1. 备份数据库 ----
echo ""
echo "[1/6] 备份数据库..."
mkdir -p "${APP_DIR}/backups"
if [ -f "${APP_DIR}/instance/itsm.db" ]; then
    cp "${APP_DIR}/instance/itsm.db" "${APP_DIR}/backups/itsm.db.pre_update_${TIMESTAMP}"
    echo "  已保存: backups/itsm.db.pre_update_${TIMESTAMP}"
else
    echo "  数据库不存在，跳过"
fi

# ---- 2. 暂存本地修改 ----
echo "[2/6] 暂存本地修改..."
cd "${APP_DIR}"
git stash push --include-untracked -m "auto-stash-${TIMESTAMP}" 2>/dev/null || true

# ---- 3. 拉取最新代码 ----
echo "[3/6] 拉取最新代码..."
git pull origin main 2>/dev/null || git pull origin master

# ---- 4. 恢复本地修改 ----
echo "[4/6] 恢复本地修改..."
git stash pop 2>/dev/null || true

# ---- 5. 更新依赖 ----
echo "[5/6] 更新 Python 依赖..."
"${VENV}/bin/pip" install -r "${APP_DIR}/requirements.txt" -q

# ---- 6. 数据库迁移 + schema 同步 ----
# init_db() 内部幂等：跑 flask db upgrade（Alembic）同步 schema + seed_all() 写权限/角色。
# SQLite/PG 通用；ITSM_DATABASE_URI 从 .env 读取以连对库。
echo "[6/6] 数据库 schema 同步..."
cd "${APP_DIR}"
ITSM_SECRET_KEY="$(grep -E '^ITSM_SECRET_KEY=' .env 2>/dev/null | cut -d= -f2-)" \
ITSM_DATABASE_URI="$(grep -E '^ITSM_DATABASE_URI=' .env 2>/dev/null | cut -d= -f2-)" \
ITSM_ENV=production \
FLASK_ENV=production \
"${VENV}/bin/python" -c "from app import init_db; init_db(); print('[OK] schema + seed 已同步')"

# ---- 6.5 重新安装 systemd service（路径自适配）----
echo "[6.5/7] 重新安装 systemd service..."
if [ -f "${APP_DIR}/scripts/lib-install.sh" ]; then
    # shellcheck disable=SC1091
    source "${APP_DIR}/scripts/lib-install.sh"
    install_service "${APP_DIR}" || {
        echo "[FATAL] service 文件安装失败" >&2
        exit 1
    }
fi

# ---- 7. 显示版本变更 ----
NEW_VERSION="(未知)"
if [ -f "${APP_DIR}/VERSION" ]; then
    NEW_VERSION=$(cat "${APP_DIR}/VERSION")
fi

echo ""
echo "============================================"
echo "  版本变更: ${OLD_VERSION} → ${NEW_VERSION}"
echo "============================================"

# ---- 7. 重启服务 ----
echo ""
echo "[最后] 重启服务..."
systemctl restart itsm
systemctl --no-pager -l status itsm || true

echo "更新完成！"
