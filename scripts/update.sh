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
# 统一生产分支为 master：CI 仅 master 发布 vue-dist，必须同源拉取（避免 main/master 错位）
git pull origin master

# ---- 4. 恢复本地修改 ----
echo "[4/6] 恢复本地修改..."
git stash pop 2>/dev/null || true

# ---- 5. 更新依赖 ----
echo "[5/6] 更新 Python 依赖..."
# cairosvg（SVG→PDF，V20.3 在线拓扑自动生成 PDF）需要 libcairo2 系统库
if ! dpkg -s libcairo2 >/dev/null 2>&1; then
    apt-get install -y -qq libcairo2
fi
"${VENV}/bin/pip" install -r "${APP_DIR}/requirements.txt" -q

# ---- 5.5 drawio webapp（V20 在线拓扑，gitignore 不入库，缺失则补拉）----
if [ ! -f "${APP_DIR}/static/vendor/drawio/index.html" ]; then
    echo "[5.5/6] 拉取 drawio webapp..."
    bash "${APP_DIR}/scripts/fetch-drawio.sh" || echo "  [WARN] drawio 拉取失败，可稍后重跑"
fi

# ---- 5.6 Vue 前端构建产物（CI 发布到 GitHub Release vue-dist，服务器免 Node）----
echo "[5.6/6] 部署 Vue 前端构建产物..."
VUE_DIST_DIR="${APP_DIR}/static/app"
mkdir -p "${VUE_DIST_DIR}"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    if gh release download vue-dist --pattern 'itsm-vue-dist.zip' --dir /tmp/itsm_vue --clobber 2>/dev/null; then
        rm -rf "${VUE_DIST_DIR}" && mkdir -p "${VUE_DIST_DIR}"
        cd /tmp/itsm_vue && unzip -o -q itsm-vue-dist.zip -d "${VUE_DIST_DIR}" && rm -rf /tmp/itsm_vue
        echo "  [OK] Vue 构建产物已部署（release vue-dist）"
    else
        echo "  [WARN] 拉取 vue-dist release 失败（首次发布前 Vue 不可用，SSR 保底）"
    fi
elif [ -d "${APP_DIR}/frontend" ] && command -v npm >/dev/null 2>&1; then
    echo "  [WARN] 无 gh CLI，改用本地构建（服务器需 Node）..."
    (cd "${APP_DIR}/frontend" && npm ci --no-audit --no-fund 2>/dev/null && npm run build 2>/dev/null && \
     cp -r dist/* "${VUE_DIST_DIR}/") && echo "  [OK] 本地构建完成" || echo "  [WARN] 本地构建失败，SSR 保底"
else
    echo "  [WARN] 无 gh 且无 Node，跳过 Vue 部署（SSR 保底）"
fi

# ---- 6. 数据库迁移 + schema 同步 ----
# init_db() 内部幂等：跑 flask db upgrade（Alembic）同步 schema + seed_all() 写权限/角色。
# SQLite/PG 通用；ITSM_DATABASE_URI 从 .env 读取以连对库。
echo "[6/6] 数据库 schema 同步..."
cd "${APP_DIR}"
ITSM_SECRET_KEY="$(grep -E '^ITSM_SECRET_KEY=' .env 2>/dev/null | cut -d= -f2-)" \
ITSM_DATABASE_URI="$(grep -E '^ITSM_DATABASE_URI=' .env 2>/dev/null | cut -d= -f2-)" \
ITSM_ENV=production \
FLASK_ENV=production \
"${VENV}/bin/python" -c "from app import create_app, init_db; init_db(create_app()); print('[OK] schema + seed 已同步')"

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
