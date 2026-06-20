#!/usr/bin/env bash
# ============================================================
# ITSM 管理控制台（Ubuntu 24）— 交互式菜单
# 整合 deploy / update / backup / migrate / rollback / pg-check / pg-migrate / pg-rollback
# 以及：重置 PG 密码 / 改指定 PG 密码 / 改 Web 端口 / 改 PG 端口
#
# 用法: sudo bash itsm-admin.sh [/path/to/app]
# 默认: APP_DIR=/home/itsm-system_20260614
#
# 设计：本脚本只做调度与「重置修改」类小操作；部署/迁移等重活调用 scripts/ 下既有脚本，
#       不重复实现其逻辑。所有写操作前给确认提示。
# ============================================================
set -uo pipefail

APP_DIR="${1:-/home/itsm-system_20260614}"
SCRIPTS_DIR="${APP_DIR}/scripts"
ENV_FILE="${APP_DIR}/.env"
VENV="${APP_DIR}/venv"
SERVICE_DST="/etc/systemd/system/itsm.service"

# ---------- 颜色 ----------
C_RED='\033[0;31m'; C_GREEN='\033[0;32m'; C_YELLOW='\033[1;33m'
C_CYAN='\033[0;36m'; C_BOLD='\033[1m'; C_OFF='\033[0m'
ok()   { echo -e "${C_GREEN}[OK]${C_OFF} $*"; }
warn() { echo -e "${C_YELLOW}[WARN]${C_OFF} $*"; }
fail() { echo -e "${C_RED}[FAIL]${C_OFF} $*" >&2; }
hr()   { echo -e "${C_CYAN}--------------------------------------------${C_OFF}"; }

# ---------- 公共：前置检查 ----------
require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        fail "请用 sudo 运行"; exit 1
    fi
}

require_app_dir() {
    if [ ! -d "${APP_DIR}" ]; then
        fail "应用目录不存在: ${APP_DIR}"
        echo "  可带目录参数运行: sudo bash $0 /your/path"
        exit 1
    fi
}

# 从 .env 读某个键的值（取最后一个非注释匹配行，避免多行重复）
env_get() {
    local key="$1"
    grep -E "^${key}=" "${ENV_FILE}" 2>/dev/null | tail -n1 | cut -d= -f2-
}

# 原地更新 .env 某键：若存在则替换该行（全部），否则追加
env_set() {
    local key="$1" val="$2"
    if [ ! -f "${ENV_FILE}" ]; then
        echo "${key}=${val}" > "${ENV_FILE}"
        chmod 600 "${ENV_FILE}"
        return
    fi
    if grep -qE "^${key}=" "${ENV_FILE}"; then
        # 用 | 做 sed 分隔符避免值里的 / 冲突；值里的 & 要转义
        local escaped
        escaped=$(printf '%s' "${val}" | sed 's/[&|]/\\&/g')
        sed -i "s|^${key}=.*|${key}=${escaped}|" "${ENV_FILE}"
    else
        echo "${key}=${val}" >> "${ENV_FILE}"
    fi
    chmod 600 "${ENV_FILE}"
}

# 确认提示；返回 0=是 1=否
confirm() {
    local prompt="$1" def="${2:-no}"
    if [ "${def}" = "yes" ]; then
        read -rp "${prompt} [Y/n] " ans
        case "${ans:-Y}" in n|N|no|NO) return 1;; *) return 0;; esac
    else
        read -rp "${prompt} [y/N] " ans
        case "${ans:-N}" in y|Y|yes|YES) return 0;; *) return 1;; esac
    fi
}

# 调用 scripts/ 下既有脚本（透传到新 shell，避免污染本脚本 set -e）
run_script() {
    local name="$1"; shift
    local path="${SCRIPTS_DIR}/${name}"
    if [ ! -f "${path}" ]; then
        fail "脚本不存在: ${path}"; return 1
    fi
    hr; echo -e "${C_BOLD}执行: bash ${name} $*${C_OFF}"; hr
    bash "${path}" "$@"
}

