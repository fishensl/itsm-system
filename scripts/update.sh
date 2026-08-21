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

if [ -f "${APP_DIR}/scripts/lib-release.sh" ]; then
    # shellcheck disable=SC1091
    source "${APP_DIR}/scripts/lib-release.sh"
else
    # 首次从不含共享库的旧版本自更新时不阻断更新；健康失败仍会明确进入人工回滚。
    restore_previous_frontend() { return 1; }
fi

echo "============================================"
echo "  ITSM 在线更新  ${TIMESTAMP}"
echo "============================================"

# 记录更新前版本
OLD_VERSION="(未知)"
if [ -f "${APP_DIR}/VERSION" ]; then
    OLD_VERSION=$(cat "${APP_DIR}/VERSION")
fi
echo "当前版本: ${OLD_VERSION}"

# ---- 1. 生成完整配对备份 ----
echo ""
echo "[1/6] 备份数据库..."
bash "${APP_DIR}/scripts/backup.sh" "${APP_DIR}"

# ---- 2. 已跟踪工作区必须干净 ----
echo "[2/6] 检查工作区..."
cd "${APP_DIR}"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "[FATAL] 工作区存在已跟踪文件修改，拒绝自动 stash/覆盖" >&2
    git status --short --untracked-files=no
    exit 1
fi
# 未跟踪运行数据由 .gitignore 管理；若与新版本文件冲突，git pull 自身会安全拒绝。

# 旧版本曾把 Fernet 历史密钥误纳入 Git。更新到“停止跟踪”提交时 Git 会删除
# 该工作树文件，因此必须先在仓库外（backups/ 已被 Git 忽略）保存 root-only 副本。
mapfile -t TRACKED_KEY_BACKUPS < <(git ls-files '.secret.key.bak.*')
if [ "${#TRACKED_KEY_BACKUPS[@]}" -gt 0 ]; then
    KEY_ARCHIVE_DIR="${APP_DIR}/backups/key-archive"
    install -d -m 0700 "${KEY_ARCHIVE_DIR}"
    for tracked_key in "${TRACKED_KEY_BACKUPS[@]}"; do
        if [ -f "${APP_DIR}/${tracked_key}" ]; then
            install -m 0600 "${APP_DIR}/${tracked_key}" \
                "${KEY_ARCHIVE_DIR}/$(basename "${tracked_key}")"
        fi
    done
    echo "  [OK] 已跟踪历史密钥已归档到 backups/key-archive（权限 600）"
fi

# ---- 公共：GitHub 多通道（git pull / vue-dist 下载共用） ----
# 代理列表：ITSM_PROXIES(逗号分隔) > ITSM_PROXY > 系统 https_proxy/http_proxy
ITSM_PROXY_LIST=""
[ -n "${ITSM_PROXIES:-}" ] && ITSM_PROXY_LIST="${ITSM_PROXIES}"
[ -z "${ITSM_PROXY_LIST}" ] && [ -n "${ITSM_PROXY:-}" ] && ITSM_PROXY_LIST="${ITSM_PROXY}"
[ -z "${ITSM_PROXY_LIST}" ] && [ -n "${https_proxy:-}${HTTPS_PROXY:-}" ] && ITSM_PROXY_LIST="${https_proxy:-${HTTPS_PROXY}}"
IFS=',' read -r -a ITSM_PROXY_ARRAY <<< "${ITSM_PROXY_LIST}"

# 镜像列表：前缀代理类（URL 前拼镜像域名）+ 域名替换类（ITSM_MIRRORS 可追加）
ITSM_MIRROR_PREFIX=(
    "https://gh-proxy.com"
    "https://ghfast.top"
    "https://ghproxy.net"
    "https://ghproxy.cc"
    "https://gh.ddlc.top"
    "https://github.moeyy.xyz"
    "https://hub.gitmirror.com"
)
ITSM_MIRROR_DOMAIN=(
    "https://kkgithub.com"
)
if [ -n "${ITSM_MIRRORS:-}" ]; then
    IFS=',' read -r -a _extra <<< "${ITSM_MIRRORS}"
    ITSM_MIRROR_PREFIX+=("${_extra[@]}")
