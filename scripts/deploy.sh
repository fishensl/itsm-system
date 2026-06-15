#!/usr/bin/env bash
# ============================================================
# ITSM 首次部署脚本 — Ubuntu 24
# 用法: sudo bash deploy.sh
# ============================================================
set -euo pipefail

# ---- 配置 ----
APP_DIR="/opt/itsm"
REPO_URL="${ITSM_REPO_URL:-}"
VENV="${APP_DIR}/venv"

echo "============================================"
echo "  ITSM 系统部署脚本"
echo "  目标: Ubuntu 24 / ${APP_DIR}"
echo "============================================"

# ---- 0. 检查 ----
if [ "$(id -u)" -ne 0 ]; then
    echo "[FATAL] 请用 sudo 运行此脚本"
    exit 1
fi

if [ -z "${REPO_URL}" ]; then
    echo "[FATAL] 请设置 ITSM_REPO_URL 环境变量为 GitHub 仓库地址"
    echo "  示例: export ITSM_REPO_URL=https://github.com/YOUR_ORG/itsm-system.git"
    exit 1
fi

# ---- 1. 系统依赖 ----
echo "[1/8] 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl

# ---- 2. 克隆仓库 ----
echo "[2/8] 克隆仓库..."
if [ -d "${APP_DIR}" ]; then
    echo "  目录已存在，跳过 clone"
else
    git clone "${REPO_URL}" "${APP_DIR}"
fi

# ---- 3. 创建运行时目录 ----
echo "[3/8] 创建运行时目录..."
mkdir -p "${APP_DIR}/instance"
mkdir -p "${APP_DIR}/logs"
mkdir -p "${APP_DIR}/reports"
mkdir -p "${APP_DIR}/uploads"
mkdir -p "${APP_DIR}/backups"
mkdir -p "${APP_DIR}/static/uploads/knowledge"
mkdir -p "${APP_DIR}/static/uploads/spare_parts"
mkdir -p "${APP_DIR}/static/uploads/topologies"

# ---- 4. Python 虚拟环境 ----
echo "[4/8] 创建 Python 虚拟环境..."
python3 -m venv "${VENV}"
"${VENV}/bin/pip" install --upgrade pip -q
"${VENV}/bin/pip" install -r "${APP_DIR}/requirements.txt" -q

# ---- 5. 生成密钥 ----
echo "[5/8] 生成密钥..."

if [ ! -f "${APP_DIR}/.env" ]; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > "${APP_DIR}/.env" <<EOF
ITSM_SECRET_KEY=${SECRET_KEY}
ITSM_ENV=production
FLASK_ENV=production
EOF
    chmod 600 "${APP_DIR}/.env"
    echo "  .env 已创建"
else
    echo "  .env 已存在，跳过"
fi

if [ ! -f "${APP_DIR}/.secret.key" ]; then
    "${VENV}/bin/python" -c "
from cryptography.fernet import Fernet
with open('${APP_DIR}/.secret.key', 'wb') as f:
    f.write(Fernet.generate_key())
"
    chmod 600 "${APP_DIR}/.secret.key"
    echo "  .secret.key 已创建"
else
    echo "  .secret.key 已存在，跳过"
fi

# ---- 6. 初始化数据库 ----
echo "[6/8] 初始化数据库..."
cd "${APP_DIR}"
"${VENV}/bin/python" -c "from app import app, init_db; init_db(); print('数据库初始化完成')"

# ---- 7. 创建系统用户 ----
echo "[7/8] 创建系统用户..."
if ! id -u itsm &>/dev/null; then
    useradd -r -s /bin/false itsm
    echo "  用户 itsm 已创建"
else
    echo "  用户 itsm 已存在"
fi
chown -R itsm:itsm "${APP_DIR}"

# ---- 8. 安装 systemd 服务 ----
echo "[8/8] 安装 systemd 服务..."
cp "${APP_DIR}/scripts/itsm.service" /etc/systemd/system/itsm.service
systemctl daemon-reload
systemctl enable itsm
systemctl start itsm

echo ""
echo "============================================"
echo "  部署完成！"
echo "============================================"
echo ""
echo "服务状态:"
systemctl status itsm --no-pager -l || true
echo ""
echo "访问地址: http://<服务器IP>:5000"
echo "默认登录: admin / admin123"
echo ""
echo "常用命令:"
echo "  状态:  sudo systemctl status itsm"
echo "  日志:  sudo journalctl -u itsm -f"
echo "  更新:  sudo bash ${APP_DIR}/scripts/update.sh"
echo "  备份:  sudo bash ${APP_DIR}/scripts/backup.sh"
