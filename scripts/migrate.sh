#!/usr/bin/env bash
# ============================================================
# ITSM 数据库迁移脚本
# 由 update.sh 自动调用
# 行为：调 init_db() 完成 schema 同步 + seed
#       （init_db 内部幂等，可重复执行）
# ============================================================
set -euo pipefail

APP_DIR="/opt/itsm"
DB="${APP_DIR}/instance/itsm.db"

echo "[migrate] 调 init_db() 同步 schema + seed"
cd "${APP_DIR}"
"${APP_DIR}/venv/bin/python" -c "from app import init_db; init_db()"
