# -*- coding: utf-8 -*-
"""Vue SPA 专用 API 蓝图（/api/*）

设计约束：
- 统一响应契约：成功 {"code":0,"data":...} / 失败 {"code":1,"message":...}
- 只服务 Vue 前端；SSR 页面不受影响（随迁随化，不重复实现已有 API）
- 复用 services/ 业务层与 utils/permission 权限体系
- 图标：后端 sidebar 用 bi-*（Bootstrap Icons），此处映射为 Element Plus 图标名
"""
from flask import Blueprint, jsonify, request, current_app, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
import os

from models import db, User
from utils.permission import get_user_permissions, has_permission, require_permission
from utils.sidebar_config import get_user_sidebar_groups
from app import csrf, limiter

vue_api_bp = Blueprint('vue_api', __name__)


# ==================== Vue SPA 静态服务（生产：dist 构建产物） ====================
_APP_DIST = None


def _app_dist_dir():
    """构建产物目录 static/app/（CI 构建后解压于此）；不存在则返回 None（开发走 Vite）"""
    global _APP_DIST
    if _APP_DIST is None:
        candidate = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 'static', 'app')
        _APP_DIST = candidate if os.path.isdir(candidate) else ''
    return _APP_DIST or None


@vue_api_bp.route('/app/', defaults={'path': ''})
@vue_api_bp.route('/app/<path:path>')
def vue_spa(path):
    """SPA 入口：静态文件直出，其余路径回退 index.html（history 路由）"""
    dist = _app_dist_dir()
    if dist is None:
        return fail('前端构建产物未部署（开发环境请使用 Vite dev server :5173）', 404)
    full = os.path.normpath(os.path.join(dist, path))
    if path and os.path.isfile(full):
        return send_from_directory(dist, path)
    # history 路由回退：index.html 由 Vue Router 接管
    return send_from_directory(dist, 'index.html')

# ==================== 统一响应契约 ====================
def ok(data=None, message=''):
    return jsonify({'code': 0, 'data': data, 'message': message})


def fail(message, status=400):
    return jsonify({'code': 1, 'data': None, 'message': message}), status


# ==================== 图标映射：bi-* → Element Plus 图标名 ====================
_ICON_MAP = {
    'bi-speedometer2': 'Odometer', 'bi-tools': 'Tools', 'bi-ticket-detailed': 'Tickets',
    'bi-exclamation-triangle': 'Warning', 'bi-calendar3-week': 'Calendar',
    'bi-person-gear': 'User', 'bi-clipboard-data': 'Document', 'bi-file-earmark-text': 'Document',
    'bi-gear-wide-connected': 'SetUp', 'bi-folder2-open': 'FolderOpened', 'bi-book': 'Notebook',
    'bi-journal-text': 'Document', 'bi-book-half': 'Reading', 'bi-folder-check': 'FolderChecked',
    'bi-briefcase': 'Briefcase', 'bi-plus-circle': 'CirclePlus', 'bi-router': 'Connection',
    'bi-diagram-3': 'Share', 'bi-building': 'OfficeBuilding', 'bi-hdd-rack': 'Monitor',
    'bi-people': 'UserFilled', 'bi-person': 'User', 'bi-lightbulb': 'Lightning',
    'bi-file-earmark-lock': 'Lock', 'bi-archive': 'Box', 'bi-graph-up': 'TrendCharts',
    'bi-shield-check': 'CircleCheck', 'bi-server': 'Monitor', 'bi-cloud': 'Cloudy',
    'bi-sliders': 'Operation', 'bi-wrench-adjustable': 'Tools', 'bi-key': 'Key',
    'bi-shield-lock': 'Lock', 'bi-database': 'Coin', 'bi-robot': 'Cpu', 'bi-hdd-network': 'Monitor',
    'bi-people-fill': 'UserFilled', 'bi-chat-dots': 'ChatDotRound', 'bi-clipboard-check': 'Finished',
    'bi-kanban': 'Files',
}


def _map_icon(bi):
    if not bi:
        return 'Document'
    return _ICON_MAP.get(bi, 'Document')


