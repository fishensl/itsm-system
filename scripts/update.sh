#!/usr/bin/env bash
# ============================================================
# ITSM 在线更新脚本
# 用法: sudo bash update.sh
# ============================================================
set -euo pipefail

APP_DIR="/opt/itsm"
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
git pull origin main

# ---- 4. 恢复本地修改 ----
echo "[4/6] 恢复本地修改..."
git stash pop 2>/dev/null || true

# ---- 5. 更新依赖 ----
echo "[5/6] 更新 Python 依赖..."
"${VENV}/bin/pip" install -r "${APP_DIR}/requirements.txt" -q

# ---- 6. 数据库迁移 ----
if [ -f "${APP_DIR}/scripts/migrate.sh" ]; then
    bash "${APP_DIR}/scripts/migrate.sh"
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

# ---- 8. 重启服务 ----
echo ""
echo "[最后] 重启服务..."
systemctl reload itsm

echo "更新完成！"