# 显示当前数据库/端口概要
show_status() {
    hr
    echo -e "${C_BOLD}当前状态${C_OFF}"
    hr
    local uri
    uri=$(env_get ITSM_DATABASE_URI)
    if [ -z "${uri}" ]; then
        echo "  数据库 URI: （未配置，默认 SQLite instance/itsm.db）"
        local db_engine="SQLite(默认)"
    elif [[ "${uri}" == postgresql* ]]; then
        echo "  数据库 URI: PostgreSQL"
        # 解析各段（不回显密码）
        local pg_user pg_host pg_port pg_db
        pg_user=$(echo "${uri}" | sed -E 's#^postgresql://([^:]+):.*#\1#')
        pg_host=$(echo "${uri}" | sed -E 's#^postgresql://[^@]+@([^:/]+).*#\1#')
        pg_port=$(echo "${uri}" | sed -E 's#.*:([0-9]+)/.*#\1#')
        [ "${pg_port}" = "${uri}" ] && pg_port="5432"
        pg_db=$(echo "${uri}" | sed -E 's#.*/([^/?]+)$#\1#')
        echo "    用户/库/主机/端口: ${pg_user} / ${pg_db} / ${pg_host} / ${pg_port}"
        local db_engine="PostgreSQL"
    else
        echo "  数据库 URI: ${uri}"
        local db_engine="SQLite"
    fi

    # Web 端口（从已安装的 service 文件读）
    local web_port
    if [ -f "${SERVICE_DST}" ]; then
        web_port=$(grep -oE '\-\-bind [^ ]+:[0-9]+' "${SERVICE_DST}" | grep -oE '[0-9]+$' | tail -n1)
    fi
    [ -z "${web_port}" ] && web_port="5000(默认)"
    echo "  Web 端口: ${web_port}"

    # 服务状态
    if systemctl is-active --quiet itsm 2>/dev/null; then
        echo "  服务状态: ${C_GREEN}running${C_OFF}"
    else
        echo "  服务状态: ${C_YELLOW}stopped/未安装${C_OFF}"
    fi
    echo "  应用目录: ${APP_DIR}"
    hr
}

# ---------- 重置/修改类操作 ----------

# 重置 PG 密码：随机生成新密码，ALTER USER + 更新 .env URI 密码段 + 重启
op_reset_pg_password() {
    require_app_dir
    local uri
    uri=$(env_get ITSM_DATABASE_URI)
    if [ -z "${uri}" ] || [[ "${uri}" != postgresql* ]]; then
        fail "当前 ITSM_DATABASE_URI 不是 PostgreSQL，无法重置 PG 密码"
        echo "  当前值: ${uri:-(未配置)}"
        return 1
    fi
    local pg_user pg_host pg_port pg_db
    pg_user=$(echo "${uri}" | sed -E 's#^postgresql://([^:]+):.*#\1#')
    pg_host=$(echo "${uri}" | sed -E 's#^postgresql://[^@]+@([^:/]+).*#\1#')
    pg_port=$(echo "${uri}" | sed -E 's#.*:([0-9]+)/.*#\1#')
    [ "${pg_port}" = "${uri}" ] && pg_port="5432"
    pg_db=$(echo "${uri}" | sed -E 's#.*/([^/?]+)$#\1#')

    echo "将为 PG 用户 ${C_BOLD}${pg_user}${C_OFF} 生成新随机密码并更新 .env。"
    confirm "确认重置?" || { echo "已取消"; return 0; }

    local new_pass
    new_pass=$(python3 -c "import secrets; print(secrets.token_hex(16))")
    if ! sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
        "ALTER USER \"${pg_user}\" WITH PASSWORD '${new_pass}';" 2>/dev/null; then
        fail "ALTER USER 失败（用户 ${pg_user} 不存在？或 PG 未装）"; return 1
    fi
    local new_uri="postgresql://${pg_user}:${new_pass}@${pg_host}:${pg_port}/${pg_db}"
    env_set ITSM_DATABASE_URI "${new_uri}"
    ok "PG 密码已重置，.env 已更新"
    echo "  新密码已写入 .env（此处不回显，查看: sudo grep ITSM_DATABASE_URI ${ENV_FILE}）"
    _restart_service
}