# ==================== 认证 ====================
@vue_api_bp.route('/api/auth/login', methods=['POST'])
@csrf.exempt  # 必须最外层：Flask-Limiter 包装会吞豁免标记
@limiter.limit('5 per minute;30 per hour', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or request.form
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    user = User.query.filter_by(username=username).first()
    if user and not user.is_active:
        current_app.logger.warning(f'停用账号 [{username}] 尝试登录(Vue)')
        return fail('该账号已停用，请联系管理员', 403)
    if user and user.check_password(password):
        # 明文/pbkdf2 升级逻辑与 SSR 登录一致（显式提交）
        if getattr(user, '_plaintext_upgraded', False):
            db.session.commit()
        elif user.needs_rehash():
            user.set_password(password)
            db.session.commit()
        login_user(user)
        current_app.logger.info(f'用户 [{username}] 登录成功(Vue)')
        return ok({'user': _user_payload(user)})
    current_app.logger.warning(f'用户 [{username}] 登录失败(Vue)')
    return fail('用户名或密码错误', 401)


@vue_api_bp.route('/api/auth/logout', methods=['POST'])
@login_required
def api_logout():
    current_app.logger.info(f'用户 [{current_user.username}] 登出(Vue)')
    logout_user()
    return ok(None)


@vue_api_bp.route('/api/auth/me', methods=['GET'])
@login_required
def api_me():
    return ok(_user_payload(current_user))


@vue_api_bp.route('/api/auth/change-password', methods=['POST'])
@login_required
def api_change_password():
    """自助改密（SPA 弹窗）：校验旧密码 + 新密码强度，成功后强制重新登录"""
    data = request.get_json(silent=True) or {}
    old_pwd = data.get('old_password') or ''
    new_pwd = data.get('new_password') or ''
    if not current_user.check_password(old_pwd):
        return fail('原密码不正确', 400)
    if len(new_pwd) < 6:
        return fail('新密码长度至少 6 位', 400)
    current_user.set_password(new_pwd)
    db.session.commit()
    from blueprints.vue_api_sys import audit_log
    audit_log('user:change_password', 'user', current_user.id, f'用户 {current_user.username} 自助修改密码')
    logout_user()
    return ok(None)


def _user_payload(user):
    """当前用户信息 + 权限码数组（admin 短路全量权限）"""
    return {
        'id': user.id,
        'username': user.username,
        'realname': user.realname or user.username,
        'role': user.role or 'viewer',
        'department_id': user.department_id,
        'region_ids': [r.id for r in user.regions],
        'customer_ids': [c.id for c in user.customers],
        'permissions': get_user_permissions(user),
    }


# ==================== 侧栏（Vue 版数据结构） ====================
@vue_api_bp.route('/api/auth/sidebar-groups', methods=['GET'])
@login_required
def api_sidebar_groups():
    from utils.ui_version import sidebar_url
    groups = get_user_sidebar_groups(current_user)
    out = []
    for g in groups:
        if not g.get('enabled'):
            continue
        item = {
            'key': g['key'],
            'title': g['title'],
            'icon': _map_icon(g.get('icon')),
            'enabled': True,
        }
        if g.get('single_link'):
            sl = g['single_link']
            item['single_link'] = {
                'name': sl.get('name', g['title']),
                # Vue SPA 专属：无条件映射已迁移页面到 /app/*（与系统界面版本无关）
                'url': sidebar_url(sl.get('url', '/'), force=True),
                'icon': _map_icon(sl.get('icon') or g.get('icon')),
            }
        else:
            children = []
            for c in g.get('children', []):
                perm = c.get('perm')
                if perm and not has_permission(perm):
                    continue
                children.append({
                    'name': c['name'],
                    'url': sidebar_url(c['url'], force=True),
                    'icon': _map_icon(c.get('icon')),
                    'perm': perm,
                })
            item['children'] = children
        out.append(item)
    return ok(out)


# ==================== Dashboard ====================
@vue_api_bp.route('/api/dashboard/overview', methods=['GET'])
@login_required
def api_dashboard_overview():
    """Vue 工作台聚合数据：统计卡 + 我的待办 + 快捷入口 + 到期授权 + 最近巡检"""
    from datetime import date, timedelta
    from sqlalchemy import func

    me = current_user
    role = me.role or 'viewer'
    me_realname = me.realname or me.username

    # ---- 统计 ----
    counts = {
        'customer': _count('customers'),
        'device': _count('devices'),
        'inspection': _count('inspections'),
        'ticket': _count('tickets'),
        'fault': _count('faults'),
        'kb': _count('knowledge_base'),
        'opp': _count('opportunities'),
        'contract': _count('contracts'),
        'project': _count('projects'),
        'spare': _count('spare_parts'),
        'region': _count('regions'),
    }

    # ---- 我的待办（工单/巡检/故障 或 商机/合同） ----
    from models import (Ticket, InspectionTask, Fault,
                        Opportunity, Contract, Customer, Device, Inspection)
    customer_map = {c.id: c.name for c in Customer.query.all()}
    my_tasks = []

    if role in ('admin', 'operator') or has_permission('task:schedule'):
        my_tickets = Ticket.query.filter(
            Ticket.assigned_to.in_([me_realname, me.username]),
            ~Ticket.status.in_(['已验收', '已关闭'])
        ).order_by(Ticket.created_at.desc()).limit(8).all()
        for t in my_tickets:
            my_tasks.append({
                'type_label': '工单', 'type_color': 'danger',
                'title': t.title,
                'sub': f"{customer_map.get(t.customer_id, '-')} · {t.priority} · {t.status}",
                'url': f'/app/tickets/{t.id}',
                'time': t.created_at.strftime('%m-%d %H:%M') if t.created_at else '',
                # FAR-时间 升序 = 最新在前，且与任务截止时间同值域可混合排序
                'sort_time': _FAR_EPOCH - _sort_epoch(t.created_at),
            })
        # 巡检待办：与任务看板同规则角色自动匹配（V23 并入我的待办）——
        # 有派发权看全部（含未指派）；主管看本部门；工程师只看自己的
        my_insp = _apply_task_scope(
            InspectionTask.query.filter(
                InspectionTask.status.in_(['待执行', '执行中', '待审核'])),
            current_user,
        )[0].order_by(InspectionTask.id.desc()).limit(5).all()
        for t in my_insp:
            my_tasks.append({
                'type_label': '巡检', 'type_color': 'primary',
                'title': t.title,
                'sub': f"{customer_map.get(t.customer_id, '-')} · {t.status} · {t.task_type}",
                'url': '/app/task-schedule',
                'time': (t.planned_start.strftime('%m-%d') if t.planned_start else '') + '~' +
                        (t.planned_end.strftime('%m-%d') if t.planned_end else ''),
                'sort_time': _sort_epoch(t.planned_end),  # 截止时间升序：最紧迫/已过期置顶
            })
        my_faults = Fault.query.filter(Fault.result != '已解决').order_by(Fault.fault_time.desc()).limit(5).all()
        for f in my_faults:
            my_tasks.append({
                'type_label': '故障', 'type_color': 'warning',
                'title': f.title,
                'sub': f"{customer_map.get(f.customer_id, '-')} · {f.fault_type or '-'}",
                'url': '/app/faults',
                'time': f.fault_time.strftime('%m-%d %H:%M') if f.fault_time else '',
                # FAR-时间 升序 = 最新在前，与任务截止时间同值域可混合排序
                'sort_time': _FAR_EPOCH - _sort_epoch(f.fault_time),
            })
    elif role == 'sales':
        my_opps = Opportunity.query.filter(
            Opportunity.owner.in_([me_realname, me.username]),
            ~Opportunity.stage.in_(['成交', '失败'])
        ).order_by(Opportunity.expected_close_date.asc().nullslast()).limit(8).all()
        for o in my_opps:
            my_tasks.append({
                'type_label': '商机', 'type_color': 'primary',
                'title': o.title,
                'sub': f"{customer_map.get(o.customer_id, '-')} · {o.stage} · {o.expected_amount or 0}",
                'url': '/app/sales?tab=opps',
                'time': o.expected_close_date.strftime('%Y-%m-%d') if o.expected_close_date else '-',
            })
        my_contracts = Contract.query.filter(Contract.status == '执行中') \
            .order_by(Contract.end_date.asc().nullslast()).limit(5).all()
        for c in my_contracts:
            my_tasks.append({
                'type_label': '合同', 'type_color': 'success',
                'title': c.title,
                'sub': f"{customer_map.get(c.customer_id, '-')} · {c.amount or 0}",
                'url': '/app/sales?tab=contracts',
                'time': c.end_date.strftime('%Y-%m-%d') if c.end_date else '-',
            })
    # 合并列表按紧迫度排序（升序）：巡检按计划截止时间（最紧迫/已过期置顶），
    # 工单/故障用 FAR-时间（最新在前，与任务截止同值域混合）；无时间的沉底
    if role in ('admin', 'operator') or has_permission('task:schedule'):
        my_tasks.sort(key=lambda x: x.get('sort_time') or _FAR_EPOCH)
        for _t in my_tasks:
            _t.pop('sort_time', None)
    my_tasks = my_tasks[:12]

    # ---- 即将到期授权 ----
    today = date.today()
    deadline = today + timedelta(days=30)
    expiring_devices = []
    if role in ('admin', 'operator', 'viewer'):
        for d in Device.query.filter(
                Device.license_expiry.isnot(None),
                Device.license_expiry <= deadline
        ).order_by(Device.license_expiry).limit(8).all():
            expiring_devices.append({
                'id': d.id, 'device_name': d.device_name,
                'customer_name': customer_map.get(d.customer_id, '-'),
                'license_expiry': d.license_expiry.strftime('%Y-%m-%d') if d.license_expiry else '',
                'remaining_days': (d.license_expiry - today).days if d.license_expiry else 0,
            })

    # ---- 最近巡检 ----
    recent_inspections = []
    if role in ('admin', 'operator', 'viewer'):
        for i in Inspection.query.order_by(Inspection.id.desc()).limit(5).all():
            recent_inspections.append({
                'id': i.id, 'title': i.title,
                'customer_name': customer_map.get(i.customer_id, '-'),
                'inspection_date': i.inspection_date.strftime('%Y-%m-%d') if i.inspection_date else '',
                'overall_status': i.overall_status,
            })

    # ---- 统计卡（按角色） ----
    def card(label, value, sub, icon, accent, url):
        return {'label': label, 'value': value, 'sub': sub, 'icon': _map_icon(icon),
                'accent': accent, 'url': url}

    metrics = [card('客户总数', counts['customer'], f"{counts['region']} 个地区", 'bi-people', '#2563eb',
                    '/app/customers'),
               card('设备总数', counts['device'], '全部设备', 'bi-hdd-rack', '#059669', '/app/devices'),
               card('巡检记录', counts['inspection'], '全部巡检', 'bi-clipboard-check', '#7c3aed',
                    '/app/inspections'),
               card('工单总数', counts['ticket'], '含历史故障', 'bi-ticket-detailed', '#f59e0b',
                    '/app/tickets'),
               card('知识条目', counts['kb'], '故障案例与手册', 'bi-book', '#0891b2',
                    '/app/knowledge-base?category=故障案例'),
               card('备件档案', counts['spare'], '备件管理', 'bi-archive', '#16a34a', '/app/spare-parts'),
               card('商机跟进', counts['opp'], '销售管线', 'bi-lightbulb', '#475569',
                    '/app/sales?tab=opps'),
               card('合同总数', counts['contract'], '执行跟踪', 'bi-file-earmark-lock', '#ea580c',
                    '/app/sales?tab=contracts')]

    # ---- 快捷入口 ----
    if role == 'admin':
        quick_entries = [
            {'url': '/app/customers', 'title': '客户管理', 'sub': '客户信息维护', 'icon': 'bi-people'},
            {'url': '/app/devices', 'title': '设备管理', 'sub': '设备档案与密码', 'icon': 'bi-hdd-rack'},
            {'url': '/app/tickets', 'title': '工单管理', 'sub': '派单/接单/处理', 'icon': 'bi-ticket-detailed'},
            {'url': '/app/knowledge-base', 'title': '知识库', 'sub': '故障案例与手册', 'icon': 'bi-book'},
            {'url': '/app/system/users', 'title': '用户管理', 'sub': '账号与角色', 'icon': 'bi-people-fill'},
        ]
    elif role == 'operator':
        quick_entries = [
            {'url': '/app/devices', 'title': '设备管理', 'sub': '设备档案', 'icon': 'bi-hdd-rack'},
            {'url': '/app/tickets', 'title': '工单处理', 'sub': '我的工单', 'icon': 'bi-ticket-detailed'},
            {'url': '/app/task-schedule', 'title': '任务安排', 'sub': '执行计划巡检', 'icon': 'bi-calendar3-week'},
            {'url': '/app/inspections', 'title': '巡检记录', 'sub': '提交巡检报告', 'icon': 'bi-clipboard-check'},
            {'url': '/app/knowledge-base', 'title': '知识库', 'sub': '快速查询', 'icon': 'bi-book'},
        ]
    elif role == 'sales':
        quick_entries = [
            {'url': '/app/customers', 'title': '客户管理', 'sub': '客户信息', 'icon': 'bi-people'},
            {'url': '/app/sales?tab=opps', 'title': '商机跟进', 'sub': '阶段推进', 'icon': 'bi-lightbulb'},
            {'url': '/app/sales?tab=quotations', 'title': '报价单', 'sub': '生成报价', 'icon': 'bi-file-earmark-text'},
            {'url': '/app/sales?tab=contracts', 'title': '合同管理', 'sub': '合同执行', 'icon': 'bi-file-earmark-lock'},
            {'url': '/app/sales?tab=projects', 'title': '项目管理', 'sub': '项目进度', 'icon': 'bi-graph-up'},
        ]
    else:
        quick_entries = [
            {'url': '/app/customers', 'title': '客户管理', 'sub': '查看客户', 'icon': 'bi-people'},
            {'url': '/app/devices', 'title': '设备管理', 'sub': '查看设备', 'icon': 'bi-hdd-rack'},
            {'url': '/app/tickets', 'title': '工单管理', 'sub': '查看工单', 'icon': 'bi-ticket-detailed'},
            {'url': '/app/knowledge-base', 'title': '知识库', 'sub': '查看知识', 'icon': 'bi-book'},
        ]

    # 设备类型分布
    device_type_stats = []
    if role in ('admin', 'operator', 'viewer'):
        rows = db.session.query(Device.device_type, func.count(Device.id)) \
            .group_by(Device.device_type).order_by(func.count(Device.id).desc()).all()
        device_type_stats = [[r[0] or '未分类', r[1]] for r in rows]

    return ok({
        'counts': counts,
        'metrics': metrics,
        'quick_entries': quick_entries,
        'my_tasks': my_tasks,
        'expiring_devices': expiring_devices,
        'recent_inspections': recent_inspections,
        'device_type_stats': device_type_stats,
    })


def _count(table):
    from sqlalchemy import text
    try:
        return db.session.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar() or 0
    except Exception:
        return 0


# ==================== 设备管理 ====================
class _FormAdapter:
    """把 JSON dict 适配为表单风格（提供 getlist），复用 services 层现有逻辑"""

    def __init__(self, data):
        self._d = data or {}

    def get(self, key, default=None):
        return self._d.get(key, default)

    def getlist(self, key):
        v = self._d.get(key)
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return [v]

    def to_dict(self):
        return self._d


def _device_payload(d, customer_map=None):
    import json as _json
    iface = []
    if d.interface:
        try:
            iface = _json.loads(d.interface) if isinstance(d.interface, str) else d.interface
        except Exception:
            iface = [d.interface]
    return {
        'id': d.id,
        'customer_id': d.customer_id,
        'customer_name': (customer_map or {}).get(d.customer_id, ''),
        'device_name': d.device_name,
        'device_type': d.device_type or '',
        'brand': d.brand or '',
        'model': d.model or '',
        'serial_number': d.serial_number or '',
        'ip_address': d.ip_address or '',
        'port': d.port,
        'username': d.username or '',
        'has_password': bool(d.password_encrypted),
        'login_method': d.login_method or '',
        'location': d.location or '',
        'interface': iface,
        'os_version': d.os_version or '',
        'rule_version': d.rule_version or '',
        'is_maintenance': bool(d.is_maintenance),
        'is_in_use': bool(d.is_in_use),
        'license_expiry': d.license_expiry.strftime('%Y-%m-%d') if d.license_expiry else '',
        'license_start': d.license_start.strftime('%Y-%m-%d') if d.license_start else '',
        'license_remaining_days': (d.license_expiry - __import__('datetime').date.today()).days
        if d.license_expiry else None,
        'remark': d.remark or '',
        'created_at': d.created_at.strftime('%Y-%m-%d %H:%M') if d.created_at else '',
    }


@vue_api_bp.route('/api/devices', methods=['GET'])
@login_required
@require_permission('device:view')
def api_device_list():
    """设备分页列表（DataTable 数据源）"""
    from models import Device as _Device, Customer as _Customer
    from sqlalchemy.orm import joinedload as _jl

    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    brand = (request.args.get('brand') or '').strip()
    model = (request.args.get('model') or '').strip()
    device_type = (request.args.get('device_type') or '').strip()
    customer_id = request.args.get('customer_id', type=int)
    is_in_use = request.args.get('is_in_use', type=int)

    q = _Device.query.options(
        _jl(_Device.customer).joinedload(_Customer.region_rel)
    )
    if search:
        q = q.filter(_Device.device_name.contains(search) |
                     _Device.ip_address.contains(search) |
                     _Device.brand.contains(search))
    if brand:
        q = q.filter(_Device.brand == brand)
    if model:
        q = q.filter(_Device.model == model)
    if device_type:
        q = q.filter(_Device.device_type == device_type)
    if customer_id:
        q = q.filter(_Device.customer_id == customer_id)
    if is_in_use is not None:
        q = q.filter(_Device.is_in_use == bool(is_in_use))

    total = q.count()
    rows = q.order_by(_Device.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    customer_map = {c.id: c.name for c in _Customer.query.all()}
    return ok({
        'items': [_device_payload(d, customer_map) for d in rows],
        'total': total, 'page': page, 'page_size': page_size,
    })


@vue_api_bp.route('/api/v2/devices/export', methods=['POST'])
@login_required
@require_permission('device:view')
def api_v2_device_export():
    """设备导出（JSON：base64 返回，与 SSR 导出同源；密码列仅 device:reveal 权限）"""
    import base64
    from datetime import date as _date
    from utils.excel_export import export_xlsx
    from utils.permission import has_permission
    from models import Device as _D, Customer as _C
    data = request.get_json(silent=True) or {}
    search = (data.get('search') or '').strip()
    customer_id = data.get('customer_id')
    with_password = bool(data.get('with_password')) and has_permission('device:reveal')
    q = _D.query
    if search:
        q = q.filter(_D.device_name.contains(search) | _D.ip_address.contains(search) |
                     _D.brand.contains(search))
    if customer_id:
        q = q.filter(_D.customer_id == int(customer_id))
    devices = q.order_by(_D.id.desc()).all()
    customer_map = {c.id: c.name for c in _C.query.all()}
    headers = ['所属客户', '设备名称', '设备类型', '品牌', '型号', '序列号', 'IP地址', '端口',
               '登录用户名', '登录密码', '授权截止日期', '授权开始日期', '登录方式', '安装位置',
               '系统版本', '规则库版本', '是否维修', '是否在用', '剩余天数', '备注']
    from utils.crypto import decrypt_password
    rows = []
    for d in devices:
        rows.append([
            customer_map.get(d.customer_id, ''), d.device_name, d.device_type or '',
            d.brand or '', d.model or '', d.serial_number or '', d.ip_address, d.port or 22,
            d.username or '', decrypt_password(d.password_encrypted) if (d.password_encrypted and with_password) else '',
            d.license_expiry.strftime('%Y-%m-%d') if d.license_expiry else '',
            d.license_start.strftime('%Y-%m-%d') if d.license_start else '',
            d.login_method or '', d.location or '', d.os_version or '', d.rule_version or '',
            '是' if d.is_maintenance else '否', '是' if d.is_in_use else '否',
            (d.license_expiry - _date.today()).days if d.license_expiry else '', d.remark or '',
        ])
    if with_password:
        current_app.logger.info('密码导出审计(Vue): 用户[%s] 导出含明文密码的设备清单(%d台), IP=%s',
                                current_user.username, len(devices), request.remote_addr)
    tmp_path, download_name = export_xlsx(headers, rows, f'设备导出_{_date.today().isoformat()}.xlsx',
                                          sheet_name='设备信息')
    with open(tmp_path, 'rb') as fh:
        b64 = base64.b64encode(fh.read()).decode('ascii')
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    return ok({'filename': download_name, 'content': b64})


@vue_api_bp.route('/api/v2/devices/import', methods=['POST'])
@login_required
@require_permission('device:add')
def api_v2_device_import():
    """设备批量导入（multipart import_file；与 SSR 导入同字段映射）"""
    from utils.upload import validate_upload, save_temp_upload, open_excel, cleanup_temp_file
    from services.device_service import _parse_date
    from utils.crypto import encrypt_password as _ep
    from models import Device as _D, Customer as _C
    if 'import_file' not in request.files:
        return fail('请选择要导入的 Excel 文件', 400)
    f = request.files['import_file']
    ALLOWED_EXCEL_EXT = {'.xlsx', '.xls'}
    ok_flag, err, _ = validate_upload(f, ALLOWED_EXCEL_EXT, max_size_mb=20)
    if not ok_flag:
        return fail(err, 400)
    tmp = save_temp_upload(f, suffix='.xlsx')
    created = 0
    errors = []
    try:
        wb, ws, err2 = open_excel(tmp, app=current_app)
        if err2:
            return fail(err2[0], 400)
        header_row = [cell.value for cell in ws[1]]
        col_map = {}
        for idx, h in enumerate(header_row):
            if h:
                col_map[str(h).strip()] = idx
        field_mapping = {
            '所属客户': 'customer_name', '设备名称': 'device_name', '设备类型': 'device_type',
            '品牌': 'brand', '型号': 'model', '序列号': 'serial_number', 'IP地址': 'ip_address',
            '端口': 'port', '登录用户名': 'username', '登录密码': 'password',
            '授权截止日期': 'license_expiry', '授权开始日期': 'license_start', '登录方式': 'login_method',
            '安装位置': 'location', '系统版本': 'os_version', '规则库版本': 'rule_version',
            '备注': 'remark', '是否维修': 'is_maintenance', '是否在用': 'is_in_use',
        }
        customers = {c.name: c for c in _C.query.all()}
        new_devices = []
        for row_idx in range(2, ws.max_row + 1):
            row_data = {}
            for cn, idx in col_map.items():
                val = ws.cell(row=row_idx, column=idx + 1).value
                field = field_mapping.get(cn)
                if field:
                    row_data[field] = str(val).strip() if val else ''
            device_name = row_data.get('device_name', '')
            if not device_name:
                errors.append(f'第{row_idx}行：设备名称为空，跳过')
                continue
            customer = customers.get(row_data.get('customer_name', '')) if row_data.get('customer_name') else None
            if row_data.get('customer_name') and not customer:
                errors.append(f'第{row_idx}行：客户 "{row_data["customer_name"]}" 不存在，已跳过')
                continue
            try:
                plain_password = row_data.get('password', '')
                new_devices.append(_D(
                    customer_id=customer.id if customer else None,
                    device_name=device_name, device_type=row_data.get('device_type', ''),
                    brand=row_data.get('brand', ''), model=row_data.get('model', ''),
                    serial_number=row_data.get('serial_number', ''),
                    ip_address=row_data.get('ip_address', ''),
                    port=int(row_data.get('port', 22)) if row_data.get('port') else 22,
                    username=row_data.get('username', ''),
                    password_encrypted=_ep(plain_password) if plain_password else '',
                    login_method=row_data.get('login_method', ''),
                    os_version=row_data.get('os_version', ''), rule_version=row_data.get('rule_version', ''),
                    is_maintenance=row_data.get('is_maintenance', '') in ('是', '1', 'true', 'True'),
                    is_in_use=row_data.get('is_in_use', '') in ('是', '1', 'true', 'True'),
                    license_expiry=_parse_date(row_data.get('license_expiry')),
                    license_start=_parse_date(row_data.get('license_start')),
                    remark=row_data.get('remark', ''),
                ))
            except Exception as e:
                errors.append(f'第{row_idx}行（{device_name}）：{e}')
        if new_devices:
            try:
                db.session.add_all(new_devices)
                db.session.commit()
                created = len(new_devices)
            except Exception as e:
                db.session.rollback()
                current_app.logger.exception('设备批量导入(Vue)提交失败: %s', e)
                errors.append(f'批量提交失败：{e}')
    finally:
        cleanup_temp_file(tmp)
    return ok({'created': created, 'errors': errors[:20], 'total_errors': len(errors)})


@vue_api_bp.route('/api/devices/<int:device_id>/related', methods=['GET'])
@login_required
@require_permission('device:view')
def api_device_related(device_id):
    """设备反向关联：关联工单（related_device_id）+ 巡检记录（任务 device_ids_json 反查）"""
    from models import Ticket as _TK, InspectionTask as _IT, Inspection as _IC
    tickets = [{'id': t.id, 'number': t.number, 'title': t.title, 'status': t.status,
                'created_at': t.created_at.strftime('%Y-%m-%d') if t.created_at else ''}
               for t in _TK.query.filter_by(related_device_id=device_id)
               .order_by(_TK.id.desc()).limit(50).all()]
    inspections = []
    task_ids = []
    for t in _IT.query.filter(_IT.device_ids_json.isnot(None)).all():
        from utils.json_fields import parse_json
        try:
            ids = {int(x) for x in parse_json(t.device_ids_json, [], 'task.device_ids_json')}
        except (ValueError, TypeError):
            continue
        if device_id in ids:
            task_ids.append(t.id)
    if task_ids:
        rows = _IC.query.filter(_IC.task_id.in_(task_ids)).order_by(_IC.id.desc()).limit(50).all()
        inspections = [{'id': i.id, 'title': i.title, 'task_title': i.task_rel.title if i.task_rel else '',
                        'overall_status': i.overall_status or '', 'review_status': i.review_status or '草稿',
                        'inspection_date': i.inspection_date.strftime('%Y-%m-%d') if i.inspection_date else ''}
                       for i in rows]
    return ok({'tickets': tickets, 'inspections': inspections})


@vue_api_bp.route('/api/devices/<int:device_id>', methods=['GET'])
@login_required
@require_permission('device:view')
def api_device_get(device_id):
    from models import Device as _Device
    d = _Device.query.get_or_404(device_id)
    return ok(_device_payload(d, {d.customer_id: d.customer.name if d.customer else ''}))


@vue_api_bp.route('/api/devices', methods=['POST'])
@login_required
@require_permission('device:add')
def api_device_create():
    from services.device_service import create_device_from_form
    data = request.get_json(silent=True) or {}
    # checkbox 归一化：JSON boolean → service 期望 'on'
    form = dict(data)
    form['is_maintenance'] = 'on' if data.get('is_maintenance') else ''
    form['is_in_use'] = 'on' if data.get('is_in_use', True) else ''
    try:
        d = create_device_from_form(_FormAdapter(form))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '设备创建失败', 400)
    _sync_device_count(d.customer_id)
    return ok({'id': d.id})


@vue_api_bp.route('/api/devices/<int:device_id>', methods=['PUT'])
@login_required
@require_permission('device:edit')
def api_device_update(device_id):
    from services.device_service import update_device_from_form
    from flask_login import current_user as _cu
    data = request.get_json(silent=True) or {}
    form = dict(data)
    form['is_maintenance'] = 'on' if data.get('is_maintenance') else ''
    form['is_in_use'] = 'on' if data.get('is_in_use') else ''
    form['changed_by_name'] = _cu.realname or _cu.username
    try:
        d = update_device_from_form(device_id, _FormAdapter(form))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '设备更新失败', 400)
    _sync_device_count(d.customer_id)
    return ok({'id': d.id})


