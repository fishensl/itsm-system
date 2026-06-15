#!/usr/bin/env bash
# ============================================================
# ITSM 公共安装函数库
# 由 deploy.sh / update.sh / migrate-to-github.sh 共用
# ============================================================

# 安装 / 更新 systemd service 文件
# 参数: $1 = 部署目录 (APP_DIR)
# 行为:
#   1. 复制仓库里的 itsm.service 到 /etc/systemd/system/
#   2. 如果 APP_DIR 不是 /opt/itsm，自动 sed 替换全部路径
#   3. 校验替换后的 WorkingDirectory 真实存在（不存在则报错）
#   4. 校验 EnvironmentFile（如配置了）存在（不存在只警告）
#   5. systemctl daemon-reload
install_service() {
    local app_dir="$1"
    local src="${app_dir}/scripts/itsm.service"
    local dst="/etc/systemd/system/itsm.service"

    if [ ! -f "${src}" ]; then
        echo "[FATAL] 源 service 文件不存在: ${src}" >&2
        return 1
    fi

    cp "${src}" "${dst}"

    # 路径替换（如果不是默认 /opt/itsm）
    if [ "${app_dir}" != "/opt/itsm" ]; then
        sed -i "s|/opt/itsm|${app_dir}|g" "${dst}"
        echo "  service 路径已适配: ${app_dir}"
    fi

    # 校验 WorkingDirectory
    local wd
    wd=$(grep -E '^WorkingDirectory=' "${dst}" | cut -d= -f2-)
    if [ -n "${wd}" ] && [ ! -d "${wd}" ]; then
        echo "[FATAL] service 配置的 WorkingDirectory 不存在: ${wd}" >&2
        echo "        当前部署目录: ${app_dir}" >&2
        return 1
    fi

    # 校验 EnvironmentFile（前置 - 表示可选，跳过）
    local envf
    envf=$(grep -E '^EnvironmentFile=[^-]' "${dst}" | cut -d= -f2-)
    if [ -n "${envf}" ] && [ ! -f "${envf}" ]; then
        echo "[WARN] EnvironmentFile 不存在: ${envf}" >&2
        echo "       建议: cp ${app_dir}/.env.example ${envf}  # 如有模板"
    fi

    systemctl daemon-reload
    return 0
}
