#!/usr/bin/env bash
# ============================================================
# ITSM 在线更新脚本
# 用法: sudo bash update.sh
# ============================================================
set -euo pipefail

APP_DIR="/opt/itsm"
VENV="${APP_DIR}/venv"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=== ITSM 更新 ${TIMESTAMP} ==="

# ---- 1. 备份数据库 ----
echo "[1/6] 备份数据库..."
mkdir -p "${APP_DIR}/backups"
if [ -f "${APP_DIR}/instance/itsm.db" ]; then
    cp "${APP_DIR}/instance/itsm.db" "${APP_DIR}/backups/itsm.db.pre_update_${TIMESTAMP}"
    echo "  备份已保存: backups/itsm.db.pre_update_${TIMESTAMP}"
else
    echo "  数据库文件不存在，跳过备份"
fi

# ---- 2. 保留本地修改 ----
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
    echo "  运行数据库迁移..."
    bash "${APP_DIR}/scripts/migrate.sh"
fi

# ---- 7. 重启服务 ----
echo "[6/6] 重启服务..."
systemctl reload itsm

echo "=== 更新完成 ==="
