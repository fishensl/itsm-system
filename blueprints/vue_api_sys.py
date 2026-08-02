# -*- coding: utf-8 -*-
"""Vue SPA 系统 API（系统域：用户/RBAC / 部门 / 备份 / 审计日志 / 系统概览）

复用 blueprints.vue_api 的 vue_api_bp 蓝图对象与 ok/fail 契约。
"""
from flask import request, current_app
from flask_login import login_required, current_user

from blueprints.vue_api import vue_api_bp, ok, fail
from models import db, Role


def audit_log(action, target_type='', target_id=None, detail=''):
    """写操作审计（表 + logger 双写，失败不阻断主流程）"""
    from models import AuditLog
    try:
        db.session.add(AuditLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            username=current_user.username if current_user.is_authenticated else '',
            action=action, target_type=target_type, target_id=target_id,
            detail=(detail or '')[:500], ip=request.remote_addr or ''))
        db.session.commit()
        current_app.logger.info(
            '审计[%s] 用户[%s] %s%s, IP=%s',
            action,
            current_user.username if current_user.is_authenticated else '?',
            f'{target_type}#{target_id} ' if target_type else '',
            detail, request.remote_addr)
    except Exception:
        db.session.rollback()
        current_app.logger.warning('审计写入失败: %s', action)


# ==================== 审计日志 ====================
@vue_api_bp.route('/api/audit-logs', methods=['GET'])
@login_required
def api_audit_logs():
    """审计日志查询（admin；敏感操作均经 audit_log 写入）"""
    if current_user.role != 'admin':
        return fail('需要管理员权限', 403)
    from models import AuditLog
    page = request.args.get('page', 1, type=int)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    username = (request.args.get('username') or '').strip()
    action = (request.args.get('action') or '').strip()
    target_type = (request.args.get('target_type') or '').strip()
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()

    q = AuditLog.query
    if username:
        q = q.filter(AuditLog.username.contains(username))
    if action:
        q = q.filter(AuditLog.action == action)
    if target_type:
        q = q.filter(AuditLog.target_type == target_type)
    if date_from:
        q = q.filter(AuditLog.created_at >= date_from)
    if date_to:
        q = q.filter(AuditLog.created_at <= date_to + ' 23:59:59')
    total = q.count()
    rows = q.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ok({
        'items': [{
            'id': r.id, 'username': r.username, 'action': r.action,
            'target_type': r.target_type, 'target_id': r.target_id,
            'detail': r.detail, 'ip': r.ip,
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else '',
        } for r in rows],
        'total': total, 'page': page, 'page_size': page_size,
    })


@vue_api_bp.route('/api/dicts/audit', methods=['GET'])
@login_required
def api_audit_dicts():
    if current_user.role != 'admin':
        return fail('需要管理员权限', 403)
    from models import AuditLog
    actions = [r[0] for r in db.session.query(AuditLog.action).distinct()
               .filter(AuditLog.action != '').order_by(AuditLog.action).all()]
    target_types = [r[0] for r in db.session.query(AuditLog.target_type).distinct()
                    .filter(AuditLog.target_type != '').order_by(AuditLog.target_type).all()]
    return ok({'actions': actions, 'target_types': target_types})


# ==================== 用户管理（admin） ====================
@vue_api_bp.route('/api/users', methods=['GET'])
@login_required
def api_user_list():
    if current_user.role != 'admin':
        return fail('需要管理员权限', 403)
    from models import User, Department
    users = User.query.order_by(User.id).all()
    dept_map = {d.id: d.name for d in Department.query.all()}
    roles = [r.code for r in Role.query.filter_by(is_active=True)
             .order_by(Role.sort_order, Role.id).all()]
    return ok({
        'users': [{
            'id': u.id, 'username': u.username, 'realname': u.realname or '',
            'role': u.role or 'viewer', 'department_id': u.department_id,
            'department_name': dept_map.get(u.department_id, ''),
            'is_active': bool(u.is_active), 'phone': u.phone or '', 'email': u.email or '',
            'created_at': u.created_at.strftime('%Y-%m-%d') if u.created_at else '',
        } for u in users],
        'departments': [{'id': d.id, 'name': d.name}
                        for d in Department.query.order_by(Department.sort_order).all()],
        'roles': roles,
    })


@vue_api_bp.route('/api/users', methods=['POST'])
@login_required
def api_user_create():
    if current_user.role != 'admin':
        return fail('需要管理员权限', 403)
    from models import User
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or 'changeme'
    if not username:
        return fail('用户名不能为空', 400)
    if User.query.filter_by(username=username).first():
        return fail(f'用户名「{username}」已存在', 400)
    u = User.create_with_password(
        username=username, password=password,
        realname=(data.get('realname') or '').strip(),
        role=data.get('role') or 'viewer',
        department_id=int(data['department_id']) if data.get('department_id') else None)
    u.phone = (data.get('phone') or '').strip()
    u.email = (data.get('email') or '').strip()
    u.is_active = bool(data.get('is_active', True))
    db.session.add(u)
    db.session.commit()
    audit_log('user:create', 'user', u.id, f'创建用户 {username}')
    return ok({'id': u.id})


