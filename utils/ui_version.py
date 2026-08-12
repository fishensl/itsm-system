"""Vue-only URL compatibility mapping.

The UI-version setting remains as a read-compatible shell for older deployments,
but SSR is no longer a runnable mode.
"""


_VUE_URL_MAP = {
    '/': '/app/', '/devices': '/app/devices', '/tickets': '/app/tickets',
    '/inspections': '/app/inspections', '/inspectors': '/app/inspectors',
    '/task-schedule/': '/app/task-schedule', '/task-templates': '/app/task-templates',
    '/device-check-templates': '/app/device-check-templates', '/customers': '/app/customers',
    '/regions': '/app/regions', '/customer-categories': '/app/customer-categories',
    '/knowledge-base': '/app/knowledge-base', '/knowledge-base/add': '/app/knowledge-base',
    '/faults': '/app/faults', '/reports': '/app/reports',
    '/spare-parts': '/app/spare-parts', '/spare-stocks': '/app/spare-parts?tab=stocks',
    '/purchase-orders': '/app/spare-parts?tab=purchases',
    '/sales-orders': '/app/spare-parts?tab=sales', '/opportunities': '/app/sales?tab=opps',
    '/quotations': '/app/sales?tab=quotations', '/contracts': '/app/sales?tab=contracts',
    '/projects': '/app/sales?tab=projects', '/contract-tasks': '/app/contract-tasks',
    '/rack': '/app/rack', '/topologies': '/app/topologies',
    '/device-types': '/app/device-dicts?tab=types',
    '/device-brands': '/app/device-dicts?tab=brands',
    '/device-network-types': '/app/device-dicts?tab=network-types',
    '/device-custom-fields': '/app/device-dicts?tab=custom-fields',
    '/device-firmwares': '/app/device-firmwares', '/tools': '/app/tools',
    '/tools/network': '/app/tools?tool=network', '/tools/convert': '/app/tools?tool=convert',
    '/tools/packet': '/app/tools?tool=packet', '/system': '/app/system/overview',
    '/system/sidebar': '/app/system/sidebar', '/ai-config': '/app/ai-config',
    '/permissions': '/app/permissions', '/departments/': '/app/system/users?tab=departments',
    '/system/backup': '/app/system/backup',
    '/system/review-checklist': '/app/system/review-checklist',
    '/users': '/app/system/users?tab=users',
}


def get_ui_version():
    return 'vue'


def set_ui_version(version):
    """Keep old callers compatible while refusing to resurrect removed SSR behaviour."""
    if version != 'vue':
        raise ValueError('SSR 已移除，系统仅支持 Vue 界面')
    from models import SystemSetting, db
    row = SystemSetting.query.filter_by(key='ui_version').first()
    if row:
        row.value = 'vue'
    else:
        db.session.add(SystemSetting(key='ui_version', value='vue'))
    db.session.commit()


def sidebar_url(url, force=False):
    """Map historical bookmarks to Vue routes; ``force`` is retained for API compatibility."""
    base = url.split('?')[0]
    if base not in _VUE_URL_MAP:
        return url
    query = url[len(base):] if base != '/' else (url[1:] if url.startswith('/?') else '')
    target = _VUE_URL_MAP[base]
    if query:
        target += ('&' + query.lstrip('?')) if '?' in target else query
    return target


def redirect_home():
    return True
