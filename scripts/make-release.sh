#!/usr/bin/env bash
# ============================================================
# 工作机离线发布包生成器
# 用法: bash scripts/make-release.sh
#
# 生成代码包、前端包、各自校验和及同版本 manifest：
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

# bundle 取 master，前端产物取当前工作树；二者必须严格来自同一、干净提交。
# 推荐在 `git worktree add --detach <dir> master` 创建的干净发布工作树内执行。
if ! git diff --quiet || ! git diff --cached --quiet || \
   [ -n "$(git ls-files --others --exclude-standard)" ]; then
    echo "[FATAL] 发布工作树不干净，拒绝生成可能前后端错配的发布包" >&2
    git status --short >&2
    exit 1
fi
RELEASE_COMMIT=$(git rev-parse HEAD)
MASTER_COMMIT=$(git rev-parse master)
if [ "${RELEASE_COMMIT}" != "${MASTER_COMMIT}" ]; then
    echo "[FATAL] 当前 HEAD 与 master 不一致，拒绝混合打包" >&2
    echo "        HEAD=${RELEASE_COMMIT} master=${MASTER_COMMIT}" >&2
    exit 1
fi

echo "============================================"
echo "  ITSM 离线发布包生成  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

# ---- 1. 代码包：git bundle ----
echo ""
echo "[1/3] 生成代码包 backups/itsm-update.bundle ..."
# 尽力同步远端（失败时用本地 master；仅出包需要网络）
git fetch origin master 2>/dev/null || echo "  [WARN] 远端同步失败，使用本地 master（可能落后）"
git bundle create "${OUT_DIR}/itsm-update.bundle" master
sha256sum "${OUT_DIR}/itsm-update.bundle" | awk '{print $1}' > "${OUT_DIR}/itsm-update.bundle.sha256"
echo "  [OK] bundle 已生成：$(git log --oneline -1 master)"

# ---- 2. 前端构建产物 ----
echo ""
echo "[2/3] 构建前端并打包 backups/vue-dist-manual.zip ..."
if [ ! -d "${APP_DIR}/frontend" ]; then
    echo "  [FATAL] 无 frontend 目录，不能生成同版本发布包" >&2
    exit 1
fi

if ! (cd "${APP_DIR}/frontend" && npm ci --no-audit --no-fund && npm run build); then
    echo "  [FATAL] 前端构建失败，拒绝打包旧 dist" >&2
    exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "[FATAL] 前端构建修改了已跟踪源文件，请先提交生成结果后重新出包" >&2
    git status --short >&2
    exit 1
fi

PY="${PYTHON:-}"
if [ -z "${PY}" ]; then
    for candidate in \
        "${APP_DIR}/.venv/Scripts/python.exe" \
        "${APP_DIR}/.venv/bin/python" \
        python3 python; do
        if [[ "${candidate}" == */* ]]; then
            [ -x "${candidate}" ] || continue
        elif ! command -v "${candidate}" >/dev/null 2>&1; then
            continue
        fi
        PY="${candidate}"
        break
    done
fi
if [ -z "${PY}" ]; then
    echo "  [FATAL] 未找到 Python；请设置 PYTHON=/path/to/python 后重试" >&2
    exit 1
fi
rm -f "${OUT_DIR}/vue-dist-manual.zip"
"${PY}" - "${OUT_DIR}/vue-dist-manual.zip" <<'PY'
import sys
import zipfile
import os

out = sys.argv[1]
dist = os.path.join('frontend', 'dist')
if not os.path.isdir(dist):
    print('[FATAL] frontend/dist 不存在')
    sys.exit(1)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, _dirs, files in os.walk(dist):
        for f in files:
            full = os.path.join(root, f)
            zf.write(full, os.path.relpath(full, dist))
print('[OK] 前端包已生成')
PY
sha256sum "${OUT_DIR}/vue-dist-manual.zip" | awk '{print $1}' > "${OUT_DIR}/vue-dist-manual.zip.sha256"

# ---- 3. 同版本 manifest：防止误把不同提交的 bundle 与前端包混用 ----
echo "[3/3] 生成同版本发布 manifest ..."
BUNDLE_SHA=$(tr -d '[:space:]' < "${OUT_DIR}/itsm-update.bundle.sha256")
VUE_SHA=$(tr -d '[:space:]' < "${OUT_DIR}/vue-dist-manual.zip.sha256")
{
    printf 'commit=%s\n' "${RELEASE_COMMIT}"
    printf 'bundle_sha256=%s\n' "${BUNDLE_SHA}"
    printf 'vue_sha256=%s\n' "${VUE_SHA}"
} > "${OUT_DIR}/itsm-release-manifest.txt"

echo ""
echo "============================================"
echo "  发布包已生成，scp 到服务器后执行 update.sh："
echo "    scp ${OUT_DIR}/itsm-update.bundle* ${OUT_DIR}/vue-dist-manual.zip* ${OUT_DIR}/itsm-release-manifest.txt root@<服务器>:/home/itsm-system_20260614/backups/"
echo "    sudo bash /home/itsm-system_20260614/scripts/update.sh /home/itsm-system_20260614"
echo "============================================"
ls -lh "${OUT_DIR}/itsm-update.bundle"* "${OUT_DIR}/vue-dist-manual.zip"* \
    "${OUT_DIR}/itsm-release-manifest.txt"