@vue_api_bp.route('/api/devices/<int:device_id>', methods=['DELETE'])
@login_required
@require_permission('device:delete')
def api_device_delete(device_id):
    from services.device_service import delete_device
    from models import Device as _D
    d = _D.query.get_or_404(device_id)
    from blueprints.vue_api_sys import audit_log
    audit_log('device:delete', 'device', device_id, f'删除设备「{d.device_name}」')
    try:
        delete_device(device_id)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '设备删除失败', 400)
    return ok(None)


@vue_api_bp.route('/api/v2/devices/<int:device_id>/reveal-password', methods=['POST'])
@login_required
@require_permission('device:reveal')
def api_device_reveal_password(device_id):
    """查看设备明文密码（审计）。

    注意：路径用 /api/v2 前缀——blueprints/asset 已有同路径 /api/devices/<id>/reveal-password
    （SSR 前端在用），注册顺序上 asset 先注册，同 rule 会被遮蔽。
    """
    from utils.crypto import decrypt_password
    from models import Device as _Device, PasswordHistory as _PH
    history_id = request.get_json(silent=True) or {}
    history_id = history_id.get('history_id')
    d = _Device.query.get_or_404(device_id)
    if history_id:
        h = _PH.query.filter_by(id=int(history_id), device_id=device_id).first()
        if not h:
            return fail('历史记录不存在', 404)
        pwd = decrypt_password(h.password_encrypted) if h.password_encrypted else ''
        kind = f'历史密码(#{h.id})'
    else:
        pwd = decrypt_password(d.password_encrypted) if d.password_encrypted else ''
        kind = '当前密码'
    current_app.logger.info(
        '密码查看审计(Vue): 用户[%s] 查看设备[%s](id=%s) %s, IP=%s',
        current_user.username, d.device_name, d.id, kind, request.remote_addr)
    # 审计写表（供 admin 审计查询页）
    from blueprints.vue_api_sys import audit_log
    audit_log('device:reveal', 'device', d.id, f'查看设备「{d.device_name}」{kind}')
    return ok({'password': pwd})


@vue_api_bp.route('/api/v2/devices/<int:device_id>/password-history', methods=['GET'])
@login_required
@require_permission('device:view')
def api_device_password_history(device_id):
    """历史密码列表（不含明文）"""
    from models import PasswordHistory as _PH
    rows = _PH.query.filter_by(device_id=device_id)\
        .order_by(_PH.id.desc()).limit(50).all()
    return ok([{
        'id': h.id,
        'changed_by': h.changed_by or '-',
        'created_at': h.created_at.strftime('%Y-%m-%d %H:%M') if h.created_at else '-',
        'remark': h.remark or '-',
    } for h in rows])


# ==================== 设备配置备份（V22：巡检同步可见 + 受控下载/在线查看） ====================
@vue_api_bp.route('/api/devices/<int:device_id>/config-backups', methods=['GET'])
@login_required
@require_permission('device:view')
def api_device_config_backups(device_id):
    """设备配置备份列表（含巡检上传同步的记录）"""
    from models import DeviceConfigBackup as _DCB
    rows = _DCB.query.filter_by(device_id=device_id).order_by(_DCB.id.desc()).limit(50).all()
    return ok([{
        'id': b.id,
        'backup_type': b.backup_type or '',
        'backup_method': b.backup_method or '',
        'backup_date': b.backup_date.strftime('%Y-%m-%d') if b.backup_date else '',
        'has_content': bool(b.config_content),
        'has_file': bool(b.file_path),
        'file_name': (b.file_path or '').split('/')[-1] or '',
        'checksum': (b.checksum or '')[:10],
        'created_by': b.created_by or '',
        'created_at': b.created_at.strftime('%Y-%m-%d %H:%M') if b.created_at else '',
    } for b in rows])


@vue_api_bp.route('/api/devices/config-backup/<int:backup_id>/download', methods=['GET'])
@login_required
@require_permission('device:view')
def api_device_config_backup_download(backup_id):
    """配置备份文件受控下载（防路径穿越，替代静态裸暴露）"""
    from models import DeviceConfigBackup as _DCB
    b = _DCB.query.get_or_404(backup_id)
    if not b.file_path:
        return fail('该备份无附件文件', 404)
    full = os.path.realpath(os.path.join('static', b.file_path))
    base = os.path.realpath(os.path.join('static', 'uploads'))
    if not full.startswith(base + os.sep) or not os.path.isfile(full):
        return fail('文件不存在', 404)
    return send_from_directory(os.path.dirname(full), os.path.basename(full), as_attachment=True)


@vue_api_bp.route('/api/devices/config-backup/<int:backup_id>/content', methods=['GET'])
@login_required
@require_permission('device:view')
def api_device_config_backup_content(backup_id):
    """配置文本在线查看"""
    from models import DeviceConfigBackup as _DCB
    b = _DCB.query.get_or_404(backup_id)
    return ok({'id': b.id, 'content': b.config_content or ''})


@vue_api_bp.route('/api/devices/<int:device_id>/config-backup', methods=['POST'])
@login_required
@require_permission('device:edit')
def api_device_config_backup_add(device_id):
    """新增配置备份（multipart：config_content / backup_type / config_file）"""
    import hashlib
    from datetime import date as _date
    from werkzeug.utils import secure_filename
    from models import DeviceConfigBackup as _DCB
    from models import Device as _D
    _D.query.get_or_404(device_id)
    content = request.form.get('config_content', '')
    backup_type = request.form.get('backup_type', '运行配置')
    backup_method = request.form.get('backup_method', '手动输入')
    file_path = ''
    f = request.files.get('config_file')
    if f and f.filename:
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'configs', str(device_id))
        os.makedirs(upload_dir, exist_ok=True)
        safe_name = secure_filename(f.filename) or 'config.txt'
        from datetime import datetime as _dt
        ts = _dt.now().strftime('%Y%m%d_%H%M%S')
        name_base, name_ext = os.path.splitext(safe_name)
        safe_name = f'{name_base}_{ts}{name_ext}'
        full_path = os.path.join(upload_dir, safe_name)
        f.save(full_path)
        file_path = f'uploads/configs/{device_id}/{safe_name}'
        backup_method = '文件上传'
        if not content:
            try:
                with open(full_path, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
            except Exception:
                pass
    if not content and not file_path:
        return fail('请填写配置内容或上传配置文件', 400)
    checksum = hashlib.md5(content.encode('utf-8')).hexdigest() if content else ''
    backup = _DCB(
        device_id=device_id, backup_type=backup_type, config_content=content,
        backup_method=backup_method, backup_date=_date.today(),
        file_path=file_path, checksum=checksum,
        created_by=(current_user.realname or current_user.username),
    )
    db.session.add(backup)
    db.session.commit()
    return ok({'id': backup.id})


@vue_api_bp.route('/api/devices/config-backup/<int:backup_id>/delete', methods=['POST'])
@login_required
@require_permission('device:delete')
def api_device_config_backup_delete(backup_id):
    """删除配置备份（含关联文件）"""
    import os as _os
    from models import DeviceConfigBackup as _DCB
    backup = _DCB.query.get_or_404(backup_id)
    if backup.file_path:
        full = _os.path.join(current_app.root_path, 'static', backup.file_path.replace('/', _os.sep))
        if _os.path.exists(full):
            try:
                _os.remove(full)
            except Exception:
                pass
    db.session.delete(backup)
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/devices/config-backup/<int:backup_id>/rollback', methods=['POST'])
@login_required
@require_permission('device:edit')
def api_device_config_backup_rollback(backup_id):
    """回滚：把选中版本内容写为新备份（标记来源，不覆盖历史）"""
    import hashlib
    from datetime import date as _date
    from models import DeviceConfigBackup as _DCB
    src = _DCB.query.get_or_404(backup_id)
    content = src.config_content or ''
    checksum = hashlib.md5(content.encode('utf-8')).hexdigest() if content else ''
    backup = _DCB(
        device_id=src.device_id, backup_type=src.backup_type, config_content=content,
        backup_method=f'回滚自 #{src.id}', backup_date=_date.today(),
        checksum=checksum,
        created_by=(current_user.realname or current_user.username),
    )
    db.session.add(backup)
    db.session.commit()
    return ok({'id': backup.id})


@vue_api_bp.route('/api/devices/config-backup/diff', methods=['GET'])
@login_required
@require_permission('device:view')
def api_device_config_backup_diff():
    """两版本逐行对比"""
    from blueprints.asset.config_backups import _compute_config_diff
    from models import DeviceConfigBackup as _DCB
    a_id = request.args.get('a', type=int)
    b_id = request.args.get('b', type=int)
    if not a_id or not b_id or a_id == b_id:
        return fail('请选择两个不同的版本进行对比', 400)
    ba = _DCB.query.get(a_id)
    bb = _DCB.query.get(b_id)
    if not ba or not bb:
        return fail('备份版本不存在', 404)
    return ok({'lines': _compute_config_diff(ba.config_content or '', bb.config_content or '')})


def _sync_device_count(customer_id):
    """同步客户 device_count 冗余字段（与 asset 蓝图一致）"""
    if not customer_id:
        return
    from models import Customer as _C
    from services.customer_service import _calculate_tier
    cnt = _count_by('devices', 'customer_id', customer_id)
    c = _C.query.get(customer_id)
    if c:
        c.device_count = cnt
        auto_tier = _calculate_tier(cnt, c.has_onsite, c.has_drill)
        if c.level not in ('核心', '重点', '常规') or not c.level:
            c.level = auto_tier
        db.session.commit()


def _count_by(table, col, value):
    from sqlalchemy import text
    return db.session.execute(
        text(f'SELECT COUNT(*) FROM {table} WHERE {col} = :v'), {'v': value}).scalar() or 0


# ==================== 通知中心 ====================
from utils.notifications import notify  # noqa: E402  (统一入口，详见 utils/notifications.py)


@vue_api_bp.route('/api/notifications', methods=['GET'])
@login_required
def api_notifications():
    """通知列表：全部（按时间倒序，limit 50）"""
    from models import Notification
    rows = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.id.desc()).limit(50).all()
    return ok({'items': [{
        'id': n.id, 'category': n.category, 'title': n.title,
        'content': n.content or '', 'link': n.link, 'is_read': bool(n.is_read),
        'created_at': n.created_at.strftime('%m-%d %H:%M') if n.created_at else '',
    } for n in rows]})


