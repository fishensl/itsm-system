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
    '/inspectors': '/app/inspectors',
    '/task-schedule/': '/app/task-schedule',
    '/task-board': '/app/task-board',
    '/task-templates': '/app/task-templates',
    '/device-check-templates': '/app/device-check-templates',
    '/customers': '/app/customers',
    '/regions': '/app/regions',
    '/customer-categories': '/app/customer-categories',
    '/knowledge-base': '/app/knowledge-base',
    '/knowledge-base/add': '/app/knowledge-base',
    '/faults': '/app/faults',
    '/reports': '/app/reports',
    '/spare-parts': '/app/spare-parts',
    '/spare-stocks': '/app/spare-parts?tab=stocks',
    '/purchase-orders': '/app/spare-parts?tab=purchases',
    '/sales-orders': '/app/spare-parts?tab=sales',
    '/opportunities': '/app/sales?tab=opps',
    '/quotations': '/app/sales?tab=quotations',
    '/contracts': '/app/sales?tab=contracts',
    '/projects': '/app/sales?tab=projects',
    '/contract-tasks': '/app/contract-tasks',
    '/rack': '/app/rack',
    '/topologies': '/app/topologies',
    '/device-types': '/app/device-dicts?tab=types',
    '/device-brands': '/app/device-dicts?tab=brands',
    '/device-network-types': '/app/device-dicts?tab=network-types',
    '/device-custom-fields': '/app/device-dicts?tab=custom-fields',
    '/device-firmwares': '/app/device-firmwares',
    '/tools': '/app/tools',
    '/tools/network': '/app/tools?tool=network',
    '/tools/convert': '/app/tools?tool=convert',
    '/tools/packet': '/app/tools?tool=packet',
    '/system': '/app/system/overview',
    '/system/sidebar': '/app/system/sidebar',
    '/ai-config': '/app/ai-config',
    '/permissions': '/app/permissions',
    '/departments/': '/app/system/users?tab=departments',
    '/system/backup': '/app/system/backup',
    '/system/review-checklist': '/app/system/review-checklist',
    '/users': '/app/system/users?tab=users',
}

# 默认界面：环境变量 > 配置表（无配置表时）；默认 Vue（可在系统设置切回 SSR）
_DEFAULT = os.environ.get('ITSM_UI_VERSION', 'vue')


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


def sidebar_url(url, force=False):
    """侧栏 URL 转换：vue 模式下已迁移页面映射到 /app/*

    force=True：无条件映射（Vue SPA 专用 API 使用，与系统界面版本无关）。
    """
    if not force and get_ui_version() != 'vue':
        return url
    base = url.split('?')[0]
    if base in _VUE_URL_MAP:
        # 保留 query（如 /knowledge-base?category=故障处置 → /app/knowledge-base?category=...）
        q = url[len(base):] if base != '/' else (url[1:] if url.startswith('/?') else '')
        target = _VUE_URL_MAP[base]
        if q:
            if '?' in target:
                # 映射值自带 query（如 /app/spare-parts?tab=stocks）：用 & 拼接
                target = target + '&' + q[1:]
            else:
                target = target + q
        return target
    return url


def redirect_home():
    """首页是否需要重定向到 /app/"""
    return get_ui_version() == 'vue'
