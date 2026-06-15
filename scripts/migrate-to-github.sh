#!/usr/bin/env bash
# ============================================================
# ITSM 手动部署 → GitHub 更新模式 迁移脚本
# 适用场景: Ubuntu 24 上已手动部署了旧版本，需要接入 GitHub 在线更新
# 用法: sudo bash migrate-to-github.sh [/path/to/app]
# 默认路径 /opt/itsm，可通过第一个参数覆盖

APP_DIR="${1:-/opt/itsm}"
REPO_URL="${ITSM_REPO_URL:-https://github.com/fishensl/itsm-system.git}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "============================================"
echo "  ITSM 迁移脚本"
echo "  手动部署 → GitHub 在线更新"
echo "============================================"

# ---- 0. 检查 ----
if [ "$(id -u)" -ne 0 ]; then
    echo "[FATAL] 请用 sudo 运行此脚本"
    exit 1
fi

if [ ! -d "${APP_DIR}" ]; then
    echo "[FATAL] ${APP_DIR} 不存在，请确认应用目录路径"
    exit 1
fi

# ---- 1. 备份现有数据（安全第一） ----
echo "[1/7] 备份现有数据..."
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

echo "  备份已保存: backups/migration_backup_${TIMESTAMP}.tar.gz"

# ---- 2. 安装 git（如果没有） ----
echo "[2/7] 检查 git..."
apt-get update -qq
apt-get install -y -qq git

# ---- 3. 初始化 git 并关联远程仓库 ----
echo "[3/7] 关联 GitHub 仓库..."
cd "${APP_DIR}"

# 先保存可能存在的本地修改
git init
git config user.name "itsm-deploy"
git config user.email "deploy@itsm.local"

# 添加远程仓库
git remote add origin "${REPO_URL}" 2>/dev/null || git remote set-url origin "${REPO_URL}"

# ---- 4. 拉取 GitHub 最新代码 ----
echo "[4/7] 拉取最新代码..."
git fetch origin

# 暂存本地所有文件
git add -A
git stash push --include-untracked -m "migration-stash-${TIMESTAMP}" 2>/dev/null || true

# 切换到远程 master
git checkout -b master 2>/dev/null || git checkout master 2>/dev/null || true
git reset --hard origin/master

# ---- 5. 恢复本地运行时文件 ----
echo "[5/7] 恢复运行时数据..."
git stash pop 2>/dev/null || true

# 确保运行时目录存在
mkdir -p "${APP_DIR}/instance"
mkdir -p "${APP_DIR}/logs"
mkdir -p "${APP_DIR}/reports"
mkdir -p "${APP_DIR}/uploads"
mkdir -p "${APP_DIR}/backups"
mkdir -p "${APP_DIR}/static/uploads/knowledge"
mkdir -p "${APP_DIR}/static/uploads/spare_parts"
mkdir -p "${APP_DIR}/static/uploads/topologies"

# 恢复数据库和密钥（如果被覆盖）
if [ -f "${APP_DIR}/backups/migration_backup_${TIMESTAMP}.tar.gz" ]; then
    tar -xzf "${APP_DIR}/backups/migration_backup_${TIMESTAMP}.tar.gz" -C "${APP_DIR}" 2>/dev/null || true
fi

# ---- 6. 创建/更新虚拟环境和 systemd 服务 ----
echo "[6/7] 安装/更新环境..."

# Python venv
if [ ! -d "${APP_DIR}/venv" ]; then
    python3 -m venv "${APP_DIR}/venv"
fi
"${APP_DIR}/venv/bin/pip" install --upgrade pip -q
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt" -q

# 生成 .env（如果不存在）
if [ ! -f "${APP_DIR}/.env" ]; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > "${APP_DIR}/.env" <<EOF
ITSM_SECRET_KEY=${SECRET_KEY}
ITSM_ENV=production
FLASK_ENV=production
EOF
    chmod 600 "${APP_DIR}/.env"
    echo "  .env 已创建"
fi

# 生成 .secret.key（如果不存在）
if [ ! -f "${APP_DIR}/.secret.key" ]; then
    "${APP_DIR}/venv/bin/python" -c "
from cryptography.fernet import Fernet
with open('${APP_DIR}/.secret.key', 'wb') as f:
    f.write(Fernet.generate_key())
"
    chmod 600 "${APP_DIR}/.secret.key"
    echo "  .secret.key 已创建"
fi

# 创建系统用户
if ! id -u itsm &>/dev/null; then
    useradd -r -s /bin/false itsm
fi
chown -R itsm:itsm "${APP_DIR}"

# 安装 systemd 服务
cp "${APP_DIR}/scripts/itsm.service" /etc/systemd/system/itsm.service
systemctl daemon-reload
systemctl enable itsm

# ---- 7. 停止旧进程，启动新服务 ----
echo "[7/7] 切换服务..."

# 如果旧进程还在跑（手动 python app.py 方式），停掉
OLD_PID=$(pgrep -f "python.*app.py" 2>/dev/null || true)
if [ -n "${OLD_PID}" ]; then
    echo "  停止旧进程 (PID: ${OLD_PID})..."
    kill "${OLD_PID}" 2>/dev/null || true
    sleep 2
fi

# 启动 systemd 服务
systemctl restart itsm

echo ""
echo "============================================"
echo "  迁移完成！"
echo "============================================"
echo ""
echo "备份文件: backups/migration_backup_${TIMESTAMP}.tar.gz"
echo ""
echo "现在可以通过以下命令更新:"
echo "  sudo bash ${APP_DIR}/scripts/update.sh"
echo ""
echo "服务状态:"
systemctl status itsm --no-pager -l || true
