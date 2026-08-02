# -*- coding: utf-8 -*-
"""界面版本切换（SSR ↔ Vue /app/*）

管理员在系统设置切换「默认界面」。切换为 vue 时：
- SSR 侧栏链接按 _VUE_URL_MAP 前缀映射到 /app/*（未迁移模块保持 SSR 路径）
- 首页 / 重定向到 /app/
回退 ssr 时恢复原样（Vue 产物保留，可随时再切）。
"""
import os

# 已迁移到 Vue 的页面：SSR 路径 → /app 路径
_VUE_URL_MAP = {
    '/': '/app/',
    '/devices': '/app/devices',
    '/tickets': '/app/tickets',
    '/inspections': '/app/inspections',
    '/customers': '/app/customers',
    '/knowledge-base': '/app/knowledge-base',
    '/faults': '/app/faults',
    '/reports': '/app/reports',
    '/spare-parts': '/app/spare-parts',
    '/opportunities': '/app/sales',
    '/quotations': '/app/sales',
    '/contracts': '/app/sales',
    '/projects': '/app/sales',
    '/rack': '/app/rack',
    '/topologies': '/app/topologies',
    '/tools': '/app/tools',
    '/users': '/app/system/users',
}

# 默认界面：环境变量 > 配置表（无配置表时）
_DEFAULT = os.environ.get('ITSM_UI_VERSION', 'ssr')


def get_ui_version():
    """当前界面版本：'vue' | 'ssr'（进程级缓存，切换后自动失效由调用方处理）"""
    try:
        from models import SystemSetting
        row = SystemSetting.query.filter_by(key='ui_version').first()
        if row and row.value in ('vue', 'ssr'):
            return row.value
    except Exception:
        pass
    return _DEFAULT


def set_ui_version(version):
    """设置界面版本（vue/ssr）"""
    from models import SystemSetting, db
    row = SystemSetting.query.filter_by(key='ui_version').first()
    if row:
        row.value = version
    else:
        db.session.add(SystemSetting(key='ui_version', value=version))
    db.session.commit()


def sidebar_url(url):
    """侧栏 URL 转换：vue 模式下已迁移页面映射到 /app/*"""
    if get_ui_version() != 'vue':
        return url
    base = url.split('?')[0]
    if base in _VUE_URL_MAP:
        # 保留 query（如 /knowledge-base?category=故障处置 → /app/knowledge-base?category=...）
        q = url[len(base):] if base != '/' else (url[1:] if url.startswith('/?') else '')
        return _VUE_URL_MAP[base] + (q or '')
    return url


def redirect_home():
    """首页是否需要重定向到 /app/"""
    return get_ui_version() == 'vue'
