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
}


def _map_icon(bi):
    if not bi:
        return 'Document'
    return _ICON_MAP.get(bi, 'Document')


# ==================== 认证 ====================
@vue_api_bp.route('/api/auth/login', methods=['POST'])
@limiter.limit('5 per minute;30 per hour', methods=['POST'])
@csrf.exempt  # 登录页对未登录用户开放（与 SSR 登录一致）
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


def _user_payload(user):
    """当前用户信息 + 权限码数组（admin 短路全量权限）"""
    return {
        'id': user.id,
        'username': user.username,
        'realname': user.realname or user.username,
        'role': user.role or 'viewer',
        'department_id': user.department_id,
        'permissions': get_user_permissions(user),
    }


# ==================== 侧栏（Vue 版数据结构） ====================
@vue_api_bp.route('/api/auth/sidebar-groups', methods=['GET'])
@login_required
def api_sidebar_groups():
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
                'url': sl.get('url', '/'),
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
                    'url': c['url'],
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
    from models import (Ticket, InspectionTask, Inspector, Fault,
                        Opportunity, Contract, Customer, Device, Inspection)
    customer_map = {c.id: c.name for c in Customer.query.all()}
    my_tasks = []

    if role in ('admin', 'operator'):
        my_tickets = Ticket.query.filter(
            Ticket.assigned_to.in_([me_realname, me.username]),
            ~Ticket.status.in_(['已验收', '已关闭'])
        ).order_by(Ticket.created_at.desc()).limit(8).all()
        for t in my_tickets:
            my_tasks.append({
                'type_label': '工单', 'type_color': 'danger',
                'title': t.title,
                'sub': f"{customer_map.get(t.customer_id, '-')} · {t.priority} · {t.status}",
                'url': f'/tickets/{t.id}',
                'time': t.created_at.strftime('%m-%d %H:%M') if t.created_at else '',
            })
        insp = Inspector.query.filter_by(user_id=me.id).first()
        if insp:
            my_iid = str(insp.id)
            from sqlalchemy import literal
            haystack = literal(',') + func.coalesce(InspectionTask.inspector_ids, '') + literal(',')
            my_insp = InspectionTask.query.filter(
                haystack.like(f'%,{my_iid},%'),
                InspectionTask.status.in_(['待执行', '执行中'])
            ).order_by(InspectionTask.id.desc()).limit(5).all()
            for t in my_insp:
                my_tasks.append({
                    'type_label': '巡检', 'type_color': 'primary',
                    'title': t.title,
                    'sub': f"{customer_map.get(t.customer_id, '-')} · {t.status} · {t.task_type}",
                    'url': f'/task-schedule/{t.id}',
                    'time': (t.planned_start.strftime('%m-%d') if t.planned_start else '') + '~' +
                            (t.planned_end.strftime('%m-%d') if t.planned_end else ''),
                })
        my_faults = Fault.query.filter(Fault.result != '已解决').order_by(Fault.fault_time.desc()).limit(5).all()
        for f in my_faults:
            my_tasks.append({
                'type_label': '故障', 'type_color': 'warning',
                'title': f.title,
                'sub': f"{customer_map.get(f.customer_id, '-')} · {f.fault_type or '-'}",
                'url': f'/faults/{f.id}',
                'time': f.fault_time.strftime('%m-%d %H:%M') if f.fault_time else '',
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
                'url': '/opportunities',
                'time': o.expected_close_date.strftime('%Y-%m-%d') if o.expected_close_date else '-',
            })
        my_contracts = Contract.query.filter(Contract.status == '执行中') \
            .order_by(Contract.end_date.asc().nullslast()).limit(5).all()
        for c in my_contracts:
            my_tasks.append({
                'type_label': '合同', 'type_color': 'success',
                'title': c.title,
                'sub': f"{customer_map.get(c.customer_id, '-')} · {c.amount or 0}",
                'url': '/contracts',
                'time': c.end_date.strftime('%Y-%m-%d') if c.end_date else '-',
            })
    my_tasks = my_tasks[:8]

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
    def card(label, value, sub, icon, accent):
        return {'label': label, 'value': value, 'sub': sub, 'icon': _map_icon(icon), 'accent': accent}

    metrics = [card('客户总数', counts['customer'], f"{counts['region']} 个地区", 'bi-people', '#2563eb'),
               card('设备总数', counts['device'], '全部设备', 'bi-hdd-rack', '#059669'),
               card('巡检记录', counts['inspection'], '全部巡检', 'bi-clipboard-check', '#7c3aed'),
               card('工单总数', counts['ticket'], '含历史故障', 'bi-ticket-detailed', '#f59e0b'),
               card('知识条目', counts['kb'], '故障案例与手册', 'bi-book', '#0891b2'),
               card('备件档案', counts['spare'], '备件管理', 'bi-archive', '#16a34a'),
               card('商机跟进', counts['opp'], '销售管线', 'bi-lightbulb', '#475569'),
               card('合同总数', counts['contract'], '执行跟踪', 'bi-file-earmark-lock', '#ea580c')]

    # ---- 快捷入口 ----
    if role == 'admin':
        quick_entries = [
            {'url': '/customers', 'title': '客户管理', 'sub': '客户信息维护', 'icon': 'bi-people'},
            {'url': '/devices', 'title': '设备管理', 'sub': '设备档案与密码', 'icon': 'bi-hdd-rack'},
            {'url': '/tickets', 'title': '工单管理', 'sub': '派单/接单/处理', 'icon': 'bi-ticket-detailed'},
            {'url': '/knowledge-base', 'title': '知识库', 'sub': '故障案例与手册', 'icon': 'bi-book'},
            {'url': '/users', 'title': '用户管理', 'sub': '账号与角色', 'icon': 'bi-people-fill'},
        ]
    elif role == 'operator':
        quick_entries = [
            {'url': '/devices', 'title': '设备管理', 'sub': '设备档案', 'icon': 'bi-hdd-rack'},
            {'url': '/tickets', 'title': '工单处理', 'sub': '我的工单', 'icon': 'bi-ticket-detailed'},
            {'url': '/task-schedule/', 'title': '任务安排', 'sub': '执行计划巡检', 'icon': 'bi-calendar3-week'},
            {'url': '/inspections', 'title': '巡检记录', 'sub': '提交巡检报告', 'icon': 'bi-clipboard-check'},
            {'url': '/knowledge-base', 'title': '知识库', 'sub': '快速查询', 'icon': 'bi-book'},
        ]
    elif role == 'sales':
        quick_entries = [
            {'url': '/customers', 'title': '客户管理', 'sub': '客户信息', 'icon': 'bi-people'},
            {'url': '/opportunities', 'title': '商机跟进', 'sub': '阶段推进', 'icon': 'bi-lightbulb'},
            {'url': '/quotations', 'title': '报价单', 'sub': '生成报价', 'icon': 'bi-file-earmark-text'},
            {'url': '/contracts', 'title': '合同管理', 'sub': '合同执行', 'icon': 'bi-file-earmark-lock'},
            {'url': '/projects', 'title': '项目管理', 'sub': '项目进度', 'icon': 'bi-graph-up'},
        ]
    else:
        quick_entries = [
            {'url': '/customers', 'title': '客户管理', 'sub': '查看客户', 'icon': 'bi-people'},
            {'url': '/devices', 'title': '设备管理', 'sub': '查看设备', 'icon': 'bi-hdd-rack'},
            {'url': '/tickets', 'title': '工单管理', 'sub': '查看工单', 'icon': 'bi-ticket-detailed'},
            {'url': '/knowledge-base', 'title': '知识库', 'sub': '查看知识', 'icon': 'bi-book'},
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
    from models import Device as _Device
    d = _Device.query.get_or_404(device_id)
    pwd = decrypt_password(d.password_encrypted) if d.password_encrypted else ''
    current_app.logger.info(
        '密码查看审计(Vue): 用户[%s] 查看设备[%s](id=%s), IP=%s',
        current_user.username, d.device_name, d.id, request.remote_addr)
    return ok({'password': pwd})


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


# ==================== 工单管理 ====================
def _ticket_payload(t, customer_map=None):
    return {
        'id': t.id,
        'number': t.number,
        'title': t.title,
        'status': t.status,
        'priority': t.priority,
        'customer_id': t.customer_id,
        'customer_name': (customer_map or {}).get(t.customer_id, ''),
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
        'accept_status': t.accept_status or '',
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
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    status = (request.args.get('status') or '').strip()
    priority = (request.args.get('priority') or '').strip()
    customer_id = request.args.get('customer_id', type=int)
    scope = (request.args.get('scope') or 'all').strip()

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
    total = q.count()
    rows = q.order_by(_T.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
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
    TicketLog.query.filter_by(ticket_id=ticket_id).delete()
    _T.query.filter_by(id=ticket_id).delete()
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/tickets/<int:ticket_id>/action', methods=['POST'])
@login_required
@require_permission('ticket:edit')
def api_ticket_action(ticket_id):
    """工单状态机动作：assign/accept/submit/audit/accept_check/close"""
    from services.ticket_service import (assign_ticket, accept_ticket, submit_ticket,
                                         audit_ticket, accept_check_ticket, close_ticket)
    data = request.get_json(silent=True) or {}
    action = data.get('action', '')
    me = current_user.realname or current_user.username
    remark = data.get('remark', '')
    try:
        if action == 'assign':
            if not data.get('assignee'):
                return fail('请填写指派处理人', 400)
            assign_ticket(ticket_id, data['assignee'], me, remark or f'派给 {data["assignee"]}')
        elif action == 'accept':
            accept_ticket(ticket_id, me, remark or '已接单，开始处理')
        elif action == 'submit':
            submit_ticket(ticket_id, me, remark or '提交审核',
                          diagnosis=data.get('diagnosis'), solution=data.get('solution'))
        elif action == 'audit':
            approved = bool(data.get('approved'))
            audit_ticket(ticket_id, approved, me, remark or ('审核通过' if approved else '审核不通过'))
        elif action == 'accept_check':
            approved = bool(data.get('approved'))
            accept_check_ticket(ticket_id, me, remark or ('客户验收通过' if approved else '客户验收退回'),
                                approved=approved)
        elif action == 'close':
            close_ticket(ticket_id, me, remark or '关闭工单')
        else:
            return fail(f'未知动作: {action}', 400)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '操作失败', 400)
    return ok(None)


@vue_api_bp.route('/api/dicts/tickets', methods=['GET'])
@login_required
@require_permission('ticket:view')
def api_ticket_dicts():
    from models import Customer as _C, FaultType as _FT
    customers = [{'id': c.id, 'name': c.name} for c in _C.query.order_by(_C.name).all()]
    fault_types = [{'id': f.id, 'name': f.name}
                   for f in _FT.query.order_by(_FT.sort_order, _FT.id).all()]
    statuses = ['待派单', '已派单', '已接单', '处理中', '待审核', '已验收', '已关闭']
    priorities = ['紧急', '高', '中', '低']
    return ok({'customers': customers, 'fault_types': fault_types,
               'statuses': statuses, 'priorities': priorities})
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
               'levels': ['核心', '重点', '常规']})