# 修改为指定 PG 密码：输入密码，ALTER USER + 更新 .env
op_set_pg_password() {
    require_app_dir
    local uri
    uri=$(env_get ITSM_DATABASE_URI)
    if [ -z "${uri}" ] || [[ "${uri}" != postgresql* ]]; then
        fail "当前 ITSM_DATABASE_URI 不是 PostgreSQL"; return 1
    fi
    local pg_user pg_host pg_port pg_db
    pg_user=$(echo "${uri}" | sed -E 's#^postgresql://([^:]+):.*#\1#')
    pg_host=$(echo "${uri}" | sed -E 's#^postgresql://[^@]+@([^:/]+).*#\1#')
    pg_port=$(echo "${uri}" | sed -E 's#.*:([0-9]+)/.*#\1#')
    [ "${pg_port}" = "${uri}" ] && pg_port="5432"
    pg_db=$(echo "${uri}" | sed -E 's#.*/([^/?]+)$#\1#')

    echo "为 PG 用户 ${C_BOLD}${pg_user}${C_OFF} 设置自定义密码。"
    # 两次输入一致校验，不回显
    local p1 p2
    read -rsp "输入新密码: " p1; echo
    read -rsp "再次输入新密码: " p2; echo
    if [ -z "${p1}" ] || [ "${p1}" != "${p2}" ]; then
        fail "密码为空或两次输入不一致"; return 1
    fi
    confirm "确认修改?" || { echo "已取消"; return 0; }

    if ! sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
        "ALTER USER \"${pg_user}\" WITH PASSWORD '${p1}';" 2>/dev/null; then
        fail "ALTER USER 失败"; return 1
    fi
    local new_uri="postgresql://${pg_user}:${p1}@${pg_host}:${pg_port}/${pg_db}"
    env_set ITSM_DATABASE_URI "${new_uri}"
    ok "PG 密码已修改，.env 已更新"
    _restart_service
}

# 改 Web 端口：改已安装 service 文件的 gunicorn --bind 端口 + app.py 开发端口
op_set_web_port() {
    require_app_dir
    if [ ! -f "${SERVICE_DST}" ]; then
        fail "未安装 itsm 服务 (${SERVICE_DST})；请先部署"; return 1
    fi
    local cur_port
    cur_port=$(grep -oE '\-\-bind [^ ]+:[0-9]+' "${SERVICE_DST}" | grep -oE '[0-9]+$' | tail -n1)
    [ -z "${cur_port}" ] && cur_port="5000"
    echo "当前 Web 端口: ${C_BOLD}${cur_port}${C_OFF}"
    local new_port
    read -rp "输入新端口(1-65535): " new_port
    if ! [[ "${new_port}" =~ ^[0-9]+$ ]] || [ "${new_port}" -lt 1 ] 2>/dev/null || [ "${new_port}" -gt 65535 ] 2>/dev/null; then
        fail "端口非法（需 1-65535 的数字）"; return 1
    fi
    if [ "${new_port}" = "${cur_port}" ]; then
        warn "新端口与当前相同，无需修改"; return 0
    fi
    echo "将把 gunicorn --bind 端口改为 ${new_port}，并同步 app.py 开发端口。"
    echo "  ⚠️ 需在防火墙放行新端口: sudo ufw allow ${new_port}/tcp（若启用 ufw）"
    confirm "确认修改?" || { echo "已取消"; return 0; }

    # 1. 改已安装的 service 文件里的 --bind 端口
    sed -i -E "s|(--bind [^ ]+:)[0-9]+|\1${new_port}|" "${SERVICE_DST}"
    # 2. 同步仓库内 itsm.service 模板（下次 update.sh 重装 service 时不回退）
    if [ -f "${SCRIPTS_DIR}/itsm.service" ]; then
        sed -i -E "s|(--bind [^ ]+:)[0-9]+|\1${new_port}|" "${SCRIPTS_DIR}/itsm.service"
    fi
    # 3. 同步 app.py 开发端口（python app.py 直跑时）
    if [ -f "${APP_DIR}/app.py" ]; then
        sed -i -E "s|(port=)[0-9]+|\1${new_port}|" "${APP_DIR}/app.py"
    fi
    systemctl daemon-reload
    ok "Web 端口已改为 ${new_port}（service + app.py 同步）"
    _restart_service
    echo "  访问地址: http://<服务器IP>:${new_port}"
}