@vue_api_bp.route('/api/notifications/unread-count', methods=['GET'])
@login_required
def api_notifications_unread():
    from models import Notification
    cnt = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return ok({'unread': cnt})


@vue_api_bp.route('/api/notifications/read', methods=['POST'])
@login_required
def api_notifications_read():
    """已读：传 ids 数组或全部已读（不传 ids）"""
    from models import Notification
    data = request.get_json(silent=True) or {}
    ids = data.get('ids')
    if ids:
        Notification.query.filter(
            Notification.id.in_(ids), Notification.user_id == current_user.id
        ).update({'is_read': True}, synchronize_session=False)
    else:
        Notification.query.filter_by(user_id=current_user.id, is_read=False)\
            .update({'is_read': True}, synchronize_session=False)
    db.session.commit()
    return ok(None)


# ==================== 全局搜索 ====================
@vue_api_bp.route('/api/search', methods=['GET'])
@login_required
def api_global_search():
    """跨模块搜索：设备/客户/工单/知识库，各限 5 条，按权限过滤"""
    q = (request.args.get('q') or '').strip()
    if not q or len(q) < 2:
        return ok({'devices': [], 'customers': [], 'tickets': [], 'knowledge': []})
    result = {'devices': [], 'customers': [], 'tickets': [], 'knowledge': []}

    if has_permission('device:view'):
        from models import Device, Customer
        cname_map = {c.id: c.name for c in Customer.query.all()}
        rows = Device.query.filter(
            Device.device_name.contains(q) | Device.ip_address.contains(q)
        ).order_by(Device.id.desc()).limit(5).all()
        result['devices'] = [{'id': d.id, 'title': d.device_name,
                              'sub': f"{cname_map.get(d.customer_id, '')} · {d.ip_address or ''}"}
                             for d in rows]

    if has_permission('customer:view'):
        from models import Customer
        rows = Customer.query.filter(
            Customer.name.contains(q) | Customer.contact_person.contains(q) |
            Customer.phone.contains(q)
        ).order_by(Customer.id.desc()).limit(5).all()
        result['customers'] = [{'id': c.id, 'title': c.name,
                                'sub': f"{c.contact_person or ''} · {c.phone or ''}"} for c in rows]

    if has_permission('ticket:view'):
        from models import Ticket
        rows = Ticket.query.filter(Ticket.title.contains(q) | Ticket.number.contains(q))\
            .order_by(Ticket.id.desc()).limit(5).all()
        result['tickets'] = [{'id': t.id, 'title': t.title,
                              'sub': f"{t.number} · {t.status}"} for t in rows]

    if has_permission('kb:view'):
        from models import KnowledgeBase
        rows = KnowledgeBase.query.filter(KnowledgeBase.title.contains(q))\
            .order_by(KnowledgeBase.id.desc()).limit(5).all()
        result['knowledge'] = [{'id': k.id, 'title': k.title,
                                'sub': k.category or ''} for k in rows]

    return ok(result)


# ==================== 任务看板（巡检任务） ====================
_TASK_STATUS_TAG = {'待执行': 'danger', '执行中': 'warning', '已完成': 'success', '已取消': 'info'}


_FAR_EPOCH = 4102444800  # 2100-01-01 哨兵：无时间项的待办沉底（升序排序时排最后）


def _sort_epoch(v):
    """datetime/date → 可比较 epoch 秒（PG 的 Date 列返回 date，无 .timestamp()）；None → 哨兵"""
    if v is None:
        return _FAR_EPOCH
    from datetime import datetime as _dt
    if isinstance(v, _dt):
        return v.timestamp()
    return _dt(v.year, v.month, v.day).timestamp()


def _apply_task_scope(query, user):
    """任务数据角色自动匹配（看板 / 工作台待办共用）：
    - 有 task:dispatch → 全部（含未指派）
    - 部门主管（无派发权）→ 本部门任务 + 未指派 + 本人派发
    - 其余（普通工程师）→ 仅指派给自己的任务
    返回 (query, scope: 'all'|'dept'|'mine')
    """
    from models import InspectionTask as _IT, User as _U
    from sqlalchemy import or_ as _or_
    from utils.permission import has_permission as _hp, is_supervisor as _sup

    if _hp('task:dispatch'):
        return query, 'all'
    if _sup(user) and getattr(user, 'department_id', None):
        dept_user_ids = [u.id for u in
                         _U.query.filter_by(department_id=user.department_id).all()]
        if dept_user_ids:
            query = query.filter(_or_(
                _IT.assigned_to_user_id.in_(dept_user_ids),
                _IT.assigned_to_user_id.is_(None),
                _IT.dispatched_by == user.id,
            ))
        return query, 'dept'
    return query.filter(_IT.assigned_to_user_id == user.id), 'mine'


def _task_payload(t, customer_map=None):
    from datetime import date
    today = date.today()
    overdue = (t.status in ('待执行', '执行中') and t.planned_end and t.planned_end < today)
    return {
        'id': t.id,
        'title': t.title,
        'status': t.status,
        'task_type': t.task_type or '',
        'customer_id': t.customer_id,
        'customer_name': (customer_map or {}).get(t.customer_id, ''),
        'planned_start': t.planned_start.strftime('%m-%d') if t.planned_start else '',
        'planned_end': t.planned_end.strftime('%m-%d') if t.planned_end else '',
        'assigned_to_user_id': t.assigned_to_user_id,
        'assigned_to_name': t.assignee_rel.realname or t.assignee_rel.username
        if t.assignee_rel else '',
        'estimated_effort': t.estimated_effort,
        'actual_effort': t.actual_effort,
        'overdue': overdue,
        'priority': t.priority or '中',
    }


@vue_api_bp.route('/api/task-board', methods=['GET'])
@login_required
@require_permission('task:schedule')
def api_task_board():
    """任务看板：按状态分组；逾期任务标记；支持客户/负责人筛选。

    角色自动匹配（V22）：有 task:dispatch 看全部；部门主管（无派发权）只看本部门
    （含未指派与本人派发）；普通工程师只看指派给自己的任务。
    """
    from models import InspectionTask as _IT, Customer as _C
    from sqlalchemy.orm import joinedload as _jl

    customer_id = request.args.get('customer_id', type=int)
    assignee_id = request.args.get('assignee_id', type=int)
    show_cancelled = request.args.get('show_cancelled') == '1'

    q = _IT.query.options(
        _jl(_IT.customer_rel), _jl(_IT.assignee_rel),
    )
    if customer_id:
        q = q.filter(_IT.customer_id == customer_id)
    if assignee_id:
        q = q.filter(_IT.assigned_to_user_id == assignee_id)
    if not show_cancelled:
        q = q.filter(_IT.status != '已取消')

    # 角色自动匹配：非派发权用户强制收窄数据范围（显式筛选仅起进一步收窄作用）
    q, scope = _apply_task_scope(q, current_user)

    tasks = q.order_by(_IT.planned_start.asc().nullslast(), _IT.id.desc()).all()

    customer_map = {c.id: c.name for c in _C.query.all()}
    groups = {}
    for st in ('待执行', '执行中', '待审核', '已完成'):
        groups[st] = [_task_payload(t, customer_map) for t in tasks if t.status == st]

    # 汇总
    return ok({
        'groups': groups,
        'status_tag': _TASK_STATUS_TAG,
        'total': len(tasks),
        'pending': len(groups['待执行']),
        'running': len(groups['执行中']),
        'reviewing': len(groups['待审核']),
        'done': len(groups['已完成']),
        'scope': scope,
        'scope_label': {'all': '全部任务', 'dept': '部门任务', 'mine': '我的任务'}[scope],
    })


@vue_api_bp.route('/api/task-board/<int:task_id>/status', methods=['POST'])
@login_required
@require_permission('task:dispatch')
def api_task_board_status(task_id):
    """看板内状态流转：复用服务层状态机（校验 + local_now 时间戳维护）"""
    from models import InspectionTask as _IT
    from services.task_schedule_service import apply_task_status
    data = request.get_json(silent=True) or {}
    status = data.get('status', '')
    t = _IT.query.get_or_404(task_id)
    try:
        apply_task_status(t, status)
    except ValueError as e:
        db.session.rollback()
        return fail(str(e), 400)
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/dicts/task-board', methods=['GET'])
@login_required
@require_permission('task:schedule')
def api_task_board_dicts():
    from models import Customer as _C, User as _U, InspectionTask as _IT
    from sqlalchemy import or_ as _or_
    from utils.permission import has_permission as _hp, is_supervisor as _sup

    me = current_user
    # 客户下拉：派发权看全部；否则优先直接关联客户，无关联时按负责区域过滤
    if _hp('task:dispatch'):
        customers = [{'id': c.id, 'name': c.name} for c in _C.query.order_by(_C.name).all()]
    else:
        cust_ids = [c.id for c in me.customers]
        region_ids = [r.id for r in me.regions]
        qc = _C.query.order_by(_C.name)
        if cust_ids or region_ids:
            conds = []
            if cust_ids:
                conds.append(_C.id.in_(cust_ids))
            if region_ids:
                conds.append(_C.region_id.in_(region_ids))
            qc = qc.filter(_or_(*conds))
        customers = [{'id': c.id, 'name': c.name} for c in qc.all()]

    # 负责人下拉：派发权看全部有任务用户；主管看部门成员；否则仅自己
    if _hp('task:dispatch'):
        uq = _U.query.filter_by(is_active=True).order_by(_U.realname)
        assignee_users = [u for u in uq.all()
                          if _IT.query.filter_by(assigned_to_user_id=u.id).first()]
    elif _sup(me) and me.department_id:
        dept_ids = [u.id for u in _U.query.filter_by(department_id=me.department_id).all()]
        assignee_users = [u for u in _U.query.filter(
            _U.id.in_(dept_ids), _U.is_active.is_(True)).order_by(_U.realname).all()
            if _IT.query.filter_by(assigned_to_user_id=u.id).first()]
    else:
        assignee_users = [me] if _IT.query.filter_by(assigned_to_user_id=me.id).first() else []
    assignees = [{'id': u.id, 'name': u.realname or u.username} for u in assignee_users]
    return ok({'customers': customers, 'assignees': assignees})
def _ticket_payload(t, customer_map=None):
    from services.ticket_service import ticket_completeness
    from models import Device as _D
    complete, missing = ticket_completeness(t)
    related_device = _D.query.get(t.related_device_id) if t.related_device_id else None
    return {
        'id': t.id,
        'number': t.number,
        'title': t.title,
        'status': t.status,
        'priority': t.priority,
        'customer_id': t.customer_id,
        'customer_name': (customer_map or {}).get(t.customer_id, ''),
        'related_device_id': t.related_device_id,
        'related_device_name': related_device.device_name if related_device else '',
        'assigned_to': t.assigned_to or '',
        'created_by': t.created_by or '',
        'created_at': t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else '',
        'fault_category_id': t.fault_category_id,
        'severity_level': t.severity_level or '',
        'source_type': t.source_type or '',
        'diagnosis': t.diagnosis or '',
        'solution': t.solution or '',
        'description': t.description or '',
        'audit_status': t.audit_status or '',
        'audit_by': t.audit_by or '',
        'audit_at': t.audit_at.strftime('%Y-%m-%d %H:%M') if t.audit_at else '',
        'audit_comment': t.audit_comment or '',
        'accept_status': t.accept_status or '',
        'accept_comment': t.accept_comment or '',
        'report_file': bool(t.report_file),
        'report_name': (t.report_file or '').split('/')[-1] or '',
        'complete': complete,
        'missing_fields': missing,
        'assigned_at': t.assigned_at.strftime('%Y-%m-%d %H:%M') if t.assigned_at else '',
        'accepted_at': t.accepted_at.strftime('%Y-%m-%d %H:%M') if t.accepted_at else '',
        'completed_at': t.completed_at.strftime('%Y-%m-%d %H:%M') if t.completed_at else '',
    }