@vue_api_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
def api_user_update(user_id):
    if current_user.role != 'admin':
        return fail('需要管理员权限', 403)
    from models import User
    u = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    new_username = (data.get('username') or '').strip()
    if not new_username:
        return fail('用户名不能为空', 400)
    if new_username != u.username and User.query.filter_by(username=new_username).first():
        return fail(f'用户名「{new_username}」已被占用', 400)
    u.username = new_username
    u.realname = (data.get('realname') or '').strip()
    u.role = data.get('role') or u.role
    u.department_id = int(data['department_id']) if data.get('department_id') else None
    u.is_active = bool(data.get('is_active', True))
    u.phone = (data.get('phone') or '').strip()
    u.email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    if password:
        u.set_password(password)
    db.session.commit()
    audit_log('user:update', 'user', u.id, f'更新用户 {new_username}')
    return ok(None)


@vue_api_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
def api_user_delete(user_id):
    if current_user.role != 'admin':
        return fail('需要管理员权限', 403)
    from models import User
    u = User.query.get_or_404(user_id)
    if u.id == current_user.id:
        return fail('不能删除当前登录账号', 400)
    audit_log('user:delete', 'user', u.id, f'删除用户 {u.username}')
    User.query.filter_by(id=user_id).delete()
    db.session.commit()
    return ok(None)


# ==================== 部门 ====================
@vue_api_bp.route('/api/departments', methods=['GET'])
@login_required
def api_department_list():
    from models import Department, User
    departments = Department.query.order_by(Department.sort_order, Department.id).all()
    users = User.query.filter_by(is_active=True).order_by(User.realname).all()
    return ok({
        'departments': [{
            'id': d.id, 'name': d.name, 'parent_id': d.parent_id,
            'head_id': d.head_id, 'sort_order': d.sort_order,
        } for d in departments],
        'users': [{'id': u.id, 'name': u.realname or u.username} for u in users],
    })


@vue_api_bp.route('/api/departments', methods=['POST'])
@login_required
def api_department_create():
    if current_user.role != 'admin':
        return fail('需要管理员权限', 403)
    from models import Department
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('部门名称不能为空', 400)
    if Department.query.filter_by(name=name).first():
        return fail('部门名称已存在', 400)
    d = Department(name=name,
                   parent_id=int(data['parent_id']) if data.get('parent_id') else None,
                   head_id=int(data['head_id']) if data.get('head_id') else None,
                   sort_order=int(data.get('sort_order') or 0))
    db.session.add(d)
    db.session.commit()
    return ok({'id': d.id})


@vue_api_bp.route('/api/departments/<int:dept_id>', methods=['PUT'])
@login_required
def api_department_update(dept_id):
    if current_user.role != 'admin':
        return fail('需要管理员权限', 403)
    from models import Department
    d = Department.query.get_or_404(dept_id)
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if name:
        d.name = name
    if data.get('parent_id'):
        d.parent_id = int(data['parent_id'])
    if data.get('head_id'):
        d.head_id = int(data['head_id'])
    if data.get('sort_order') is not None:
        d.sort_order = int(data['sort_order'])
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/departments/<int:dept_id>', methods=['DELETE'])
@login_required
def api_department_delete(dept_id):
    if current_user.role != 'admin':
        return fail('需要管理员权限', 403)
    from models import Department, User
    d = Department.query.get_or_404(dept_id)
    if User.query.filter_by(department_id=dept_id).count() > 0:
        return fail(f'部门「{d.name}」下仍有成员，无法删除', 400)
    if Department.query.filter_by(parent_id=dept_id).count() > 0:
        return fail(f'部门「{d.name}」下有子部门，无法删除', 400)
    db.session.delete(d)
    db.session.commit()
    return ok(None)


# ==================== 系统概览 ====================
@vue_api_bp.route('/api/system/overview', methods=['GET'])
@login_required
def api_system_overview():
    """系统概览：业务统计 + 版本（CPU/内存等资源采集在 SSR 已有，Vue 简版）"""
    from models import (User, Customer, Device, Ticket, Inspection, KnowledgeBase,
                        SparePart, Topology, Department, Notification, AuditLog)
    stats = {
        'user': User.query.count(),
        'department': Department.query.count(),
        'customer': Customer.query.count(),
        'device': Device.query.count(),
        'ticket': Ticket.query.count(),
        'inspection': Inspection.query.count(),
        'kb': KnowledgeBase.query.count(),
        'spare': SparePart.query.count(),
        'topology': Topology.query.count(),
        'notification_unread': Notification.query.filter_by(
            user_id=current_user.id, is_read=False).count(),
        'audit_today': AuditLog.query.count(),
    }
    try:
        with open(current_app.root_path + '/VERSION', encoding='utf-8') as f:
            version = f.read().strip()
    except Exception:
        version = 'unknown'
    return ok({'stats': stats, 'version': version})