# 改 PG 端口：改 postgresql.conf + pg_hba.conf + 重启 PG + 改 .env URI 端口段 + 重启 itsm
op_set_pg_port() {
    require_app_dir
    local uri
    uri=$(env_get ITSM_DATABASE_URI)
    if [ -z "${uri}" ] || [[ "${uri}" != postgresql* ]]; then
        fail "当前 ITSM_DATABASE_URI 不是 PostgreSQL"; return 1
    fi
    # 解析当前端口
    local cur_port pg_user pg_host pg_db
    cur_port=$(echo "${uri}" | sed -E 's#.*:([0-9]+)/.*#\1#')
    [ "${cur_port}" = "${uri}" ] && cur_port="5432"
    pg_user=$(echo "${uri}" | sed -E 's#^postgresql://([^:]+):.*#\1#')
    pg_host=$(echo "${uri}" | sed -E 's#^postgresql://[^@]+@([^:/]+).*#\1#')
    pg_db=$(echo "${uri}" | sed -E 's#.*/([^/?]+)$#\1#')

    echo "当前 PG 端口: ${C_BOLD}${cur_port}${C_OFF}"
    warn "改 PG 端口会重启 PostgreSQL（影响所有连该实例的库），并改 postgresql.conf + pg_hba.conf。"
    warn "若 ${pg_host} 不是 localhost，需另行配置远程监听；本操作只处理本机监听端口。"
    local new_port
    read -rp "输入新 PG 端口(1-65535): " new_port
    if ! [[ "${new_port}" =~ ^[0-9]+$ ]] || [ "${new_port}" -lt 1 ] 2>/dev/null || [ "${new_port}" -gt 65535 ] 2>/dev/null; then
        fail "端口非法"; return 1
    fi
    if [ "${new_port}" = "${cur_port}" ]; then
        warn "新端口与当前相同"; return 0
    fi
    confirm "确认修改 PG 端口为 ${new_port}?（会重启 PostgreSQL）" || { echo "已取消"; return 0; }

    # 定位 PG 配置目录（Ubuntu 24 通常 /etc/postgresql/16/main）
    local pg_ver pg_conf_dir
    pg_ver=$(ls -d /etc/postgresql/*/main 2>/dev/null | sort -V | tail -n1)
    if [ -z "${pg_ver}" ]; then
        fail "未找到 PostgreSQL 配置目录 (/etc/postgresql/*/main)，PG 是否已装？"; return 1
    fi
    pg_conf_dir="${pg_ver}"
    local pg_conf="${pg_conf_dir}/postgresql.conf"
    local hba_conf="${pg_conf_dir}/pg_hba.conf"
    if [ ! -f "${pg_conf}" ]; then
        fail "postgresql.conf 不存在: ${pg_conf}"; return 1
    fi

    # 备份配置
    local ts; ts=$(date +%Y%m%d_%H%M%S)
    cp "${pg_conf}" "${pg_conf}.bak_${ts}"
    cp "${hba_conf}" "${hba_conf}.bak_${ts}" 2>/dev/null || true

    # 改 port = xxxx（注释行首可能有 #，统一改/加）
    if grep -qE "^[#[:space:]]*port[[:space:]]*=" "${pg_conf}"; then
        sed -i -E "s|^[#[:space:]]*port[[:space:]]*=.*|port = ${new_port}|" "${pg_conf}"
    else
        echo "port = ${new_port}" >> "${pg_conf}"
    fi

    # 重启 PG
    if ! systemctl restart postgresql; then
        fail "PostgreSQL 重启失败，回滚配置"
        cp "${pg_conf}.bak_${ts}" "${pg_conf}"
        systemctl restart postgresql || true
        return 1
    fi
    sleep 2
    # 验证 PG 在新端口监听
    if ! sudo -u postgres psql -p "${new_port}" -c "SELECT 1" >/dev/null 2>&1; then
        fail "PG 新端口 ${new_port} 连接失败，回滚"
        cp "${pg_conf}.bak_${ts}" "${pg_conf}"
        systemctl restart postgresql || true
        return 1
    fi

    # 更新 .env URI 端口段
    local pg_pass
    pg_pass=$(echo "${uri}" | sed -E 's#^postgresql://[^:]+:([^@]+)@.*#\1#')
    local new_uri="postgresql://${pg_user}:${pg_pass}@${pg_host}:${new_port}/${pg_db}"
    env_set ITSM_DATABASE_URI "${new_uri}"

    ok "PG 端口已改为 ${new_port}（postgresql.conf + .env 已更新，PostgreSQL 已重启）"
    echo "  配置备份: ${pg_conf}.bak_${ts}"
    _restart_service
}

# 重启服务（若已安装）
_restart_service() {
    if systemctl list-unit-files 2>/dev/null | grep -q '^itsm\.service'; then
        systemctl restart itsm && ok "itsm 服务已重启" || warn "itsm 重启失败，查: journalctl -u itsm -n 30"
    else
        warn "itsm 服务未安装，跳过重启"
    fi
}

# 服务是否已安装
_service_installed() {
    systemctl list-unit-files 2>/dev/null | grep -q '^itsm\.service'
}

# 重启 itsm 服务
op_restart_service() {
    require_app_dir
    if ! _service_installed; then
        fail "itsm 服务未安装"; return 1
    fi
    echo "重启 itsm 服务…"
    if systemctl restart itsm; then
        sleep 2
        if systemctl is-active --quiet itsm; then
            ok "itsm 服务已重启并运行"
        else
            warn "已执行 restart，但服务未进入 active，查: journalctl -u itsm -n 30"
        fi
    else
        fail "重启失败，查: journalctl -u itsm -n 30"; return 1
    fi
}