def _ticket_logs(ticket_id):
    from models import TicketLog
    rows = TicketLog.query.filter_by(ticket_id=ticket_id)\
        .order_by(TicketLog.id.desc()).limit(50).all()
    return [{'action': x.action, 'operator': x.operator or '',
             'comment': x.comment or '',
             'created_at': x.created_at.strftime('%m-%d %H:%M') if x.created_at else ''}
            for x in rows]


@vue_api_bp.route('/api/tickets', methods=['GET'])
@login_required
@require_permission('ticket:view')
def api_ticket_list():
    from models import Ticket as _T, Customer as _C
    from datetime import date as _date
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    status = (request.args.get('status') or '').strip()
    priority = (request.args.get('priority') or '').strip()
    customer_id = request.args.get('customer_id', type=int)
    scope = (request.args.get('scope') or 'all').strip()
    date_from = request.args.get('date_from') or ''
    date_to = request.args.get('date_to') or ''
    incomplete_only = request.args.get('incomplete_only', type=int) == 1

    q = _T.query
    if search:
        q = q.filter(_T.title.contains(search) | _T.number.contains(search))
    if status:
        q = q.filter(_T.status == status)
    if priority:
        q = q.filter(_T.priority == priority)
    if customer_id:
        q = q.filter(_T.customer_id == customer_id)
    if scope == 'mine':
        me = current_user.realname or current_user.username
        q = q.filter((_T.assigned_to == me) | (_T.created_by == me))
    if date_from:
        try:
            q = q.filter(_T.created_at >= _date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(_T.created_at <= _date.fromisoformat(date_to))
        except ValueError:
            pass
    rows_all = q.order_by(_T.id.desc()).all()
    if incomplete_only:
        from services.ticket_service import ticket_completeness
        rows_all = [t for t in rows_all if not ticket_completeness(t)[0]]
    total = len(rows_all)
    rows = rows_all[(page - 1) * page_size: page * page_size]
    customer_map = {c.id: c.name for c in _C.query.all()}
    return ok({'items': [_ticket_payload(t, customer_map) for t in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/tickets/<int:ticket_id>', methods=['GET'])
@login_required
@require_permission('ticket:view')
def api_ticket_get(ticket_id):
    from models import Ticket as _T
    t = _T.query.get_or_404(ticket_id)
    payload = _ticket_payload(t)
    payload['logs'] = _ticket_logs(t.id)
    return ok(payload)


@vue_api_bp.route('/api/tickets', methods=['POST'])
@login_required
@require_permission('ticket:add')
def api_ticket_create():
    from services.ticket_service import create_ticket, assign_ticket, accept_ticket
    data = request.get_json(silent=True) or {}
    me = current_user.realname or current_user.username
    try:
        t = create_ticket(data, me)
        # 自接单：录单+派单+接单一体
        if data.get('dispatch_mode') == 'self_accept':
            assign_ticket(t.id, me, me, remark='录单时自行接单')
            accept_ticket(t.id, me, remark='录单即开工')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '工单创建失败', 400)
    return ok({'id': t.id, 'number': t.number})


@vue_api_bp.route('/api/tickets/<int:ticket_id>', methods=['PUT'])
@login_required
@require_permission('ticket:edit')
def api_ticket_update(ticket_id):
    from services.ticket_service import update_ticket
    data = request.get_json(silent=True) or {}
    me = current_user.realname or current_user.username
    try:
        update_ticket(ticket_id, data, me)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '工单更新失败', 400)
    return ok(None)


@vue_api_bp.route('/api/tickets/<int:ticket_id>', methods=['DELETE'])
@login_required
@require_permission('ticket:delete')
def api_ticket_delete(ticket_id):
    from models import Ticket as _T, TicketLog
    t = _T.query.get_or_404(ticket_id)
    current_app.logger.info(
        '工单删除审计(Vue): 用户[%s] 删除工单[%s](id=%s), IP=%s',
        current_user.username, t.number, t.id, request.remote_addr)
    from blueprints.vue_api_sys import audit_log
    audit_log('ticket:delete', 'ticket', t.id, f'删除工单「{t.number}」')
    TicketLog.query.filter_by(ticket_id=ticket_id).delete()
    _T.query.filter_by(id=ticket_id).delete()
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/tickets/<int:ticket_id>/archive-as-case', methods=['POST'])
@login_required
@require_permission('kb:add')
def api_ticket_archive_as_case(ticket_id):
    """归档为知识库案例（仅已关闭/已验收/已完成；内容由诊断/方案/描述拼装）"""
    from models import Ticket as _T, KnowledgeBase as _KB
    t = _T.query.get_or_404(ticket_id)
    if t.status not in ('已关闭', '已验收', '已完成'):
        return fail(f'仅已关闭/已验收/已完成工单可归档（当前状态：{t.status}）', 400)
    content_parts = []
    if t.diagnosis:
        content_parts.append(f'## 诊断分析\n\n{t.diagnosis}\n')
    if t.solution:
        content_parts.append(f'## 解决方案\n\n{t.solution}\n')
    if t.description:
        content_parts.append(f'## 故障描述\n\n{t.description}\n')
    if t.fault_category_level1:
        rc = [f'一级分类：{t.fault_category_level1}']
        if t.fault_category_level2:
            rc.append(f'二级分类：{t.fault_category_level2}')
        if t.root_cause_category:
            rc.append(f'根因分类：{t.root_cause_category}')
        if t.severity_level:
            rc.append(f'严重级别：{t.severity_level}')
        content_parts.append('## 根因分析\n\n' + '\n'.join(rc) + '\n')
    content = '\n\n'.join(content_parts) if content_parts else f'（工单 #{t.number} 归档）'
    tags = ['工单归档']
    if t.fault_category_level1:
        tags.append(t.fault_category_level1)
    if t.root_cause_category:
        tags.append(t.root_cause_category)
    kb = _KB(
        title=f'【案例】{t.title}', category='故障处置', content=content,
        related_ticket_id=t.id, tags=','.join(tags),
        created_by=current_user.realname or current_user.username,
    )
    db.session.add(kb)
    db.session.commit()
    from blueprints.vue_api_sys import audit_log
    audit_log('kb:create', 'kb', kb.id, f'工单 {t.number} 归档为知识库案例 #{kb.id}')
    return ok({'id': kb.id})


@vue_api_bp.route('/api/tickets/<int:ticket_id>/action', methods=['POST'])
@login_required
@require_permission('ticket:edit')
def api_ticket_action(ticket_id):
    """工单状态机动作：assign/accept/submit/audit/accept_check/close

    submit 支持 multipart 表单（report_file 处理报告 + diagnosis + solution + remark），
    JSON 请求也可带 diagnosis/solution（无文件）。
    """
    from services.ticket_service import (assign_ticket, accept_ticket, submit_ticket,
                                         audit_ticket, accept_check_ticket, close_ticket,
                                         unassign_ticket)
    data = request.get_json(silent=True) or {}
    if request.form:
        for k, v in request.form.items():
            data[k] = v
    action = data.get('action', '')
    me = current_user.realname or current_user.username
    remark = data.get('remark', '')
    report_path = ''
    try:
        if action == 'submit' and request.files.get('report_file'):
            from utils.upload import validate_upload
            from models import Ticket as _T3
            ALLOWED_REPORT_EXT = {'.doc', '.docx', '.pdf', '.xlsx', '.xls',
                                  '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.zip'}
            f = request.files['report_file']
            ok_flag, err, safe_name = validate_upload(f, ALLOWED_REPORT_EXT, max_size_mb=50)
            if not ok_flag:
                return fail(err or '文件校验失败')
            t3 = _T3.query.get_or_404(ticket_id)
            os.makedirs(os.path.join('static', 'uploads', 'ticket_reports', str(t3.id)), exist_ok=True)
            report_path = '/'.join(('uploads', 'ticket_reports', str(t3.id), safe_name))
            f.save(os.path.join('static', report_path))

        if action == 'assign':
            if not data.get('assignee'):
                return fail('请填写指派处理人', 400)
            assign_ticket(ticket_id, data['assignee'], me, remark or f'派给 {data["assignee"]}')
        elif action == 'accept':
            accept_ticket(ticket_id, me, remark or '已接单，开始处理')
        elif action == 'submit':
            submit_ticket(ticket_id, me, remark or '提交审核',
                          diagnosis=data.get('diagnosis'), solution=data.get('solution'),
                          report_path=report_path, submitter_user_id=current_user.id,
                          note=data.get('note') or '')
        elif action == 'audit':
            approved = bool(data.get('approved'))
            audit_ticket(ticket_id, approved, me, remark or ('审核通过' if approved else '退回修改'),
                         requirements=data.get('requirements') or '')
        elif action == 'accept_check':
            approved = bool(data.get('approved'))
            accept_check_ticket(ticket_id, me, remark or ('客户验收通过' if approved else '客户验收退回'),
                                approved=approved)
        elif action == 'close':
            close_ticket(ticket_id, me, remark or '关闭工单')
        elif action == 'reassign':
            unassign_ticket(ticket_id, me, remark or '撤回重派')
        else:
            return fail(f'未知动作: {action}', 400)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '操作失败', 400)

    # ---- 事件源：通知被指派/创建人（派单与审核结果） ----
    try:
        from models import Ticket as _T2, User as _U2
        t = _T2.query.get(ticket_id)
        target_name = None
        if action == 'assign':
            target_name = data.get('assignee')
        elif action in ('audit', 'accept_check', 'close'):
            target_name = t.created_by or (t.assigned_to if action == 'close' else None)
        if target_name:
            target = _U2.query.filter(
                (_U2.username == target_name) | (_U2.realname == target_name)).first()
            if target and target.id != current_user.id:
                status_map = {'audit': '审核通过' if data.get('approved') else '审核退回',
                              'accept_check': '验收通过' if data.get('approved') else '验收退回',
                              'close': '已关闭', 'assign': '有新工单派给你'}
                notify(target.id, 'ticket', f'工单 {t.number} {status_map.get(action, action)}',
                       t.title, f'/app/tickets/{t.id}')
    except Exception:
        current_app.logger.warning('工单通知发送失败 ticket_id=%s', ticket_id)
    return ok(None)


@vue_api_bp.route('/api/tickets/<int:ticket_id>/versions', methods=['GET'])
@login_required
@require_permission('ticket:view')
def api_ticket_versions(ticket_id):
    """工单提交版本历史（每次提交处理结果 + 每轮审核意见）"""
    from services.submission_version_service import list_versions
    return ok(list_versions('ticket', ticket_id))


@vue_api_bp.route('/api/tickets/report/latest/<int:ticket_id>', methods=['GET'])
@login_required
@require_permission('ticket:view')
def api_ticket_report_latest(ticket_id):
    """下载工单最新版处理报告（SSR 模板链接用）"""
    from models import SubmissionVersion as _SV
    v = _SV.query \
        .filter_by(entity_type='ticket', entity_id=ticket_id) \
        .filter(_SV.report_file != '') \
        .order_by(_SV.version_no.desc()).first()
    if not v:
        return fail('报告不存在', 404)
    return _send_report_file(v.report_file)


@vue_api_bp.route('/api/dicts/tickets', methods=['GET'])
@login_required
@require_permission('ticket:view')
def api_ticket_dicts():
    from models import Customer as _C, FaultType as _FT, Device as _D
    customers = [{'id': c.id, 'name': c.name, 'region_id': c.region_id}
                 for c in _C.query.order_by(_C.name).all()]
    fault_types = [{'id': f.id, 'name': f.name}
                   for f in _FT.query.order_by(_FT.sort_order, _FT.id).all()]
    statuses = ['待派单', '已派单', '已接单', '处理中', '待审核', '已验收', '已关闭']
    priorities = ['紧急', '高', '中', '低']
    devices = [{'id': d.id, 'device_name': d.device_name, 'customer_id': d.customer_id}
               for d in _D.query.order_by(_D.device_name).all()]
    return ok({'customers': customers, 'fault_types': fault_types,
               'statuses': statuses, 'priorities': priorities, 'devices': devices})
@vue_api_bp.route('/api/dicts/devices', methods=['GET'])
@login_required
@require_permission('device:view')
def api_device_dicts():
    from models import Device as _Device, Customer as _C, DeviceType as _DT
    brands = [r[0] for r in db.session.query(_Device.brand).distinct()
              .filter(_Device.brand != '').order_by(_Device.brand).all()]
    types = [{'name': t.name} for t in _DT.query.order_by(_DT.sort_order, _DT.id).all()]
    customers = [{'id': c.id, 'name': c.name}
                 for c in _C.query.order_by(_C.name).all()]
    return ok({'brands': brands, 'device_types': types, 'customers': customers})


# ==================== 客户管理 ====================
def _serialize_extra_fields(raw):
    """JSON 数组 [{name,value},...] → JSON 字符串（空则 ''），与 services 的 serialize_extra_fields 对齐"""
    import json as _json
    if not raw:
        return ''
    if isinstance(raw, str):
        return raw
    pairs = []
    for item in raw:
        if isinstance(item, dict) and str(item.get('name') or '').strip():
            pairs.append({'name': str(item.get('name')).strip(),
                          'value': str(item.get('value') or '').strip()})
    return _json.dumps(pairs, ensure_ascii=False) if pairs else ''


def _customer_payload(c, region_map=None, category_map=None):
    from services.customer_service import parse_extra_fields
    return {
        'id': c.id,
        'name': c.name,
        'contact_person': c.contact_person or '',
        'phone': c.phone or '',
        'email': c.email or '',
        'level': c.level or '常规',
        'city': c.city or '',
        'address': c.address or '',
        'office': c.office or '',
        'source': c.source or '',
        'remark': c.remark or '',
        'region_id': c.region_id,
        'category_id': c.category_id,
        'parent_id': c.parent_id,
        'has_onsite': bool(c.has_onsite),
        'has_onsite_label': '有' if c.has_onsite else '无',
        'onsite_contact': c.onsite_contact or '',
        'onsite_phone': c.onsite_phone or '',
        'onsite_office': c.onsite_office or '',
        'has_drill': bool(c.has_drill),
        'inspection_frequency': c.inspection_frequency or '',
        'device_count': c.device_count or 0,
        'category_name': (category_map or {}).get(c.category_id, ''),
        'region_name': (region_map or {}).get(c.region_id, ''),
        'created_at': c.created_at.strftime('%Y-%m-%d %H:%M') if c.created_at else '',
        'extra_fields': parse_extra_fields(c),
    }


@vue_api_bp.route('/api/v2/customers/export', methods=['POST'])
@login_required
@require_permission('customer:view')
def api_v2_customer_export():
    """客户导出（base64，列序与导入模板一致）"""
    import base64
    from datetime import date as _date
    from utils.excel_export import export_xlsx
    from models import Customer as _C
    headers = ['客户名称', '联系人', '电话', '邮箱', '所属地区', '地市', '地址',
               '单位类别', '客户等级', '办公室', '有无驻场', '驻场联系人', '驻场联系方式', '驻场办公室',
               '有无攻防演练', '巡检频率', '来源', '备注']
    rows = []
    for c in _C.query.order_by(_C.name).all():
        region_label = ''
        if c.region_rel:
            region_label = f'{c.region_rel.parent.name} - {c.region_rel.name}' if c.region_rel.parent else c.region_rel.name
        rows.append([
            c.name, c.contact_person or '', c.phone or '', c.email or '',
            region_label, c.city or '', c.address or '',
            (c.category_rel.name if c.category_rel else ''), c.level or '',
            c.office or '', '是' if c.has_onsite else '否',
            c.onsite_contact or '', c.onsite_phone or '', c.onsite_office or '',
            '是' if c.has_drill else '否', c.inspection_frequency or '',
            c.source or '', c.remark or '',
        ])
    tmp_path, download_name = export_xlsx(headers, rows, f'客户导出_{_date.today().isoformat()}.xlsx',
                                          sheet_name='客户信息')
    with open(tmp_path, 'rb') as fh:
        b64 = base64.b64encode(fh.read()).decode('ascii')
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    return ok({'filename': download_name, 'content': b64})


@vue_api_bp.route('/api/v2/customers/import', methods=['POST'])
@login_required
@require_permission('customer:add')
def api_v2_customer_import():
    """客户批量导入（multipart import_file；与 SSR 导入同字段映射）"""
    from utils.upload import validate_upload, save_temp_upload, open_excel, cleanup_temp_file
    from models import Customer as _C, Region as _R, CustomerCategory as _CC
    if 'import_file' not in request.files:
        return fail('请选择要导入的 Excel 文件', 400)
    f = request.files['import_file']
    ok_flag, err, _ = validate_upload(f, {'.xlsx', '.xls'}, max_size_mb=20)
    if not ok_flag:
        return fail(err, 400)
    tmp = save_temp_upload(f, suffix='.xlsx')
    success = 0
    unknown_categories = set()
    try:
        wb, ws, err2 = open_excel(tmp, app=current_app)
        if err2:
            return fail(err2[0], 400)
        col_map = {}
        header = [c.value for c in ws[1]]
        for i, h in enumerate(header):
            if h:
                col_map[str(h).strip()] = i

        def _cell(r, name):
            idx = col_map.get(name)
            if idx is None:
                return ''
            v = ws.cell(r, idx + 1).value
            return str(v).strip() if v is not None else ''

        TRUE_SET = {'是', '1', 'true', 'True', 'Y', 'y', '有'}
        for r in range(2, ws.max_row + 1):
            name = _cell(r, '客户名称')
            if not name:
                continue
            if _C.query.filter_by(name=name).first():
                continue
            region_id = None
            region_name = _cell(r, '所属地区')
            if region_name:
                region = _R.query.filter_by(name=region_name.split(' - ')[-1]).first()
                if region:
                    region_id = region.id
            category_id = None
            cat_name = _cell(r, '单位类别')
            if cat_name:
                cat = _CC.query.filter_by(name=cat_name).first()
                if cat:
                    category_id = cat.id
                else:
                    unknown_categories.add(cat_name)
            db.session.add(_C(
                name=name, contact_person=_cell(r, '联系人') or None,
                phone=_cell(r, '电话') or None, email=_cell(r, '邮箱') or None,
                region_id=region_id, category_id=category_id,
                city=_cell(r, '地市') or None, address=_cell(r, '地址') or None,
                office=_cell(r, '办公室') or '', level=_cell(r, '客户等级') or '常规',
                has_onsite=_cell(r, '有无驻场') in TRUE_SET,
                onsite_contact=_cell(r, '驻场联系人') or '',
                onsite_phone=_cell(r, '驻场联系方式') or '',
                onsite_office=_cell(r, '驻场办公室') or '',
                has_drill=_cell(r, '有无攻防演练') in TRUE_SET,
                inspection_frequency=_cell(r, '巡检频率') or '',
                source=_cell(r, '来源') or None, remark=_cell(r, '备注') or None,
            ))
            success += 1
        db.session.commit()
    finally:
        cleanup_temp_file(tmp)
    return ok({'created': success, 'unknown_categories': sorted(unknown_categories)})


@vue_api_bp.route('/api/customers', methods=['GET'])
@login_required
@require_permission('customer:view')
def api_customer_list():
    """客户分页列表（DataTable 数据源）"""
    from models import Customer as _C, Region as _R, CustomerCategory as _CC

    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    level = (request.args.get('level') or '').strip()
    category_id = request.args.get('category_id', type=int)
    region_id = request.args.get('region_id', type=int)

    q = _C.query
    if search:
        q = q.filter(_C.name.contains(search) |
                     _C.contact_person.contains(search) |
                     _C.phone.contains(search))
    if level:
        q = q.filter(_C.level == level)
    if category_id:
        q = q.filter(_C.category_id == category_id)
    if region_id:
        q = q.filter(_C.region_id == region_id)

    total = q.count()
    rows = q.order_by(_C.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    region_map = {r.id: r.name for r in _R.query.all()}
    category_map = {cc.id: cc.name for cc in _CC.query.all()}
    return ok({'items': [_customer_payload(c, region_map, category_map) for c in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/customers/<int:customer_id>', methods=['GET'])
@login_required
@require_permission('customer:view')
def api_customer_get(customer_id):
    from models import Customer as _C, Region as _R, CustomerCategory as _CC
    c = _C.query.get_or_404(customer_id)
    region_map = {r.id: r.name for r in _R.query.all()}
    category_map = {cc.id: cc.name for cc in _CC.query.all()}
    payload = _customer_payload(c, region_map, category_map)
    payload['inspection_count'] = _count_by('inspections', 'customer_id', c.id)
    payload['ticket_count'] = _count_by('tickets', 'customer_id', c.id)
    return ok(payload)


@vue_api_bp.route('/api/customers', methods=['POST'])
@login_required
@require_permission('customer:add')
def api_customer_create():
    from services.customer_service import create_customer
    data = request.get_json(silent=True) or {}
    # checkbox 归一化：JSON boolean → service 期望 'on'
    form = dict(data)
    form['has_onsite'] = 'on' if data.get('has_onsite') else ''
    form['has_drill'] = 'on' if data.get('has_drill') else ''
    form['extra_fields'] = _serialize_extra_fields(data.get('extra_fields'))
    try:
        c = create_customer(form, device_count=0)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '客户创建失败', 400)
    # 与 SSR 一致：按巡检频率自动生成本年度任务（失败不阻塞）
    if c.inspection_frequency:
        try:
            from utils.customer_task_generator import generate_for_customer
            generate_for_customer(c.id)
        except Exception:
            current_app.logger.exception('客户 %s 任务自动生成失败', c.id)
    return ok({'id': c.id, 'level': c.level})


@vue_api_bp.route('/api/customers/<int:customer_id>', methods=['PUT'])
@login_required
@require_permission('customer:edit')
def api_customer_update(customer_id):
    from services.customer_service import update_customer
    data = request.get_json(silent=True) or {}
    form = dict(data)
    form['has_onsite'] = 'on' if data.get('has_onsite') else ''
    form['has_drill'] = 'on' if data.get('has_drill') else ''
    form['extra_fields'] = _serialize_extra_fields(data.get('extra_fields'))
    try:
        c = update_customer(customer_id, form)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '客户更新失败', 400)
    # 与 SSR 一致：频率变更后幂等补打本年度任务
    if c.inspection_frequency:
        try:
            from utils.customer_task_generator import generate_for_customer
            generate_for_customer(c.id)
        except Exception:
            current_app.logger.exception('客户 %s 任务自动生成失败', c.id)
    return ok({'id': c.id, 'level': c.level})


@vue_api_bp.route('/api/customers/<int:customer_id>', methods=['DELETE'])
@login_required
@require_permission('customer:delete')
def api_customer_delete(customer_id):
    from models import Customer as _C
    from services.customer_service import delete_customer
    c = _C.query.get_or_404(customer_id)
    current_app.logger.info(
        '客户删除审计(Vue): 用户[%s] 删除客户[%s](id=%s), IP=%s',
        current_user.username, c.name, c.id, request.remote_addr)
    from blueprints.vue_api_sys import audit_log
    audit_log('customer:delete', 'customer', c.id, f'删除客户「{c.name}」')
    try:
        delete_customer(customer_id)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '客户删除失败', 400)
    return ok(None)


@vue_api_bp.route('/api/dicts/customers', methods=['GET'])
@login_required
@require_permission('customer:view')
def api_customer_dicts():
    from models import CustomerCategory as _CC, Region as _R
    categories = [{'id': cc.id, 'name': cc.name}
                  for cc in _CC.query.order_by(_CC.sort_order, _CC.id).all()]
    regions = [{'id': r.id, 'name': r.name, 'parent_id': r.parent_id}
               for r in _R.query.order_by(_R.sort_order, _R.id).all()]
    return ok({'customer_categories': categories, 'regions': regions,
               'levels': ['auto', '核心', '重点', '常规']})


# ==================== 巡检记录 ====================
def _inspection_payload(i, customer_map=None, full=False, task_map=None):
    """巡检序列化。注意 review_status 的 ''(草稿) 在 API 边界归一为 '草稿'（过滤时反向映射）"""
    from utils.json_fields import parse_json
    from services.inspection_service import inspection_completeness
    complete, missing = inspection_completeness(i)
    payload = {
        'id': i.id,
        'title': i.title,
        'customer_id': i.customer_id,
        'customer_name': (customer_map or {}).get(i.customer_id, ''),
        'task_id': i.task_id,
        'task_title': (task_map or {}).get(i.task_id)
                      or (i.task_rel.title if i.task_rel else '') or '',
        'inspection_date': i.inspection_date.strftime('%Y-%m-%d') if i.inspection_date else '',
        'overall_status': i.overall_status or '',
        'review_status': i.review_status or '草稿',
        'inspector_name': i.inspector_name or i.inspector or '',
        'inspector_user_id': i.inspector_user_id,
        'report_file': bool(i.report_file),
        'report_label': '有' if i.report_file else '无',
        'report_file_name': (i.report_file or '').split('/')[-1] or '',
        'submitted_report': bool(i.submitted_report),
        'submitted_report_name': (i.submitted_report or '').split('/')[-1] or '',
        'complete': complete,
        'missing_fields': missing,
        'location': i.location or '',
        'conclusion': i.conclusion or '',
    }
    if full:
        payload['content_json'] = parse_json(i.content_json, [], 'inspection.content_json')
        payload['field_values_json'] = parse_json(i.field_values_json, {}, 'inspection.field_values_json')
        payload['sections_json'] = parse_json(i.sections_json, {}, 'inspection.sections_json')
        payload['review_comment'] = i.review_comment or ''
        payload['reviewed_at'] = i.reviewed_at.strftime('%Y-%m-%d %H:%M') if i.reviewed_at else ''
        payload['created_at'] = i.created_at.strftime('%Y-%m-%d %H:%M') if i.created_at else ''
    return payload


@vue_api_bp.route('/api/inspections', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_inspection_list():
    from models import Inspection as _I, Customer as _C, InspectionTask as _IT
    from sqlalchemy.orm import joinedload as _jl
    from datetime import date as _date
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    status = (request.args.get('status') or '').strip()
    review_status = (request.args.get('review_status') or '').strip()
    customer_id = request.args.get('customer_id', type=int)
    task_id = request.args.get('task_id', type=int)
    date_from = request.args.get('date_from') or ''
    date_to = request.args.get('date_to') or ''
    incomplete_only = request.args.get('incomplete_only', type=int) == 1

    q = _I.query.options(_jl(_I.customer_rel))
    if search:
        q = q.filter(_I.title.contains(search))
    if status:
        q = q.filter(_I.overall_status == status)
    if review_status:
        q = q.filter(_I.review_status == ('' if review_status == '草稿' else review_status))
    if customer_id:
        q = q.filter(_I.customer_id == customer_id)
    if task_id:
        q = q.filter(_I.task_id == task_id)
    if date_from:
        try:
            q = q.filter(_I.inspection_date >= _date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(_I.inspection_date <= _date.fromisoformat(date_to))
        except ValueError:
            pass
    rows_all = q.order_by(_I.inspection_date.desc(), _I.id.desc()).all()
    if incomplete_only:
        from services.inspection_service import inspection_completeness
        rows_all = [i for i in rows_all if not inspection_completeness(i)[0]]
    total = len(rows_all)
    rows = rows_all[(page - 1) * page_size: page * page_size]
    customer_map = {c.id: c.name for c in _C.query.all()}
    task_ids = {i.task_id for i in rows if i.task_id}
    task_map = {t.id: t.title for t in _IT.query.filter(_IT.id.in_(task_ids)).all()} if task_ids else {}
    return ok({'items': [_inspection_payload(i, customer_map, task_map=task_map) for i in rows],
               'total': total, 'page': page, 'page_size': page_size})


@vue_api_bp.route('/api/inspections/<int:inspection_id>', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_inspection_get(inspection_id):
    from models import Inspection as _I
    i = _I.query.get_or_404(inspection_id)
    payload = _inspection_payload(i, {i.customer_id: i.customer_rel.name if i.customer_rel else ''}, full=True)
    return ok(payload)


@vue_api_bp.route('/api/inspections', methods=['POST'])
@login_required
@require_permission('inspection:add')
def api_inspection_create():
    from services.inspection_service import create_inspection
    data = request.get_json(silent=True) or {}
    try:
        i = create_inspection(data, current_user.realname or current_user.username)
        if data.get('conclusion'):
            i.conclusion = data['conclusion']
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '巡检创建失败', 400)
    return ok({'id': i.id})


@vue_api_bp.route('/api/inspections/<int:inspection_id>', methods=['PUT'])
@login_required
@require_permission('inspection:edit')
def api_inspection_update(inspection_id):
    from services.inspection_service import update_inspection
    data = request.get_json(silent=True) or {}
    try:
        i = update_inspection(inspection_id, data)
        if 'conclusion' in data:
            i.conclusion = data.get('conclusion') or ''
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '巡检更新失败', 400)
    return ok({'id': i.id})


@vue_api_bp.route('/api/inspections/<int:inspection_id>', methods=['DELETE'])
@login_required
@require_permission('inspection:delete')
def api_inspection_delete(inspection_id):
    from services.inspection_service import delete_inspection
    from models import Inspection as _I
    i = _I.query.get_or_404(inspection_id)
    current_app.logger.info(
        '巡检删除审计(Vue): 用户[%s] 删除巡检[%s](id=%s), IP=%s',
        current_user.username, i.title, i.id, request.remote_addr)
    try:
        delete_inspection(inspection_id)
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '巡检删除失败', 400)
    return ok(None)


@vue_api_bp.route('/api/inspections/<int:inspection_id>/submit', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def api_inspection_submit(inspection_id):
    """提交审核：review_status → 待审核。

    支持 multipart（report_file 现场报告上传，补齐"记录页新建→提交审核"闭环）：
    带文件时保存到 submission 版本并置 submitted_report 后再提交。
    """
    from services.inspection_service import submit_for_review
    from services.submission_version_service import add_version, latest_pending_version
    from utils.upload import validate_upload
    from models import Inspection as _I
    from utils.constants import REVIEW_PENDING as _RP

    ALLOWED_REPORT_EXT = {'.doc', '.docx', '.pdf', '.xlsx', '.xls',
                          '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.zip'}
    i = _I.query.get_or_404(inspection_id)
    report_path = ''
    if request.files.get('report_file'):
        if i.submitted_report or latest_pending_version('inspection', inspection_id):
            return fail('该记录已有报告或待审核版本，请勿重复上传', 400)
        ok_flag, err, safe_name = validate_upload(request.files['report_file'], ALLOWED_REPORT_EXT, max_size_mb=50)
        if not ok_flag:
            return fail(err, 400)
        subdir = 'inspection_reports'
        os.makedirs(os.path.join('static', 'uploads', subdir), exist_ok=True)
        report_path = os.path.join(subdir, safe_name)
        request.files['report_file'].save(os.path.join('static', 'uploads', report_path))
        i.submitted_report = report_path
        add_version('inspection', inspection_id, report_file=report_path,
                    content={'conclusion': i.conclusion or '', 'remark': ''},
                    submitted_by_user_id=current_user.id, review_status=_RP)
    try:
        submit_for_review(inspection_id, current_user.realname or current_user.username)
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '提交审核失败', 400)
    return ok(None)


# ==================== 巡检审核检查项清单（V23：系统级可配置） ====================
DEFAULT_REVIEW_CHECKLIST = [
    {'name': '核心设备配置备份', 'enabled': True},
    {'name': '拓扑图', 'enabled': True},
    {'name': '资产信息', 'enabled': True},
    {'name': '链路状态及信息', 'enabled': True},
    {'name': '路由信息', 'enabled': True},
    {'name': '现场图片', 'enabled': True},
    {'name': '设备除尘', 'enabled': True},
    {'name': '机房环境', 'enabled': True},
    {'name': '会议测试', 'enabled': True},
]
REVIEW_CHECKLIST_SETTING_KEY = 'inspection_review_checklist'


def _get_review_checklist():
    """读取巡检审核检查项清单（SystemSetting，无效/缺失回退默认 9 项）"""
    from utils.json_fields import parse_json
    from models import SystemSetting
    row = SystemSetting.query.filter_by(key=REVIEW_CHECKLIST_SETTING_KEY).first()
    items = parse_json(row.value if row else '', [], 'system_settings.review_checklist')
    if not isinstance(items, list) or not items:
        return [dict(x) for x in DEFAULT_REVIEW_CHECKLIST]
    return items


@vue_api_bp.route('/api/system/inspection-review-checklist', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_review_checklist_get():
    return ok({'items': _get_review_checklist()})


@vue_api_bp.route('/api/system/inspection-review-checklist', methods=['PUT'])
@login_required
@require_permission('permission:edit')
def api_review_checklist_put():
    """管理员保存检查项清单（[{name, enabled}]，name 非空）"""
    import json
    from models import SystemSetting
    data = request.get_json(silent=True) or {}
    items = data.get('items') or []
    cleaned = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = (it.get('name') or '').strip()
        if name:
            cleaned.append({'name': name, 'enabled': bool(it.get('enabled', True))})
    if not cleaned:
        return fail('检查项不能为空', 400)
    row = SystemSetting.query.filter_by(key=REVIEW_CHECKLIST_SETTING_KEY).first()
    if not row:
        row = SystemSetting(key=REVIEW_CHECKLIST_SETTING_KEY, value='')
        db.session.add(row)
    row.value = json.dumps(cleaned, ensure_ascii=False)
    db.session.commit()
    return ok({'items': cleaned})


@vue_api_bp.route('/api/inspections/<int:inspection_id>/ai-analyze', methods=['POST'])
@login_required
@require_permission('inspection:review')
def api_inspection_ai_analyze(inspection_id):
    """AI 辅助审核：基于巡检记录内容生成分析建议（需在 AI 对接中启用配置）"""
    from utils.json_fields import parse_json
    from models import AIConfig, Inspection as _I
    cfg = AIConfig.query.filter_by(is_enabled=True).order_by(AIConfig.id).first()
    if not cfg:
        return fail('未配置可用的 AI 服务（系统设置 → AI 对接），无法使用 AI 辅助分析', 400)
    i = _I.query.get_or_404(inspection_id)
    parts = [f'巡检标题：{i.title}']
    if i.conclusion:
        parts.append(f'结论：{i.conclusion}')
    parts.append(f'总体状态：{i.overall_status or "-"}')
    parts.append(f'审核状态：{i.review_status or "-"}')
    if i.location:
        parts.append(f'地点：{i.location}')
    content = parse_json(i.content_json, [], 'inspection.content_json')
    if content:
        import json as _json
        parts.append('检查内容：' + _json.dumps(content, ensure_ascii=False)[:1500])
    from services.submission_version_service import latest_pending_version
    v = latest_pending_version('inspection', inspection_id)
    if v and v.content:
        import json as _json
        parts.append('最新提交内容：' + _json.dumps(v.content, ensure_ascii=False)[:1500])
    prompt = ('你是 IT 运维巡检审核助手。请基于以下巡检记录给出审核建议：'
              '1) 资料是否完整、结论与内容是否一致；2) 需要重点核实的事项；'
              '3) 建议通过或退回及理由。\n\n' + '\n'.join(parts))
    from utils.ai_client import AIClient
    try:
        text = AIClient(cfg).chat(prompt)
    except Exception as e:
        current_app.logger.warning('AI 巡检分析失败 inspection_id=%s: %s', inspection_id, e)
        return fail(f'AI 调用失败：{e}', 500)
    return ok({'analysis': text})


@vue_api_bp.route('/api/inspections/<int:inspection_id>/review', methods=['POST'])
@login_required
@require_permission('inspection:review')
def api_inspection_review(inspection_id):
    """审核巡检：approved=True 通过（自动生成 Word 报告）/ False 退回修改。
    remark=退回原因/审核意见，requirements=需要修改的内容（空时由需修改检查项自动拼装），
    checklist=检查项勾选 {"项名": "合格|需修改|不适用"}。"""
    from services.inspection_service import review_inspection
    from models import Inspection as _IC
    from services.submission_version_service import latest_pending_version
    data = request.get_json(silent=True) or {}
    approved = bool(data.get('approved'))
    remark = data.get('remark') or ''
    requirements = data.get('requirements') or ''
    checklist = data.get('checklist')
    try:
        review_inspection(inspection_id, approved, current_user.realname or current_user.username,
                          remark, requirements, checklist)
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '审核失败', 400)
    # ---- 事件源：审核结果通知提交工程师 ----
    try:
        from utils.notifications import notify
        i = _IC.query.get(inspection_id)
        target_uid = None
        if i:
            v = latest_pending_version('inspection', inspection_id)
            target_uid = (v.submitted_by if v else None) or i.inspector_user_id
        if target_uid and target_uid != current_user.id:
            notify(target_uid, 'inspection',
                   f'巡检「{i.title if i else ""}」审核{"通过" if approved else "退回"}',
                   (remark or requirements) or ('已生成正式报告' if approved else '请按修改要求重新提交'),
                   f'/app/inspections/{inspection_id}')
    except Exception:
        current_app.logger.warning('巡检审核通知失败 inspection_id=%s', inspection_id)
    return ok(None)


@vue_api_bp.route('/api/inspections/assets/<int:asset_id>/download', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_submission_asset_download(asset_id):
    """下载提交资料文件（配置包/拓扑图/资产清单等，防路径穿越）"""
    from models import SubmissionAsset as _SA
    a = _SA.query.get_or_404(asset_id)
    if not a.file_path:
        return fail('该资料无附件文件', 404)
    return _send_report_file(a.file_path)


@vue_api_bp.route('/api/inspections/assets/<int:asset_id>/content', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_submission_asset_content(asset_id):
    """提交资料文本内容在线查看（核心设备文本配置）"""
    from models import SubmissionAsset as _SA
    a = _SA.query.get_or_404(asset_id)
    return ok({'id': a.id, 'content': a.content_text or ''})


@vue_api_bp.route('/api/task-schedule/<int:task_id>/required-assets', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_task_required_assets(task_id):
    """任务提交资料必传配置（按任务模板）+ 任务客户设备列表（提交弹窗数据源）"""
    from services.inspection_service import get_task_required_assets
    from models import InspectionTask as _IT, Device as _D
    t = _IT.query.get_or_404(task_id)
    devices = [{'id': d.id, 'device_name': d.device_name, 'device_type': d.device_type or ''}
               for d in _D.query.filter_by(customer_id=t.customer_id, is_in_use=True)
               .order_by(_D.device_name).all()]
    return ok({'required_assets': get_task_required_assets(t), 'devices': devices})


@vue_api_bp.route('/api/inspections/task/<int:task_id>/report', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def api_inspection_upload_report(task_id):
    """工程师从任务上传全套资料 → 自动创建/复用巡检记录 + 建版本 + 任务「执行中→待审核」。

    multipart 字段：
      report_file(必传，可豁免：report_skip_reason) + conclusion + remark
      config_zip(完整配置包) + config_zip_device_id + config_zip_skip_reason
      config_text_file_N / config_text_content_N / config_text_device_id_N（核心设备文本配置，可粘贴或传文件）
      config_text_skip_reason
      topology_file（拓扑图）+ topology_skip_reason
      asset_list（资产清单 Excel，提交时解析导入设备）+ asset_list_skip_reason
    """
    from services.inspection_service import upload_report_for_task
    from utils.upload import validate_upload
    from models import InspectionTask as _IT

    ALLOWED_REPORT_EXT = {'.doc', '.docx', '.pdf', '.xlsx', '.xls',
                          '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.zip'}
    ALLOWED_ZIP_EXT = {'.zip'}
    ALLOWED_TEXT_EXT = {'.txt', '.cfg', '.conf', '.log', '.text'}
    ALLOWED_TOPOLOGY_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp',
                            '.pdf', '.vsd', '.vsdx', '.drawio', '.xml'}
    ALLOWED_ASSET_EXT = {'.xlsx', '.xls'}

    def _save_file(f, subdir, allowed, max_mb=50):
        ok_flag, err, safe_name = validate_upload(f, allowed, max_size_mb=max_mb)
        if not ok_flag:
            return None, err
        os.makedirs(os.path.join('static', 'uploads', subdir), exist_ok=True)
        rel = '/'.join(('uploads', subdir, safe_name))
        f.save(os.path.join('static', rel))
        return rel, None

    task = _IT.query.get_or_404(task_id)

    report_path = ''
    report_skip_reason = (request.form.get('report_skip_reason') or '').strip()
    f = request.files.get('report_file')
    if f:
        report_path, err = _save_file(f, f'inspection_reports/{task.id}', ALLOWED_REPORT_EXT)
        if err:
            return fail(err or '报告文件校验失败')

    # 完整配置备份包
    config_zip_path = ''
    config_zip_device_id = request.form.get('config_zip_device_id') or None
    config_zip_skip_reason = (request.form.get('config_zip_skip_reason') or '').strip()
    f = request.files.get('config_zip')
    if f:
        config_zip_path, err = _save_file(f, f'inspection_configs/{task.id}', ALLOWED_ZIP_EXT, max_mb=100)
        if err:
            return fail(err or '配置包文件校验失败')

    # 核心设备文本配置（动态行：文件 N 或粘贴 N + 设备 N）
    config_texts = []
    handled_idx = set()
    for key, fobj in request.files.items():
        if not key.startswith('config_text_file_'):
            continue
        n = key.rsplit('_', 1)[-1]
        if not n.isdigit():
            continue
        handled_idx.add(n)
        tpath, err = _save_file(fobj, f'inspection_configs/{task.id}', ALLOWED_TEXT_EXT)
        if err:
            return fail(err or '文本配置文件校验失败')
        dev_id = request.form.get(f'config_text_device_id_{n}') or None
        content = ''
        try:
            with open(os.path.join('static', tpath), 'r', encoding='utf-8', errors='replace') as fh:
                content = fh.read()
        except Exception:
            pass
        config_texts.append({'device_id': dev_id, 'content': content,
                             'file_path': tpath, 'file_name': fobj.filename or ''})
    for n, value in request.form.items():
        if not n.startswith('config_text_content_'):
            continue
        idx = n.rsplit('_', 1)[-1]
        if not idx.isdigit() or idx in handled_idx:
            continue
        content = (value or '').strip()
        if not content:
            continue
        dev_id = request.form.get(f'config_text_device_id_{idx}') or None
        config_texts.append({'device_id': dev_id, 'content': content, 'file_path': '', 'file_name': ''})
    config_text_skip_reason = (request.form.get('config_text_skip_reason') or '').strip()

    # 拓扑图
    topology_file_path = ''
    topology_file_name = ''
    topology_skip_reason = (request.form.get('topology_skip_reason') or '').strip()
    f = request.files.get('topology_file')
    if f:
        topology_file_path, err = _save_file(f, f'inspection_topologies/{task.id}', ALLOWED_TOPOLOGY_EXT)
        if err:
            return fail(err or '拓扑图文件校验失败')
        topology_file_name = f.filename or ''

    # 资产清单（保存 + 解析导入设备）
    asset_list_path = ''
    asset_list_file_name = ''
    asset_list_skip_reason = (request.form.get('asset_list_skip_reason') or '').strip()
    asset_import_result = None
    f = request.files.get('asset_list')
    if f:
        asset_list_path, err = _save_file(f, f'inspection_assets/{task.id}', ALLOWED_ASSET_EXT)
        if err:
            return fail(err or '资产清单文件校验失败')
        asset_list_file_name = f.filename or ''
        try:
            from services.asset_list_service import import_asset_list
            asset_import_result = import_asset_list(
                asset_list_path, task.customer_id,
                current_user.realname or current_user.username, asset_list_file_name)
        except Exception as e:
            db.session.rollback()
            return fail(str(e) or '资产清单解析失败', 400)

    conclusion = (request.form.get('conclusion') or '').strip()
    remark = (request.form.get('remark') or '').strip()
    me = current_user
    try:
        inspection, version, asset_result = upload_report_for_task(
            task.id, report_path, conclusion,
            current_user_id=me.id,
            current_user_name=me.realname or me.username,
            force=(me.role == 'admin'),
            remark=remark,
            report_skip_reason=report_skip_reason,
            config_zip_path=config_zip_path, config_zip_device_id=config_zip_device_id,
            config_zip_skip_reason=config_zip_skip_reason,
            config_texts=config_texts, config_text_skip_reason=config_text_skip_reason,
            topology_file_path=topology_file_path, topology_file_name=topology_file_name,
            topology_skip_reason=topology_skip_reason,
            asset_list_path=asset_list_path, asset_list_file_name=asset_list_file_name,
            asset_list_skip_reason=asset_list_skip_reason,
        )
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '上传失败', 400)

    if asset_result['config_backups'] or asset_result['topologies']:
        try:
            from blueprints.vue_api_sys import audit_log
            audit_log('巡检提交资料同步', 'task', task.id,
                      '配置备份 %d 条、拓扑 %d 条、资产导入 %s' % (
                          asset_result['config_backups'], asset_result['topologies'],
                          (asset_import_result or {}).get('created', 0)))
        except Exception:
            current_app.logger.warning('巡检资料同步审计失败 task_id=%s', task_id)

    return ok({'inspection_id': inspection.id, 'version_no': version.version_no,
               'task_status': task.status,
               'config_backups': asset_result['config_backups'],
               'topologies': asset_result['topologies'],
               'skipped': asset_result['skipped'],
               'asset_import': asset_import_result})


@vue_api_bp.route('/api/inspections/<int:inspection_id>/versions', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_inspection_versions(inspection_id):
    """巡检记录提交版本历史（每次上传报告 + 每轮审核意见）"""
    from services.submission_version_service import list_versions
    return ok(list_versions('inspection', inspection_id))


@vue_api_bp.route('/api/inspections/report/latest/<int:inspection_id>', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_inspection_report_latest(inspection_id):
    """下载巡检记录最新版现场报告（SSR 模板链接用）"""
    from models import SubmissionVersion as _SV
    v = _SV.query \
        .filter_by(entity_type='inspection', entity_id=inspection_id) \
        .filter(_SV.report_file != '') \
        .order_by(_SV.version_no.desc()).first()
    if not v:
        return fail('报告不存在', 404)
    return _send_report_file(v.report_file)


@vue_api_bp.route('/api/inspections/report/<int:version_id>', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_inspection_report_download(version_id):
    """下载某版上传的现场报告（防路径穿越）"""
    from models import SubmissionVersion as _SV
    v = _SV.query.get_or_404(version_id)
    if v.entity_type != 'inspection' or not v.report_file:
        return fail('报告不存在', 404)
    return _send_report_file(v.report_file)


@vue_api_bp.route('/api/tickets/report/<int:version_id>', methods=['GET'])
@login_required
@require_permission('ticket:view')
def api_ticket_report_download(version_id):
    """下载某版上传的工单处理报告（防路径穿越）"""
    from models import SubmissionVersion as _SV
    v = _SV.query.get_or_404(version_id)
    if v.entity_type != 'ticket' or not v.report_file:
        return fail('报告不存在', 404)
    return _send_report_file(v.report_file)


def _send_report_file(rel_path):
    """安全下载 static/uploads/ 下的报告文件：realpath 校验防路径穿越"""
    full = os.path.realpath(os.path.join('static', rel_path))
    base = os.path.realpath(os.path.join('static', 'uploads'))
    if not full.startswith(base + os.sep) or not os.path.isfile(full):
        return fail('文件不存在', 404)
    return send_from_directory(os.path.dirname(full), os.path.basename(full), as_attachment=True)


@vue_api_bp.route('/api/dicts/inspections', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_inspection_dicts():
    from models import Customer as _C, Inspector as _I, InspectionTask as _IT
    customers = [{'id': c.id, 'name': c.name, 'region_id': c.region_id}
                 for c in _C.query.order_by(_C.name).all()]
    inspectors = [{'user_id': ins.user_id, 'name': ins.name}
                  for ins in _I.query.filter_by(is_active=True).order_by(_I.id).all()]
    tasks = []
    for t in _IT.query.order_by(_IT.id.desc()).limit(500).all():
        tasks.append({
            'id': t.id, 'title': t.title, 'status': t.status,
            'customer_id': t.customer_id,
            'customer_name': t.customer_rel.name if t.customer_rel else '',
            'assignee_id': t.assigned_to_user_id,
            'has_record': bool(t.records),
        })
    overall_statuses = ['正常', '警告', '异常']  # 显式展示顺序（常量 OVERALL_STATUSES 校验）
    review_statuses = ['草稿', '待审核', '已通过', '已退回']
    return ok({'customers': customers, 'inspectors': inspectors, 'tasks': tasks,
               'overall_statuses': overall_statuses, 'review_statuses': review_statuses})

# ==================== 地区管理 ====================
def _region_payload(r):
    return {'id': r.id, 'name': r.name, 'parent_id': r.parent_id, 'sort_order': r.sort_order or 0}


@vue_api_bp.route('/api/regions', methods=['GET'])
@login_required
@require_permission('region:view')
def api_region_list():
    from sqlalchemy.orm import joinedload
    from models import Region
    cities = Region.query.options(joinedload(Region.children)) \
        .filter_by(parent_id=None).order_by(Region.sort_order, Region.id).all()
    out = []
    for c in cities:
        kids = sorted(c.children, key=lambda d: (d.sort_order or 0, d.id))
        out.append({**_region_payload(c), 'children': [_region_payload(k) for k in kids]})
    return ok(out)


@vue_api_bp.route('/api/regions', methods=['POST'])
@login_required
@require_permission('region:add')
def api_region_add():
    from models import Region
    from sqlalchemy import func
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('地区名称不能为空')
    parent_id = data.get('parent_id') or None
    if Region.query.filter_by(name=name, parent_id=parent_id).first():
        return fail(f'同级已存在同名地区 "{name}"')
    max_so = db.session.query(func.max(Region.sort_order)).filter_by(parent_id=parent_id).scalar() or 0
    r = Region(name=name, parent_id=parent_id, sort_order=max_so + 1)
    db.session.add(r)
    db.session.commit()
    return ok({'id': r.id})


@vue_api_bp.route('/api/regions/<int:rid>', methods=['PUT'])
@login_required
@require_permission('region:edit')
def api_region_update(rid):
    from models import Region
    r = Region.query.get_or_404(rid)
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('地区名称不能为空')
    parent_id = data.get('parent_id') or None
    if parent_id == rid:
        return fail('不能将地区挂到自身')
    r.name = name
    r.parent_id = parent_id
    r.sort_order = int(data.get('sort_order') or 0)
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/regions/<int:rid>', methods=['DELETE'])
@login_required
@require_permission('region:delete')
def api_region_delete(rid):
    from models import Region
    r = Region.query.get_or_404(rid)
    if Region.query.filter_by(parent_id=rid).count() > 0:
        return fail('该地区下还有子地区，请先删除子地区')
    db.session.delete(r)
    db.session.commit()
    return ok(None)


# ==================== 单位类别 ====================
@vue_api_bp.route('/api/customer-categories', methods=['GET'])
@login_required
@require_permission('category:view')
def api_category_list():
    from models import CustomerCategory
    cats = CustomerCategory.query.order_by(CustomerCategory.sort_order, CustomerCategory.id).all()
    return ok([{'id': c.id, 'name': c.name, 'sort_order': c.sort_order or 0} for c in cats])


@vue_api_bp.route('/api/customer-categories', methods=['POST'])
@login_required
@require_permission('category:edit')
def api_category_add():
    from models import CustomerCategory
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('类别名称不能为空')
    if CustomerCategory.query.filter_by(name=name).first():
        return fail('类别名称已存在')
    cat = CustomerCategory(name=name, sort_order=int(data.get('sort_order') or 0))
    db.session.add(cat)
    db.session.commit()
    return ok({'id': cat.id})


@vue_api_bp.route('/api/customer-categories/<int:cid>', methods=['PUT'])
@login_required
@require_permission('category:edit')
def api_category_update(cid):
    from models import CustomerCategory
    cat = CustomerCategory.query.get_or_404(cid)
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if name:
        cat.name = name
    cat.sort_order = int(data.get('sort_order', cat.sort_order or 0))
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/customer-categories/<int:cid>', methods=['DELETE'])
@login_required
@require_permission('category:edit')
def api_category_delete(cid):
    from models import CustomerCategory, Customer
    cat = CustomerCategory.query.get_or_404(cid)
    count = Customer.query.filter_by(category_id=cid).count()
    if count > 0:
        return fail(f'类别「{cat.name}」下有 {count} 个客户，无法删除')
    db.session.delete(cat)
    db.session.commit()
    return ok(None)