# ==================== 巡检记录 ====================
def _inspection_payload(i, customer_map=None, full=False):
    """巡检序列化。注意 review_status 的 ''(草稿) 在 API 边界归一为 '草稿'（过滤时反向映射）"""
    from utils.json_fields import parse_json
    payload = {
        'id': i.id,
        'title': i.title,
        'customer_id': i.customer_id,
        'customer_name': (customer_map or {}).get(i.customer_id, ''),
        'inspection_date': i.inspection_date.strftime('%Y-%m-%d') if i.inspection_date else '',
        'overall_status': i.overall_status or '',
        'review_status': i.review_status or '草稿',
        'inspector_name': i.inspector_name or i.inspector or '',
        'report_file': bool(i.report_file),
        'report_label': '有' if i.report_file else '无',
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
    from models import Inspection as _I, Customer as _C
    from sqlalchemy.orm import joinedload as _jl
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    status = (request.args.get('status') or '').strip()
    review_status = (request.args.get('review_status') or '').strip()
    customer_id = request.args.get('customer_id', type=int)

    q = _I.query.options(_jl(_I.customer_rel))
    if search:
        q = q.filter(_I.title.contains(search))
    if status:
        q = q.filter(_I.overall_status == status)
    if review_status:
        q = q.filter(_I.review_status == ('' if review_status == '草稿' else review_status))
    if customer_id:
        q = q.filter(_I.customer_id == customer_id)
    total = q.count()
    rows = q.order_by(_I.inspection_date.desc(), _I.id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()
    customer_map = {c.id: c.name for c in _C.query.all()}
    return ok({'items': [_inspection_payload(i, customer_map) for i in rows],
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
    """提交审核：review_status → 待审核"""
    from services.inspection_service import submit_for_review
    try:
        submit_for_review(inspection_id, current_user.realname or current_user.username)
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '提交审核失败', 400)
    return ok(None)


@vue_api_bp.route('/api/inspections/<int:inspection_id>/review', methods=['POST'])
@login_required
@require_permission('inspection:review')
def api_inspection_review(inspection_id):
    """审核巡检：approved=True 通过（自动生成 Word 报告）/ False 退回"""
    from services.inspection_service import review_inspection
    data = request.get_json(silent=True) or {}
    approved = bool(data.get('approved'))
    remark = data.get('remark') or ''
    try:
        review_inspection(inspection_id, approved, current_user.realname or current_user.username, remark)
    except Exception as e:
        db.session.rollback()
        return fail(str(e) or '审核失败', 400)
    return ok(None)


@vue_api_bp.route('/api/dicts/inspections', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_inspection_dicts():
    from models import Customer as _C, Inspector as _I
    customers = [{'id': c.id, 'name': c.name} for c in _C.query.order_by(_C.name).all()]
    inspectors = [{'user_id': ins.user_id, 'name': ins.name}
                  for ins in _I.query.filter_by(is_active=True).order_by(_I.id).all()]
    overall_statuses = ['正常', '警告', '异常']
    review_statuses = ['草稿', '待审核', '已通过', '已退回']
    return ok({'customers': customers, 'inspectors': inspectors,
               'overall_statuses': overall_statuses, 'review_statuses': review_statuses})
