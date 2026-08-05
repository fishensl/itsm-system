#!/usr/bin/env bash
# ============================================================
# 工作机一键推送更新：scp 发布包 → 远程执行 update.sh（全自动，零手动步骤）
# 前置：已配置 ssh 免密（一次性：type ~/.ssh/id_rsa_test.pub | ssh root@<服务器> "cat >> ~/.ssh/authorized_keys"）
# 用法: bash scripts/push-update.sh [root@服务器IP] [远程应用目录]
# 默认: root@172.16.123.124 /home/itsm-system_20260614
# ============================================================
set -euo pipefail

SERVER="${1:-root@172.16.123.124}"
REMOTE_DIR="${2:-/home/itsm-system_20260614}"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "============================================"
echo "  ITSM 一键推送更新  → ${SERVER}"
echo "============================================"

# 1. 确认发布包存在
if [ ! -f "${APP_DIR}/backups/itsm-update.bundle" ] || [ ! -f "${APP_DIR}/backups/vue-dist-manual.zip" ]; then
    echo "[FATAL] 发布包缺失，请先执行 bash scripts/make-release.sh"
    exit 1
fi

# 2. 传输发布包（scp，内网秒级）
echo "[1/2] 传输发布包..."
scp -o ConnectTimeout=10 "${APP_DIR}/backups/itsm-update.bundle" "${APP_DIR}/backups/vue-dist-manual.zip" \
    "${SERVER}:${REMOTE_DIR}/backups/"

# 3. 远程执行更新（bundle 应用 + 前端部署 + 迁移 + 重启，全程本地文件零网络）
echo "[2/2] 远程执行 update.sh ..."
ssh -o ConnectTimeout=10 "${SERVER}" "sudo bash ${REMOTE_DIR}/scripts/update.sh ${REMOTE_DIR}"

echo ""
echo "部署完成！浏览器硬刷新（Ctrl+Shift+R）后验证：巡检审核清单 / 巡检记录 500"