# 启动 itsm 服务
op_start_service() {
    require_app_dir
    if ! _service_installed; then fail "itsm 服务未安装"; return 1; fi
    if systemctl is-active --quiet itsm; then
        warn "itsm 服务已在运行"; return 0
    fi
    if systemctl start itsm; then
        sleep 2
        systemctl is-active --quiet itsm && ok "itsm 服务已启动" || warn "启动后未 active，查日志"
    else
        fail "启动失败"; return 1
    fi
}

# 停止 itsm 服务
op_stop_service() {
    require_app_dir
    if ! _service_installed; then fail "itsm 服务未安装"; return 1; fi
    if ! systemctl is-active --quiet itsm; then
        warn "itsm 服务未在运行"; return 0
    fi
    confirm "确认停止 itsm 服务?（停止后网站不可访问）" || { echo "已取消"; return 0; }
    systemctl stop itsm && ok "itsm 服务已停止" || { fail "停止失败"; return 1; }
}

# 查看服务状态 + 最近日志
op_service_status() {
    require_app_dir
    if ! _service_installed; then fail "itsm 服务未安装"; return 1; fi
    hr; echo -e "${C_BOLD}服务状态${C_OFF}"; hr
    systemctl status itsm --no-pager -l || true
    echo ""
    hr; echo -e "${C_BOLD}最近 30 行日志${C_OFF}"; hr
    journalctl -u itsm -n 30 --no-pager || true
}

# ---------- 菜单 ----------
menu_main() {
    while true; do
        echo ""
        hr
        echo -e "${C_BOLD}  ITSM 管理控制台${C_OFF}  (${APP_DIR})"
        hr
        echo "  部署与运维:"
        echo "   1) 首次部署（deploy.sh）           2) 在线更新（update.sh）"
        echo "   3) 数据库备份（backup.sh）         4) schema 同步（migrate.sh）"
        echo "   5) 紧急回滚 SQLite（rollback.sh）"
        echo "  PostgreSQL 迁移:"
        echo "   6) 迁移前体检（pg-check.sh）       7) SQLite→PG 迁移（pg-migrate.sh）"
        echo "   8) PG→SQLite 回滚（pg-rollback.sh）"
        echo "  重置 / 修改:"
        echo "   9) 重置 PG 密码（随机）            10) 修改为指定 PG 密码"
        echo "  11) 修改 Web 访问端口               12) 修改 PostgreSQL 端口"
        echo "  服务管理:"
        echo "  13) 重启 itsm 服务                  14) 启动 itsm 服务"
        echo "  15) 停止 itsm 服务                  16) 查看状态 + 日志"
        echo "  其它:"
        echo "  17) 查看当前状态                    0) 退出"
        hr
        local choice
        read -rp "请选择 [0-17]: " choice
        case "${choice}" in
            1) require_root; run_script deploy.sh ;;
            2) require_root; require_app_dir; run_script update.sh "${APP_DIR}" ;;
            3) require_root; require_app_dir; run_script backup.sh "${APP_DIR}" ;;
            4) require_root; require_app_dir; run_script migrate.sh "${APP_DIR}" ;;
            5) require_root; require_app_dir; run_script rollback.sh "${APP_DIR}" ;;
            6) require_root; require_app_dir; run_script pg-check.sh "${APP_DIR}" ;;
            7) require_root; require_app_dir; run_script pg-migrate.sh "${APP_DIR}" ;;
            8) require_root; require_app_dir; run_script pg-rollback.sh "${APP_DIR}" ;;
            9) require_root; op_reset_pg_password ;;
            10) require_root; op_set_pg_password ;;
            11) require_root; op_set_web_port ;;
            12) require_root; op_set_pg_port ;;
            13) require_root; op_restart_service ;;
            14) require_root; op_start_service ;;
            15) require_root; op_stop_service ;;
            16) require_root; op_service_status ;;
            17) show_status ;;
            0) echo "再见"; exit 0 ;;
            "") continue ;;
            *) warn "无效选择: ${choice}" ;;
        esac
        echo ""
        read -rp "按回车返回菜单..." _enter
    done
}

# ---------- 入口 ----------
require_root
# deploy.sh 在目录还不存在时也要能跑（首次部署），所以只在非部署操作里校验目录
menu_main
