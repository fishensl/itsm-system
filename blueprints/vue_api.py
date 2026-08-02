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
from utils.permission import get_user_permissions, has_permission
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
