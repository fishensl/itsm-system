#!/usr/bin/env bash
# ============================================================
# ITSM 数据库迁移脚本（预留）
# update.sh 会在更新后自动调用此脚本
# ============================================================
set -euo pipefail

APP_DIR="/opt/itsm"
DB="${APP_DIR}/instance/itsm.db"

echo "数据库迁移: 无需操作"

# 示例 — 手动 SQL 迁移:
# if [ -f "${DB}" ]; then
#     sqlite3 "${DB}" "ALTER TABLE devices ADD COLUMN new_field TEXT DEFAULT '';" 2>/dev/null || true
# fi

# 如果用 Flask-Migrate，替换为:
# cd "${APP_DIR}"
# "${APP_DIR}/venv/bin/flask" db upgrade
