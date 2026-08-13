#!/usr/bin/env bash
# 发布脚本共享函数。调用方应启用 set -euo pipefail。

restore_previous_frontend() {
    local current_dir="${1:-}" previous_dir="${2:-}" failed_dir="${3:-}"
    if [ -z "${current_dir}" ] || [ -z "${previous_dir}" ] || [ -z "${failed_dir}" ] || \
       [ "${current_dir}" = "/" ] || [ "${previous_dir}" = "/" ] || [ "${failed_dir}" = "/" ] || \
       [ "${current_dir}" = "${previous_dir}" ] || [ "${current_dir}" = "${failed_dir}" ] || \
       [ "${previous_dir}" = "${failed_dir}" ]; then
        echo "[ERROR] 前端恢复目录参数不安全" >&2
        return 1
    fi
    if [ ! -f "${previous_dir}/index.html" ]; then
        echo "[ERROR] 上一版前端不存在或不完整: ${previous_dir}" >&2
        return 1
    fi
    if [ -e "${failed_dir}" ]; then
        echo "[ERROR] 失败版本留存目录已存在: ${failed_dir}" >&2
        return 1
    fi

    if [ -e "${current_dir}" ]; then
        mv -- "${current_dir}" "${failed_dir}" || return 1
    fi
    if [ "${ITSM_RELEASE_FAIL_AFTER_ARCHIVE:-0}" = "1" ] || \
       ! mv -- "${previous_dir}" "${current_dir}"; then
        # 第二步失败时恢复刚归档的当前版，避免 static/app 缺失。
        if [ -e "${failed_dir}" ] && [ ! -e "${current_dir}" ]; then
            mv -- "${failed_dir}" "${current_dir}" || true
        fi
        return 1
    fi
    return 0
}