fi

GITHUB_REPO_URL=$(git -C "${APP_DIR}" remote get-url origin 2>/dev/null | sed 's/\.git$//')
GITHUB_RELEASE_URL=""
GITHUB_RELEASE_SHA_URL=""
GITHUB_RELEASE_BASE=""
ITSM_AVAILABLE=()

# 探测 URL 可用性（Range 请求 1 字节，HTTP 200/206 即可用，每个 ≤10s）
probe_url() {
    curl -sfL -r 0-0 -o /dev/null --connect-timeout 5 --max-time 10 "$@" >/dev/null 2>&1
}

# 探测全部通道（代理/直连/镜像），可用项写入全局 ITSM_AVAILABLE（格式 kind|url）
probe_all_channels() {
    ITSM_AVAILABLE=()
    local p m
    for p in "${ITSM_PROXY_ARRAY[@]+"${ITSM_PROXY_ARRAY[@]}"}"; do
        [ -z "$p" ] && continue
        if probe_url "${GITHUB_RELEASE_URL}" --proxy "$p"; then
            ITSM_AVAILABLE+=("proxy|$p")
            echo "  [OK] 代理可用: $p"
        else
            echo "  [WARN] 代理不可达: $p"
        fi
    done
    if [ ${#ITSM_PROXY_ARRAY[@]} -eq 0 ] && probe_url "${GITHUB_RELEASE_URL}"; then
        ITSM_AVAILABLE+=("direct|")
        echo "  [OK] 直连可用"
    fi
    if [ "${ITSM_SKIP_MIRRORS:-0}" != "1" ]; then
        for m in "${ITSM_MIRROR_PREFIX[@]+"${ITSM_MIRROR_PREFIX[@]}"}"; do
            [ -z "$m" ] && continue
            if probe_url "${m}/${GITHUB_RELEASE_URL}"; then
                ITSM_AVAILABLE+=("mirror|${m}/${GITHUB_RELEASE_URL}")
                echo "  [OK] 镜像可用: $m"
            fi
        done
        for m in "${ITSM_MIRROR_DOMAIN[@]+"${ITSM_MIRROR_DOMAIN[@]}"}"; do
            [ -z "$m" ] && continue
            if probe_url "${m}/${GITHUB_RELEASE_BASE}"; then
                ITSM_AVAILABLE+=("mirror|${m}/${GITHUB_RELEASE_BASE}")
                echo "  [OK] 镜像可用: $m"
            fi
        done
    fi
}

# git pull：离线 bundle（本地文件，秒级应用，零网络）→ 直连（限时 60s，不再无限卡死）→ 代理 → 镜像 依次兜底
git_pull_with_fallback() {
    local branch="${1:-master}" p m repo_base bundle
    bundle="${APP_DIR}/backups/itsm-update.bundle"
    if [ -f "${bundle}" ]; then
        echo "  [INFO] 发现离线代码包 backups/itsm-update.bundle，本地应用..."
        if timeout 60 git pull "${bundle}" "${branch}" 2>/dev/null; then
            mv "${bundle}" "${bundle}.used.$(date +%Y%m%d_%H%M%S)" 2>/dev/null || rm -f "${bundle}"
            rm -f "${bundle}.sha256"
            echo "  [OK] 代码已更新（本地 bundle，零网络依赖）"
            return 0
        else
            echo "  [WARN] bundle 应用失败（可能已最新/损坏），继续网络拉取"
        fi
    fi
    if [ -n "${ITSM_PROXY_LIST}" ]; then
        export https_proxy="${ITSM_PROXY_ARRAY[0]}" http_proxy="${ITSM_PROXY_ARRAY[0]}"
        echo "  [INFO] git pull 使用代理: ${https_proxy}"
    fi
    if timeout 60 git pull origin "${branch}" 2>/dev/null; then
        return 0
    fi
    echo "  [WARN] git 直连拉取超时/失败，尝试代理/镜像拉取..."
    # 超时中断可能残留 index.lock，清理后重试
    rm -f "${APP_DIR}/.git/index.lock"
    for p in "${ITSM_PROXY_ARRAY[@]+"${ITSM_PROXY_ARRAY[@]}"}"; do
        [ -z "$p" ] && continue
        if timeout 120 git -c http.proxy="$p" pull origin "${branch}" 2>/dev/null; then
            echo "  [OK] 经代理完成 git pull: $p"
            return 0
        fi
    done
    for m in "${ITSM_MIRROR_PREFIX[@]+"${ITSM_MIRROR_PREFIX[@]}"}"; do
        [ -z "$m" ] && continue
        if timeout 120 git pull "${m}/${GITHUB_REPO_URL}" "${branch}" 2>/dev/null; then
            echo "  [OK] 经镜像完成 git pull: $m"
            return 0
        fi
    done
    repo_base="${GITHUB_REPO_URL#https://github.com/}"
    for m in "${ITSM_MIRROR_DOMAIN[@]+"${ITSM_MIRROR_DOMAIN[@]}"}"; do
        [ -z "$m" ] && continue
        if timeout 120 git pull "${m}/${repo_base}" "${branch}" 2>/dev/null; then
            echo "  [OK] 经镜像完成 git pull: $m"
            return 0
        fi
    done
    echo "  [WARN] git 拉取全部通道失败（网络受限），可稍后重跑 update.sh"
    return 1
}

# ---- 发布包完整性校验（离线包两个文件必须成对，缺一即中断） ----
if [ -f "${APP_DIR}/backups/itsm-update.bundle" ]; then
    for release_file in itsm-update.bundle.sha256 vue-dist-manual.zip \
        vue-dist-manual.zip.sha256 itsm-release-manifest.txt; do
        if [ ! -f "${APP_DIR}/backups/${release_file}" ]; then
            echo "[FATAL] 发布包不完整：缺少 backups/${release_file}" >&2
            exit 1
        fi
    done
    expected_bundle=$(tr -d '[:space:]' < "${APP_DIR}/backups/itsm-update.bundle.sha256")
    actual_bundle=$(sha256sum "${APP_DIR}/backups/itsm-update.bundle" | awk '{print $1}')
    if [ "${expected_bundle}" != "${actual_bundle}" ]; then
        echo "[FATAL] itsm-update.bundle SHA256 校验失败" >&2
        exit 1
    fi
    OFFLINE_MANIFEST="${APP_DIR}/backups/itsm-release-manifest.txt"
    OFFLINE_EXPECTED_COMMIT=$(awk -F= '$1 == "commit" {print $2; exit}' "${OFFLINE_MANIFEST}")
    manifest_bundle_sha=$(awk -F= '$1 == "bundle_sha256" {print $2; exit}' "${OFFLINE_MANIFEST}")
    manifest_vue_sha=$(awk -F= '$1 == "vue_sha256" {print $2; exit}' "${OFFLINE_MANIFEST}")
    expected_vue=$(tr -d '[:space:]' < "${APP_DIR}/backups/vue-dist-manual.zip.sha256")
    if ! [[ "${OFFLINE_EXPECTED_COMMIT}" =~ ^[0-9a-f]{40}$ ]] || \
       [ "${manifest_bundle_sha}" != "${actual_bundle}" ] || \
       [ "${manifest_vue_sha}" != "${expected_vue}" ]; then
        echo "[FATAL] 离线发布 manifest 与 bundle/前端校验和不匹配" >&2
        exit 1
    fi
fi

# ---- 3. 拉取最新代码 ----
echo "[3/6] 拉取最新代码..."
# 统一生产分支为 master：CI 仅 master 发布 vue-dist，必须同源拉取（避免 main/master 错位）
# git pull 限时执行，失败走代理/镜像兜底（不无限卡死）
if ! git_pull_with_fallback master; then
    echo "  [FATAL] 代码拉取失败，已在依赖、迁移和重启前停止" >&2
    exit 1
fi
# 兼容从旧版本自更新：git pull 后重新加载可能刚新增的发布恢复函数。
if [ -f "${APP_DIR}/scripts/lib-release.sh" ]; then
    # shellcheck disable=SC1091
    source "${APP_DIR}/scripts/lib-release.sh"
fi

BACKEND_COMMIT=$(git rev-parse HEAD)
if [ -n "${OFFLINE_EXPECTED_COMMIT:-}" ] && \
   [ "${BACKEND_COMMIT}" != "${OFFLINE_EXPECTED_COMMIT}" ]; then
    echo "[FATAL] 离线 bundle 应用后的 HEAD 与发布 manifest 不一致" >&2
    exit 1
fi
# 在线产物使用后端 HEAD 对应的唯一 Release，禁止滚动覆盖造成前后端错配。
RELEASE_TAG="vue-dist-${BACKEND_COMMIT}"
GITHUB_RELEASE_URL="${GITHUB_REPO_URL}/releases/download/${RELEASE_TAG}/itsm-vue-dist.zip"
GITHUB_RELEASE_SHA_URL="${GITHUB_RELEASE_URL}.sha256"
GITHUB_RELEASE_BASE="${GITHUB_RELEASE_URL#https://github.com/}"

# ---- 4. 确认代码版本 ----
echo "[4/6] 当前代码: $(git rev-parse --short HEAD)"

# ---- 5. 更新依赖 ----
echo "[5/6] 更新 Python 依赖..."
# cairosvg（SVG→PDF，V20.3 在线拓扑自动生成 PDF）需要 libcairo2 系统库
if ! dpkg -s libcairo2 >/dev/null 2>&1; then
    apt-get install -y -qq libcairo2
fi
# unzip：离线 Vue 构建产物的唯一系统解压依赖；不再为本地构建无条件安装 zip。
if ! dpkg -s unzip >/dev/null 2>&1; then
    apt-get install -y -qq unzip
fi
if [ -n "${OFFLINE_EXPECTED_COMMIT:-}" ]; then
    # 离线发布禁止访问 PyPI；本批依赖未变化时由已安装包直接满足。
    "${VENV}/bin/pip" install --no-index -r "${APP_DIR}/requirements.txt" -q
else
    "${VENV}/bin/pip" install -r "${APP_DIR}/requirements.txt" -q
fi

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
    local zip_file="$1" checksum_file="$2" tmp_dir previous_dir expected_sha actual_sha
    if [ ! -f "${zip_file}" ] || ! unzip -t -q "${zip_file}" >/dev/null 2>&1; then
        echo "  [WARN] vue-dist zip 缺失或校验失败: ${zip_file}"
        return 1
    fi
    if [ ! -f "${checksum_file}" ]; then
        echo "  [WARN] vue-dist 缺少 SHA256 文件: ${checksum_file}"
        return 1
    fi
    expected_sha=$(tr -d '[:space:]' < "${checksum_file}")
    actual_sha=$(sha256sum "${zip_file}" | awk '{print $1}')
    if ! [[ "${expected_sha}" =~ ^[0-9a-fA-F]{64}$ ]] || \
       [ "${expected_sha,,}" != "${actual_sha}" ]; then
        echo "  [WARN] vue-dist SHA256 校验失败"
        return 1
    fi
    tmp_dir="${VUE_DIST_DIR}.new"
    previous_dir="${VUE_DIST_DIR}.previous"
    rm -rf "${tmp_dir}" && mkdir -p "${tmp_dir}"
    unzip -o -q "${zip_file}" -d "${tmp_dir}"
    if [ ! -f "${tmp_dir}/index.html" ]; then
        echo "  [WARN] vue-dist 缺少 index.html，取消部署"
        rm -rf "${tmp_dir}"
        return 1
    fi
    rm -f "${zip_file}" "${checksum_file}"
    rm -rf "${previous_dir}"
    if [ -e "${VUE_DIST_DIR}" ]; then
        mv "${VUE_DIST_DIR}" "${previous_dir}"
    fi
    if ! mv "${tmp_dir}" "${VUE_DIST_DIR}"; then
        [ -e "${previous_dir}" ] && mv "${previous_dir}" "${VUE_DIST_DIR}"
        return 1
    fi
    # 部署验证闭环：入口 asset + 关键 chunk（巡检审核清单）存在
    local entry rc
    entry=$(grep -o 'assets/index-[^"]*\.js' "${VUE_DIST_DIR}/index.html" 2>/dev/null | head -1)
    rc=$(ls "${VUE_DIST_DIR}/assets/" 2>/dev/null | grep -c "ReviewChecklist" || true)
    echo "  [INFO] 前端入口: ${entry:-未知}"
    echo "  [INFO] 巡检审核清单 chunk: ${rc} 个"
    echo "  [OK] Vue 构建产物已部署（vue-dist）"
    return 0
}

VUE_DEPLOYED=false
# 0) 本地手动包优先（网络被墙时管理员 scp 上传到 backups/vue-dist-manual.zip）
LOCAL_ZIP="${APP_DIR}/backups/vue-dist-manual.zip"
LOCAL_ZIP_SHA="${LOCAL_ZIP}.sha256"
if [ -f "${LOCAL_ZIP}" ]; then
    echo "  [INFO] 发现本地手动包 backups/vue-dist-manual.zip，优先部署..."
    if deploy_vue_dist "${LOCAL_ZIP}" "${LOCAL_ZIP_SHA}"; then
        VUE_DEPLOYED=true
    fi
fi

# 1) 多通道拉取：复用 [3/6] 探测结果（ITSM_AVAILABLE），按优先级（代理 → 直连 → 镜像）下载
if [ "${VUE_DEPLOYED}" != "true" ] && command -v curl >/dev/null 2>&1; then
    if [ -n "${GITHUB_REPO_URL}" ]; then
        if [ "${#ITSM_AVAILABLE[@]}" -eq 0 ]; then
            echo "  [INFO] 探测可用下载通道（代理/直连/镜像）..."
            probe_all_channels || true
        fi
        # 按优先级（代理 → 直连 → 镜像）依次下载，第一个成功即部署
        if [ "${#ITSM_AVAILABLE[@]}" -gt 0 ]; then
            echo "  [INFO] 共 ${#ITSM_AVAILABLE[@]} 个可用通道，开始下载..."
            for item in "${ITSM_AVAILABLE[@]}"; do
                kind="${item%%|*}"
                url="${item#*|}"
                echo "  [INFO] 下载通道: ${kind} ${url}"
                rm -f /tmp/itsm-vue-dist.zip /tmp/itsm-vue-dist.zip.sha256
                if [ "${kind}" = "proxy" ]; then
                    curl -fL --connect-timeout 15 --max-time 300 -o /tmp/itsm-vue-dist.zip \
                        --proxy "${url}" "${GITHUB_RELEASE_URL}" 2>/dev/null
                    curl -fL --connect-timeout 15 --max-time 60 -o /tmp/itsm-vue-dist.zip.sha256 \
                        --proxy "${url}" "${GITHUB_RELEASE_SHA_URL}" 2>/dev/null
                elif [ "${kind}" = "direct" ]; then
                    curl -fL --connect-timeout 15 --max-time 300 -o /tmp/itsm-vue-dist.zip \
                        "${GITHUB_RELEASE_URL}" 2>/dev/null
                    curl -fL --connect-timeout 15 --max-time 60 -o /tmp/itsm-vue-dist.zip.sha256 \
                        "${GITHUB_RELEASE_SHA_URL}" 2>/dev/null
                else
                    curl -fL --connect-timeout 15 --max-time 300 -o /tmp/itsm-vue-dist.zip \
                        "${url}" 2>/dev/null
                    curl -fL --connect-timeout 15 --max-time 60 -o /tmp/itsm-vue-dist.zip.sha256 \
                        "${url}.sha256" 2>/dev/null
                fi
                if [ -s /tmp/itsm-vue-dist.zip ] && \
                   deploy_vue_dist /tmp/itsm-vue-dist.zip /tmp/itsm-vue-dist.zip.sha256; then
                    VUE_DEPLOYED=true
                    break
                else
                    echo "  [WARN] 该通道下载/校验失败，尝试下一个"
                fi
            done
            rm -f /tmp/itsm-vue-dist.zip /tmp/itsm-vue-dist.zip.sha256
        else
            echo "  [WARN] 所有通道（代理/直连/镜像）均不可达"
        fi
    fi
fi
# 2) gh CLI 拉取
if [ "${VUE_DEPLOYED}" != "true" ] && command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    if gh release download "${RELEASE_TAG}" --pattern 'itsm-vue-dist.zip*' --dir /tmp/itsm_vue --clobber 2>/dev/null && \
       [ -f /tmp/itsm_vue/itsm-vue-dist.zip ]; then
        deploy_vue_dist /tmp/itsm_vue/itsm-vue-dist.zip \
            /tmp/itsm_vue/itsm-vue-dist.zip.sha256 && VUE_DEPLOYED=true || true
    else
        echo "  [WARN] gh 拉取 vue-dist 失败"
    fi
    rm -rf /tmp/itsm_vue
fi
# 3) 本地构建（服务器需 Node）
if [ "${VUE_DEPLOYED}" != "true" ] && [ -d "${APP_DIR}/frontend" ] && command -v npm >/dev/null 2>&1; then
    echo "  [WARN] 拉取失败，改用本地构建（服务器需 Node）..."
    LOCAL_BUILD_ZIP="/tmp/itsm-vue-dist-local.zip"
    LOCAL_BUILD_SHA="${LOCAL_BUILD_ZIP}.sha256"
    rm -f "${LOCAL_BUILD_ZIP}" "${LOCAL_BUILD_SHA}"
    if (cd "${APP_DIR}/frontend" && npm ci --no-audit --no-fund 2>/dev/null && \
        npm run build 2>/dev/null && cd dist && zip -qr "${LOCAL_BUILD_ZIP}" .) && \
       sha256sum "${LOCAL_BUILD_ZIP}" | awk '{print $1}' > "${LOCAL_BUILD_SHA}" && \
       deploy_vue_dist "${LOCAL_BUILD_ZIP}" "${LOCAL_BUILD_SHA}"; then
        VUE_DEPLOYED=true
        echo "  [OK] 本地构建完成并原子部署"
    else
        echo "  [WARN] 本地构建失败"
    fi
fi
# 4) 最终检查：前端产物缺失 → 更新失败（明确报错退出，不再"SSR 保底"糊弄"更新完成"）
if [ "${VUE_DEPLOYED}" != "true" ]; then
    echo "  [FATAL] 前端产物部署失败（无手动包且网络多通道均不可达）"
    echo "         请用 scripts/make-release.sh 生成发布包（itsm-update.bundle + vue-dist-manual.zip），"
    echo "         同时上传到 backups/ 后重跑本脚本"
    exit 1
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
systemctl --no-pager -l status itsm
if ! wait_for_readyz; then
    echo "[ERROR] 服务重启后 readyz 未通过，尝试恢复上一版前端..." >&2
    FAILED_VUE_DIR="${VUE_DIST_DIR}.failed.${TIMESTAMP}"
    if restore_previous_frontend "${VUE_DIST_DIR}" "${VUE_DIST_DIR}.previous" "${FAILED_VUE_DIR}"; then
        systemctl restart itsm
        if wait_for_readyz; then
            echo "[ROLLBACK] 已恢复上一版前端；失败版本保留在 ${FAILED_VUE_DIR}" >&2
        else
            echo "[FATAL] 上一版前端已恢复，但 readyz 仍失败；请按本次配对备份回滚后端/数据库" >&2
        fi
    else
        echo "[FATAL] 上一版前端自动恢复失败；请按本次配对备份执行人工回滚" >&2
    fi
    exit 1
fi

echo "更新完成！"
