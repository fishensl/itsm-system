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
# unzip：Vue 构建产物解压依赖（部分最小化系统未预装）
if ! dpkg -s unzip >/dev/null 2>&1; then
    apt-get install -y -qq unzip
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

# 部署 zip：校验完整性 + index.html 存在后，临时目录 → 原子替换
deploy_vue_dist() {
    local zip_file="$1" tmp_dir
    if [ ! -f "${zip_file}" ] || ! unzip -t -q "${zip_file}" >/dev/null 2>&1; then
        echo "  [WARN] vue-dist zip 缺失或校验失败: ${zip_file}"
        return 1
    fi
    tmp_dir="${VUE_DIST_DIR}.new"
    rm -rf "${tmp_dir}" && mkdir -p "${tmp_dir}"
    unzip -o -q "${zip_file}" -d "${tmp_dir}"
    rm -f "${zip_file}"
    if [ ! -f "${tmp_dir}/index.html" ]; then
        echo "  [WARN] vue-dist 缺少 index.html，取消部署"
        rm -rf "${tmp_dir}"
        return 1
    fi
    rm -rf "${VUE_DIST_DIR}" && mv "${tmp_dir}" "${VUE_DIST_DIR}"
    echo "  [OK] Vue 构建产物已部署（vue-dist）"
    return 0
}

VUE_DEPLOYED=false
# 0) 本地手动包优先（网络被墙时管理员 scp 上传到 backups/vue-dist-manual.zip）
LOCAL_ZIP="${APP_DIR}/backups/vue-dist-manual.zip"
if [ -f "${LOCAL_ZIP}" ]; then
    echo "  [INFO] 发现本地手动包 backups/vue-dist-manual.zip，优先部署..."
    if deploy_vue_dist "${LOCAL_ZIP}"; then
        VUE_DEPLOYED=true
        mv "${LOCAL_ZIP}" "${LOCAL_ZIP}.used.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || rm -f "${LOCAL_ZIP}"
    fi
fi
# 1) gh CLI 拉取
if [ "${VUE_DEPLOYED}" != "true" ] && command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    if gh release download vue-dist --pattern 'itsm-vue-dist.zip' --dir /tmp/itsm_vue --clobber 2>/dev/null && \
       [ -f /tmp/itsm_vue/itsm-vue-dist.zip ]; then
        deploy_vue_dist /tmp/itsm_vue/itsm-vue-dist.zip && VUE_DEPLOYED=true || true
    else
        echo "  [WARN] gh 拉取 vue-dist 失败"
    fi
    rm -rf /tmp/itsm_vue
fi
# 2) curl 兜底（公共仓库免认证，无需 gh；直连失败走 ghproxy 镜像）
if [ "${VUE_DEPLOYED}" != "true" ] && command -v curl >/dev/null 2>&1; then
    REPO_URL=$(git -C "${APP_DIR}" remote get-url origin 2>/dev/null | sed 's/\.git$//')
    if [ -n "${REPO_URL}" ]; then
        RELEASE_URL="${REPO_URL}/releases/download/vue-dist/itsm-vue-dist.zip"
        echo "  [INFO] 改用 curl 拉取 vue-dist（${RELEASE_URL}）..."
        rm -f /tmp/itsm-vue-dist.zip
        if ! curl -fL --connect-timeout 20 --max-time 300 -o /tmp/itsm-vue-dist.zip \
                "${RELEASE_URL}" 2>/dev/null; then
            echo "  [INFO] 直连失败，尝试 ghproxy 镜像..."
            if ! curl -fL --connect-timeout 20 --max-time 300 -o /tmp/itsm-vue-dist.zip \
                    "https://ghproxy.com/${RELEASE_URL}" 2>/dev/null; then
                echo "  [WARN] curl 拉取 vue-dist 失败（直连与 ghproxy 均不可达，可稍后重跑 update.sh）"
            fi
        fi
        if [ -s /tmp/itsm-vue-dist.zip ]; then
            deploy_vue_dist /tmp/itsm-vue-dist.zip && VUE_DEPLOYED=true || true
        fi
        rm -f /tmp/itsm-vue-dist.zip
    fi
fi
# 3) 本地构建（服务器需 Node）
if [ "${VUE_DEPLOYED}" != "true" ] && [ -d "${APP_DIR}/frontend" ] && command -v npm >/dev/null 2>&1; then
    echo "  [WARN] 拉取失败，改用本地构建（服务器需 Node）..."
    (cd "${APP_DIR}/frontend" && npm ci --no-audit --no-fund 2>/dev/null && npm run build 2>/dev/null && \
     cp -r dist/* "${VUE_DIST_DIR}/") && VUE_DEPLOYED=true && echo "  [OK] 本地构建完成" || echo "  [WARN] 本地构建失败"
fi
# 4) 最终检查：Vue 产物缺失时明确告警（默认界面为 Vue 时 /app/* 会 404）
if [ "${VUE_DEPLOYED}" != "true" ]; then
    echo "  [WARN] Vue 产物部署失败（无 gh/curl/Node 或 vue-dist 未发布），SSR 保底"
    if [ ! -f "${VUE_DIST_DIR}/index.html" ]; then
        echo "  [FATAL] static/app 无 Vue 产物：默认界面为 Vue 时 /app/* 将 404！"
        echo "         请先确认 CI 完成并发布 vue-dist（GitHub Actions frontend job），再重跑本脚本"
    fi
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
