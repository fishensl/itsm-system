#!/usr/bin/env bash
# ============================================================
# ITSM 手动部署 → GitHub 更新模式 迁移脚本
# 适用场景: Ubuntu 24 上已手动部署了旧版本，需要接入 GitHub 在线更新
# 用法: sudo bash migrate-to-github.sh [/path/to/app] [repo_url]
# 示例: sudo bash migrate-to-github.sh /home/itsm-system_20260614
# ============================================================
set -euo pipefail

APP_DIR="${1:-/opt/itsm}"
REPO_URL="${2:-https://github.com/fishensl/itsm-system.git}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
GIT="git -C ${APP_DIR}"

echo "============================================"
echo "  ITSM 迁移脚本"
echo "  手动部署 → GitHub 在线更新"
echo "  目录: ${APP_DIR}"
echo "============================================"

# ---- 0. 检查 ----
if [ "$(id -u)" -ne 0 ]; then
    echo "[FATAL] 请用 sudo 运行此脚本"
    exit 1
fi

if [ ! -d "${APP_DIR}" ]; then
    echo "[FATAL] ${APP_DIR} 不存在"
    exit 1
fi

# 解决 sudo 下 git dubious ownership 问题
${GIT} config --global --add safe.directory "${APP_DIR}" 2>/dev/null || true

# ---- 1. 备份现有数据 ----
echo "[1/8] 备份现有数据..."
mkdir -p "${APP_DIR}/backups"

BACKUP_FILE="${APP_DIR}/backups/migration_backup_${TIMESTAMP}.tar.gz"
tar -czf "${BACKUP_FILE}" \
    -C "${APP_DIR}" \
    instance/itsm.db \
    .secret.key \
    .env \
    reports/ \
    uploads/ \
    static/uploads/ \
    2>/dev/null || true

echo "  备份: backups/migration_backup_${TIMESTAMP}.tar.gz"

# ---- 2. 安装 git ----
echo "[2/8] 检查 git..."
apt-get update -qq 2>/dev/null || true
apt-get install -y -qq git 2>/dev/null || true

# ---- 3. 备份旧代码中的本地修改 ----
echo "[3/8] 备份本地修改..."
LOCAL_BACKUP="/tmp/itsm_local_${TIMESTAMP}"
mkdir -p "${LOCAL_BACKUP}"

# 保存可能被覆盖的本地文件
for f in app.py config.py models.py requirements.txt; do
    if [ -f "${APP_DIR}/${f}" ]; then
        mkdir -p "$(dirname "${LOCAL_BACKUP}/${f}")"
        cp "${APP_DIR}/${f}" "${LOCAL_BACKUP}/${f}" 2>/dev/null || true
    fi
done

# ---- 4. 初始化 git 并拉取 ----
echo "[4/8] 初始化 Git 仓库..."
cd "${APP_DIR}"

# 如果已有 .git 目录，先备份再重建
if [ -d ".git" ]; then
    rm -rf .git
fi

${GIT} init
${GIT} config user.name "itsm-deploy"
${GIT} config user.email "deploy@itsm.local"
${GIT} remote add origin "${REPO_URL}"

# ---- 5. 拉取 GitHub 最新代码 ----
echo "[5/8] 拉取 GitHub 最新代码..."
if ! ${GIT} fetch origin master; then
    echo ""
    echo "  [WARN] 无法连接 GitHub，尝试重试..."
    sleep 2
    if ! ${GIT} fetch origin master; then
        echo ""
        echo "============================================"
        echo "  [FATAL] GitHub 连接失败两次"
        echo "  请检查网络后手动执行:"
        echo "    cd ${APP_DIR}"
        echo "    git fetch origin master"
        echo "    git reset --hard origin/master"
        echo "    bash scripts/migrate-to-github.sh ${APP_DIR}"
        echo "============================================"
        echo "  数据备份在: backups/migration_backup_${TIMESTAMP}.tar.gz"
        exit 1
    fi
fi

${GIT} checkout -b master 2>/dev/null || ${GIT} checkout master 2>/dev/null || true
${GIT} reset --hard origin/master

# ---- 6. 恢复本地数据 ----
echo "[6/8] 恢复运行时数据..."
mkdir -p "${APP_DIR}/instance" "${APP_DIR}/logs" "${APP_DIR}/reports" "${APP_DIR}/uploads" "${APP_DIR}/backups"
mkdir -p "${APP_DIR}/static/uploads/knowledge" "${APP_DIR}/static/uploads/spare_parts" "${APP_DIR}/static/uploads/topologies"

# 从 tar 恢复数据库和密钥
if [ -f "${BACKUP_FILE}" ]; then
    tar -xzf "${BACKUP_FILE}" -C "${APP_DIR}" 2>/dev/null || true
fi

# ---- 7. 安装环境 ----
echo "[7/8] 安装 Python 环境..."

# venv
if [ ! -d "${APP_DIR}/venv" ]; then
    python3 -m venv "${APP_DIR}/venv"
fi
"${APP_DIR}/venv/bin/pip" install --upgrade pip -q 2>/dev/null || true
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt" -q

# .env
if [ ! -f "${APP_DIR}/.env" ]; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > "${APP_DIR}/.env" <<EOF
ITSM_SECRET_KEY=${SECRET_KEY}
ITSM_ENV=production
FLASK_ENV=production
EOF
    chmod 600 "${APP_DIR}/.env"
fi

# .secret.key
if [ ! -f "${APP_DIR}/.secret.key" ]; then
    "${APP_DIR}/venv/bin/python" -c "
from cryptography.fernet import Fernet
with open('${APP_DIR}/.secret.key', 'wb') as f:
    f.write(Fernet.generate_key())
"
    chmod 600 "${APP_DIR}/.secret.key"
fi

# 系统用户
id -u itsm &>/dev/null || useradd -r -s /bin/false itsm
chown -R itsm:itsm "${APP_DIR}"

# systemd 服务
cp "${APP_DIR}/scripts/itsm.service" /etc/systemd/system/itsm.service
systemctl daemon-reload
systemctl enable itsm

# ---- 8. 切换服务 ----
echo "[8/8] 切换服务..."

# 停旧进程
OLD_PIDS=$(pgrep -f "python.*app.py" 2>/dev/null || true)
if [ -n "${OLD_PIDS}" ]; then
    echo "  停止旧进程..."
    echo "${OLD_PIDS}" | xargs kill 2>/dev/null || true
    sleep 2
fi

systemctl restart itsm

echo ""
echo "============================================"
echo "  迁移完成！"
echo "============================================"
echo "  版本: $(cat ${APP_DIR}/VERSION 2>/dev/null || echo '?')"
echo "  备份: backups/migration_backup_${TIMESTAMP}.tar.gz"
echo ""
echo "  更新命令: sudo bash ${APP_DIR}/scripts/update.sh"
echo ""
systemctl status itsm --no-pager -l || true
