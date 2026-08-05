#!/usr/bin/env bash
# ============================================================
# 工作机离线发布包生成器
# 用法: bash scripts/make-release.sh
#
# 生成两个文件（scp 到服务器 backups/ 后跑 update.sh 即完成离线更新）：
#   backups/itsm-update.bundle   代码包（git bundle，含 master 全部提交，秒级应用）
#   backups/vue-dist-manual.zip  前端构建产物（update.sh 优先部署）
#
# 只需"生成"这一次需要能访问 GitHub；服务器应用全程零网络。
# ============================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${APP_DIR}"
OUT_DIR="${APP_DIR}/backups"
mkdir -p "${OUT_DIR}"

echo "============================================"
echo "  ITSM 离线发布包生成  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# ---- 1. 代码包：git bundle ----
echo ""
echo "[1/2] 生成代码包 backups/itsm-update.bundle ..."
# 尽力同步远端（失败时用本地 master；仅出包需要网络）
git fetch origin master 2>/dev/null || echo "  [WARN] 远端同步失败，使用本地 master（可能落后）"
git bundle create "${OUT_DIR}/itsm-update.bundle" master
echo "  [OK] bundle 已生成：$(git log --oneline -1 master)"

# ---- 2. 前端构建产物 ----
echo ""
echo "[2/2] 构建前端并打包 backups/vue-dist-manual.zip ..."
if [ ! -d "${APP_DIR}/frontend" ]; then
    echo "  [WARN] 无 frontend 目录，跳过前端打包（保持现有 static/app 不变）"
    exit 0
fi

(cd "${APP_DIR}/frontend" && npm run build 2>/dev/null || { echo "  [WARN] npm build 失败，改用现有 dist 打包"; true; })

PY="python3"; command -v python3 >/dev/null 2>&1 || PY="python"
rm -f "${OUT_DIR}/vue-dist-manual.zip"
"${PY}" - "${OUT_DIR}/vue-dist-manual.zip" <<'PY'
import sys
import zipfile
import os

out = sys.argv[1]
dist = os.path.join('frontend', 'dist')
if not os.path.isdir(dist):
    print('[WARN] frontend/dist 不存在，前端包未生成')
    sys.exit(0)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, _dirs, files in os.walk(dist):
        for f in files:
            full = os.path.join(root, f)
            zf.write(full, os.path.relpath(full, dist))
print('[OK] 前端包已生成')
PY

echo ""
echo "============================================"
echo "  发布包已生成，scp 到服务器后执行 update.sh："
echo "    scp ${OUT_DIR}/itsm-update.bundle ${OUT_DIR}/vue-dist-manual.zip root@<服务器>:/home/itsm-system_20260614/backups/"
echo "    sudo bash /home/itsm-system_20260614/scripts/update.sh /home/itsm-system_20260614"
echo "============================================"
ls -lh "${OUT_DIR}/itsm-update.bundle" "${OUT_DIR}/vue-dist-manual.zip"
