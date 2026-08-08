# -*- coding: utf-8 -*-
"""Vue SPA 系统 API（系统域：用户/RBAC / 部门 / 备份 / 审计日志 / 系统概览）

复用 blueprints.vue_api 的 vue_api_bp 蓝图对象与 ok/fail 契约。
"""
from flask import request, current_app
from flask_login import login_required, current_user

from blueprints.vue_api import vue_api_bp, ok, fail
from models import db, Role, user_regions
from utils.permission import require_permission, admin_required


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
    if not current_user.is_admin:
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
    if not current_user.is_admin:
        return fail('需要管理员权限', 403)
    from models import AuditLog
    actions = [r[0] for r in db.session.query(AuditLog.action).distinct()
               .filter(AuditLog.action != '').order_by(AuditLog.action).all()]
    target_types = [r[0] for r in db.session.query(AuditLog.target_type).distinct()
                    .filter(AuditLog.target_type != '').order_by(AuditLog.target_type).all()]
    return ok({'actions': actions, 'target_types': target_types})


# ==================== 用户管理（admin） ====================
def _set_user_roles(user, roles):
    """设置用户多角色：校验非空、角色存在；写入 role_codes 并同步主角色 role"""
    codes = [str(r).strip() for r in (roles or []) if str(r).strip()]
    if not codes:
        raise ValueError('至少选择一个角色')
    existing = {r.code for r in Role.query.all()}
    unknown = [c for c in codes if c not in existing]
    if unknown:
        raise ValueError(f'角色不存在：{", ".join(unknown)}')
    user.set_role_codes(codes)


@vue_api_bp.route('/api/users', methods=['GET'])
@login_required
def api_user_list():
    if not current_user.is_admin:
        return fail('需要管理员权限', 403)
    from models import User, Department
    page = max(request.args.get('page', 1, type=int), 1)
    page_size = min(request.args.get('page_size', 20, type=int), 100)
    search = (request.args.get('search') or '').strip()
    q = User.query
    if search:
        like = f'%{search}%'
        q = q.filter(db.or_(User.username.like(like), User.realname.like(like)))
    total = q.count()
    users = q.order_by(User.id).offset((page - 1) * page_size).limit(page_size).all()
    dept_map = {d.id: d.name for d in Department.query.all()}
    roles = [r.code for r in Role.query.filter_by(is_active=True)
             .order_by(Role.sort_order, Role.id).all()]
    role_names = {r.code: r.name for r in Role.query.all()}
    # 用户负责区域：一次 IN 预加载（多对多），避免逐用户 N+1
    region_map = {}
    if users:
        from models import Region
        uids = [u.id for u in users]
        rows = db.session.execute(
            db.select(user_regions.c.user_id, user_regions.c.region_id)
            .where(user_regions.c.user_id.in_(uids))
            .order_by(user_regions.c.region_id)).all()
        for uid, rid in rows:
            region_map.setdefault(uid, []).append(rid)
        region_names = {r.id: r.name for r in Region.query.all()}
    else:
        region_names = {}
    # 用户直接关联客户：一次 IN 预加载
    cust_map = {}
    cust_names = {}
    if users:
        from models import Customer, customer_engineers as _ce
        uids = [u.id for u in users]
        rows = db.session.execute(
            db.select(_ce.c.engineer_id, _ce.c.customer_id)
            .where(_ce.c.engineer_id.in_(uids))
            .order_by(_ce.c.customer_id)).all()
        for uid, cid in rows:
            cust_map.setdefault(uid, []).append(cid)
        if cust_map:
            all_cids = {cid for cids in cust_map.values() for cid in cids}
            cust_names = {c.id: c.name for c in Customer.query.filter(Customer.id.in_(all_cids))}
    return ok({
        'users': [{
            'id': u.id, 'username': u.username, 'realname': u.realname or '',
            'role': u.role or 'viewer', 'role_name': role_names.get(u.role, u.role or 'viewer'),
            'roles': u.role_codes_list(),
            'department_id': u.department_id,
            'department_name': dept_map.get(u.department_id, ''),
            'is_active': bool(u.is_active), 'phone': u.phone or '', 'email': u.email or '',
            'certifications': u.cert_list(),
            'region_ids': region_map.get(u.id, []),
            'region_names': [region_names.get(rid, '') for rid in region_map.get(u.id, [])],
            'customer_ids': cust_map.get(u.id, []),
            'customer_names': [cust_names.get(cid, '') for cid in cust_map.get(u.id, [])],
            'created_at': u.created_at.strftime('%Y-%m-%d') if u.created_at else '',
        } for u in users],
        'departments': [{'id': d.id, 'name': d.name}
                        for d in Department.query.order_by(Department.sort_order).all()],
        'roles': roles,
        'role_names': role_names,
        'total': total, 'page': page, 'page_size': page_size,
    })


@vue_api_bp.route('/api/users', methods=['POST'])
@login_required
def api_user_create():
    if not current_user.is_admin:
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
    if 'roles' in data:
        try:
            _set_user_roles(u, data['roles'])
        except ValueError as e:
            return fail(str(e), 400)
    elif not u.role_codes_list():
        u.set_role_codes([u.role or 'viewer'])
    u.phone = (data.get('phone') or '').strip()
    u.email = (data.get('email') or '').strip()
    u.is_active = bool(data.get('is_active', True))
    if data.get('certifications') is not None:
        u.set_cert_list(list(data['certifications']))
    if data.get('region_ids'):
        from models import Region
        u.regions = Region.query.filter(Region.id.in_(
            [int(x) for x in data['region_ids']])).all()
    if data.get('customer_ids') is not None:
        from models import Customer
        u.customers = Customer.query.filter(Customer.id.in_(
            [int(x) for x in data['customer_ids']])).all() if data['customer_ids'] else []
    db.session.add(u)
    db.session.commit()
    audit_log('user:create', 'user', u.id, f'创建用户 {username}')
    return ok({'id': u.id})


@vue_api_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
def api_user_update(user_id):
    if not current_user.is_admin:
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
    if data.get('roles') is not None:
        try:
            _set_user_roles(u, data['roles'])
        except ValueError as e:
            return fail(str(e), 400)
    elif data.get('role') and data.get('role') != u.role:
        codes = [data['role']] + [c for c in u.role_codes_list() if c != data['role']]
        u.set_role_codes(codes)
    u.department_id = int(data['department_id']) if data.get('department_id') else None
    u.is_active = bool(data.get('is_active', True))
    u.phone = (data.get('phone') or '').strip()
    u.email = (data.get('email') or '').strip()
    if data.get('certifications') is not None:
        u.set_cert_list(list(data['certifications']))
    if 'region_ids' in data:
        from models import Region
        u.regions = Region.query.filter(Region.id.in_(
            [int(x) for x in data['region_ids']])).all() if data['region_ids'] else []
    if 'customer_ids' in data:
        from models import Customer
        u.customers = Customer.query.filter(Customer.id.in_(
            [int(x) for x in data['customer_ids']])).all() if data['customer_ids'] else []
    password = data.get('password') or ''
    if password:
        u.set_password(password)
    db.session.commit()
    audit_log('user:update', 'user', u.id, f'更新用户 {new_username}')
    return ok(None)


@vue_api_bp.route('/api/users/<int:user_id>/password', methods=['PUT'])
@login_required
def api_user_reset_password(user_id):
    """管理员强制重置任意账号密码（无需原密码）"""
    if not current_user.is_admin:
        return fail('需要管理员权限', 403)
    from models import User
    u = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    new_pwd = (data.get('new_password') or '').strip()
    if len(new_pwd) < 6:
        return fail('新密码长度至少 6 位', 400)
    u.set_password(new_pwd)
    db.session.commit()
    audit_log('user:reset_password', 'user', u.id, f'管理员重置用户 {u.username} 的密码')
    return ok(None)


@vue_api_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
def api_user_delete(user_id):
    if not current_user.is_admin:
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
    if not current_user.is_admin:
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
    audit_log('dept:create', 'department', d.id, f'创建部门 {name}')
    return ok({'id': d.id})


@vue_api_bp.route('/api/departments/<int:dept_id>', methods=['PUT'])
@login_required
def api_department_update(dept_id):
    if not current_user.is_admin:
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
    audit_log('dept:update', 'department', dept_id, f'更新部门 {d.name}')
    return ok(None)


@vue_api_bp.route('/api/departments/<int:dept_id>', methods=['DELETE'])
@login_required
def api_department_delete(dept_id):
    if not current_user.is_admin:
        return fail('需要管理员权限', 403)
    from models import Department, User
    d = Department.query.get_or_404(dept_id)
    if User.query.filter_by(department_id=dept_id).count() > 0:
        return fail(f'部门「{d.name}」下仍有成员，无法删除', 400)
    if Department.query.filter_by(parent_id=dept_id).count() > 0:
        return fail(f'部门「{d.name}」下有子部门，无法删除', 400)
    db.session.delete(d)
    db.session.commit()
    audit_log('dept:delete', 'department', dept_id, f'删除部门 {d.name}')
    return ok(None)


# ==================== 界面版本切换 ====================
@vue_api_bp.route('/api/system/ui-version', methods=['GET'])
@login_required
def api_ui_version_get():
    from utils.ui_version import get_ui_version, _VUE_URL_MAP
    return ok({'version': get_ui_version(), 'vue_migrated_count': len(_VUE_URL_MAP)})


@vue_api_bp.route('/api/system/ui-version', methods=['PUT'])
@login_required
def api_ui_version_set():
    if not current_user.is_admin:
        return fail('需要管理员权限', 403)
    from utils.ui_version import set_ui_version
    data = request.get_json(silent=True) or {}
    version = data.get('version')
    if version not in ('vue', 'ssr'):
        return fail('非法的界面版本', 400)
    set_ui_version(version)
    audit_log('system:ui_version', 'system', None, f'切换默认界面为 {version}')
    return ok({'version': version})


# ==================== 系统概览 ====================
@vue_api_bp.route('/api/system/overview', methods=['GET'])
@login_required
def api_system_overview():
    """系统概览：业务统计 + 最近用户 + 版本 + 部署信息（与 SSR 系统概览同模块结构）"""
    from models import (User, Customer, Device, Ticket, Inspection,
                        Topology, Department)
    from utils.system_info import collect_deployment_info
    stats = {
        'user_active': User.query.filter_by(is_active=True).count(),
        'user_total': User.query.count(),
        'department': Department.query.count(),
        'customer': Customer.query.count(),
        'device': Device.query.count(),
        'topology': Topology.query.count(),
        'inspection': Inspection.query.count(),
        'ticket': Ticket.query.count(),
    }
    recent_users = [
        {'name': u.realname or u.username, 'username': u.username, 'role': u.role or 'viewer'}
        for u in User.query.order_by(User.id.desc()).limit(5).all()
    ]
    try:
        with open(current_app.root_path + '/VERSION', encoding='utf-8') as f:
            version = f.read().strip()
    except Exception:
        version = 'unknown'
    return ok({'stats': stats, 'recent_users': recent_users, 'version': version,
               'deploy': collect_deployment_info()})


@vue_api_bp.route('/api/system/repair-device-counts', methods=['POST'])
@login_required
@require_permission('system:repair')
def api_repair_device_counts():
    """全客户重算 device_count/等级（修复冗余快照与 devices 表不一致，如幽灵设备残留）。

    口径与删除校验一致（devices 表实际行数）。返回修复明细，写审计日志。
    """
    from models import Customer as _Cust, Device as _Dev
    from services.device_service import sync_customer_device_count
    rows = []
    for c in _Cust.query.order_by(_Cust.id).all():
        real = _Dev.query.filter_by(customer_id=c.id).count()
        if c.device_count != real:
            rows.append({'customer_id': c.id, 'name': c.name,
                         'before': c.device_count or 0, 'after': real})
    for r in rows:
        try:
            sync_customer_device_count(r['customer_id'])
        except Exception:
            db.session.rollback()
    if rows:
        audit_log('system:repair_device_counts', 'system', None,
                  f'修复 {len(rows)} 个客户设备数: ' +
                  '; '.join(f"{r['name']}({r['before']}→{r['after']})" for r in rows[:20]))
    return ok({'fixed': len(rows), 'details': rows[:50],
               'total_customers': _Cust.query.count()})

# ==================== 侧栏自定义 ====================
@vue_api_bp.route('/api/system/sidebar', methods=['GET'])
@login_required
def api_sidebar_custom_get():
    """全部分组（含禁用）+ 当前启停/顺序（按用户偏好顺序）"""
    from utils.sidebar_config import get_user_sidebar_groups
    current = get_user_sidebar_groups(current_user)
    return ok([
        {'key': g['key'], 'title': g['title'], 'enabled': bool(g.get('enabled', True))}
        for g in current
    ])


@vue_api_bp.route('/api/system/sidebar', methods=['PUT'])
@login_required
def api_sidebar_custom_save():
    from utils.sidebar_config import save_user_sidebar
    payload = request.get_json(silent=True) or {}
    groups_data = payload.get('groups', [])
    if not isinstance(groups_data, list) or not all(
            isinstance(g, dict) and g.get('key') for g in groups_data):
        return fail('参数错误', 400)
    save_user_sidebar(current_user, groups_data)
    return ok(None)


@vue_api_bp.route('/api/system/sidebar/reset', methods=['POST'])
@login_required
def api_sidebar_custom_reset():
    from models import UserDashboardPreference
    pref = UserDashboardPreference.query.filter_by(user_id=current_user.id).first()
    if pref:
        pref.sidebar_json = None
        db.session.commit()
    return ok(None)

# ==================== AI 对接 ====================
def _ai_payload(c):
    return {
        'id': c.id,
        'provider': c.provider or 'OpenAI',
        'api_endpoint': c.api_endpoint or '',
        'has_api_key': bool(c.api_key_encrypted),
        'model_name': c.model_name or '',
        'max_tokens': c.max_tokens or 2048,
        'temperature': c.temperature if c.temperature is not None else 0.7,
        'inspection_prompt_template': c.inspection_prompt_template or '',
        'fault_prompt_template': c.fault_prompt_template or '',
        'is_enabled': bool(c.is_enabled),
    }


@vue_api_bp.route('/api/ai-config', methods=['GET'])
@login_required
@require_permission('ai:view')
def api_ai_config_list():
    from models import AIConfig
    configs = AIConfig.query.order_by(AIConfig.id.desc()).all()
    return ok([_ai_payload(c) for c in configs])


@vue_api_bp.route('/api/ai-config', methods=['POST'])
@login_required
@require_permission('ai:edit')
def api_ai_config_add():
    from models import AIConfig
    from utils.crypto import encrypt_password
    data = request.get_json(silent=True) or {}
    cfg = AIConfig(
        provider=(data.get('provider') or 'OpenAI').strip() or 'OpenAI',
        api_endpoint=(data.get('api_endpoint') or '').strip(),
        model_name=(data.get('model_name') or '').strip(),
        max_tokens=int(data.get('max_tokens') or 2048),
        temperature=float(data.get('temperature') if data.get('temperature') is not None else 0.7),
        inspection_prompt_template=(data.get('inspection_prompt_template') or '').strip(),
        fault_prompt_template=(data.get('fault_prompt_template') or '').strip(),
        is_enabled=bool(data.get('is_enabled')),
    )
    key = (data.get('api_key') or '').strip()
    if key:
        cfg.api_key_encrypted = encrypt_password(key)
    db.session.add(cfg)
    db.session.commit()
    current_app.logger.info('AI 配置新增: id=%s', cfg.id)
    return ok({'id': cfg.id})


@vue_api_bp.route('/api/ai-config/<int:cid>', methods=['PUT'])
@login_required
@require_permission('ai:edit')
def api_ai_config_update(cid):
    from models import AIConfig
    from utils.crypto import encrypt_password
    cfg = AIConfig.query.get_or_404(cid)
    data = request.get_json(silent=True) or {}
    if data.get('provider') is not None:
        cfg.provider = (data['provider'] or 'OpenAI').strip() or 'OpenAI'
    if data.get('api_endpoint') is not None:
        cfg.api_endpoint = (data['api_endpoint'] or '').strip()
    if data.get('model_name') is not None:
        cfg.model_name = (data['model_name'] or '').strip()
    if data.get('max_tokens') is not None:
        cfg.max_tokens = int(data['max_tokens'] or 2048)
    if data.get('temperature') is not None:
        cfg.temperature = float(data['temperature'])
    if data.get('inspection_prompt_template') is not None:
        cfg.inspection_prompt_template = (data['inspection_prompt_template'] or '').strip()
    if data.get('fault_prompt_template') is not None:
        cfg.fault_prompt_template = (data['fault_prompt_template'] or '').strip()
    if data.get('is_enabled') is not None:
        cfg.is_enabled = bool(data['is_enabled'])
    key = (data.get('api_key') or '').strip()
    if key:
        cfg.api_key_encrypted = encrypt_password(key)
    db.session.commit()
    return ok(None)


@vue_api_bp.route('/api/ai-config/<int:cid>', methods=['DELETE'])
@login_required
@require_permission('ai:edit')
def api_ai_config_delete(cid):
    from models import AIConfig
    AIConfig.query.filter_by(id=cid).delete()
    db.session.commit()
    current_app.logger.info('AI 配置删除: id=%s', cid)
    return ok(None)


@vue_api_bp.route('/api/ai-config/<int:cid>/test', methods=['POST'])
@login_required
@require_permission('ai:edit')
def api_ai_config_test(cid):
    from models import AIConfig
    from utils.ai_client import AIClient
    cfg = AIConfig.query.get_or_404(cid)
    ok_flag, msg = AIClient(cfg).test_connection()
    return ok({'success': ok_flag, 'message': msg})

# ==================== 数据备份 ====================
@vue_api_bp.route('/api/system/backup/stats', methods=['GET'])
@login_required
@admin_required
def api_backup_stats():
    from models import (User, Customer, Device, Ticket, Inspection, Fault,
                        KnowledgeBase, SparePart, Topology)
    import os
    stats = {
        'user': User.query.count(), 'customer': Customer.query.count(),
        'device': Device.query.count(), 'ticket': Ticket.query.count(),
        'inspection': Inspection.query.count(), 'fault': Fault.query.count(),
        'kb': KnowledgeBase.query.count(), 'spare': SparePart.query.count(),
        'topology': Topology.query.count(),
    }
    root = os.path.abspath(current_app.root_path)
    file_size = 0
    for disk_rel in ('reports', 'uploads', os.path.join('static', 'uploads')):
        d = os.path.join(root, disk_rel)
        if os.path.isdir(d):
            for dp, _ds, fs in os.walk(d):
                for fn in fs:
                    try:
                        file_size += os.path.getsize(os.path.join(dp, fn))
                    except OSError:
                        pass
    return ok({'stats': stats, 'file_size_mb': round(file_size / 1024 / 1024, 1)})


@vue_api_bp.route('/api/system/backup/export', methods=['POST'])
@login_required
@admin_required
def api_backup_export():
    """导出备份包：服务端落盘 reports/exports/{token}.zip，返回 token 供一次性下载。

    避免大包 base64 全量回传浏览器（大数据量时内存/连接瓶颈）。
    下载走 /api/system/backup/export-download/<token>（一次性，24h 有效，下载后自动清理）。
    """
    from datetime import datetime
    import os
    from utils.data_io import build_export_zip
    from blueprints.vue_export import save_export_file
    data = request.get_json(silent=True) or {}
    config_only = bool(data.get('config_only'))
    password = (data.get('password') or '').strip() or None
    tmp_path, size, manifest = build_export_zip(config_only=config_only, password=password)
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    suffix = '_config' if config_only else ''
    enc_mark = '_encrypted' if password else ''
    download_name = f'itsm_backup_{ts}{suffix}{enc_mark}.zip'
    current_app.logger.info('用户 [%s] 导出备份包 %s（%s 字节）', current_user.username,
                            download_name, size)
    audit_log('backup:export', 'backup', None, f'导出备份包 {download_name}')
    # 服务端落盘 + ExportFile 登记（token 一次性下载）。
    # 注意：build_export_zip(password=...) 已用 Fernet 整包加密（magic 头），
    # 此处不传 password 避免叠加 pyzipper 层（双密码）；导入时用户用同一密码解密。
    token = save_export_file(tmp_path, download_name, password=None,
                             user_id=current_user.id)
    return ok({'token': token, 'filename': download_name, 'size': size})


@vue_api_bp.route('/api/system/backup/export-download/<token>', methods=['GET'])
@login_required
@admin_required
def api_backup_export_download(token):
    """一次性下载备份包（创建人/admin；响应头 X-Export-Password 下发加密包密码；审计）"""
    from blueprints.vue_export import serve_export_file
    resp = serve_export_file(token, current_user.id, current_user.is_admin)
    if resp is None:
        return fail('导出文件不存在、已下载或已失效（一次性下载，24h 内有效）', 404)
    audit_log('backup:export_download', 'backup', None, '下载备份包')
    return resp


@vue_api_bp.route('/api/system/backup/import', methods=['POST'])
@login_required
@admin_required
def api_backup_import():
    import tempfile
    import os
    import shutil
    from datetime import datetime as _dt
    confirm = (request.form.get('confirm') or '').strip()
    if confirm != '我确认覆盖':
        return fail('请输入"我确认覆盖"以二次确认')
    f = request.files.get('backup_file')
    if not f or not f.filename or not f.filename.lower().endswith('.zip'):
        return fail('请选择 .zip 备份包')
    restore_key = request.form.get('restore_secret_key') == '1'
    import_password = (request.form.get('password') or '').strip() or None
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip', prefix='itsm_import_')
    os.close(tmp_fd)

    # 导入前自动备份当前数据（覆盖恢复有风险：DB 回灌可回滚，但文件/密钥还原不走事务，
    # 磁盘覆盖后无法原子回滚 → 必须先在备份目录留一份全量 zip 兜底）。
    # 失败仅告警不阻断导入（兜底失效但导入流程不受影响）。
    pre_import_name = ''
    try:
        from utils.data_io import build_export_zip
        backup_dir = current_app.config.get('BACKUP_DIR') or os.path.join(current_app.root_path, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        ts = _dt.utcnow().strftime('%Y%m%d_%H%M%S')
        pre_import_name = f'pre_import_{ts}.zip'
        tmp_backup, _size, _manifest = build_export_zip(config_only=False)
        shutil.move(tmp_backup, os.path.join(backup_dir, pre_import_name))
        audit_log('backup:pre_import', 'backup', None,
                  f'导入前自动备份当前数据到 backups/{pre_import_name}')
        current_app.logger.info('用户 [%s] 导入前自动备份: %s', current_user.username, pre_import_name)
    except Exception:
        pre_import_name = ''
        current_app.logger.warning('导入前自动备份失败（导入继续）', exc_info=True)

    try:
        f.save(tmp_path)
        try:
            from utils.data_io import perform_import
            result = perform_import(tmp_path, restore_secret_key=restore_key,
                                    password=import_password)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception('导入备份失败')
            if pre_import_name:
                return fail(f'导入失败：{e}（已自动备份当前数据到 backups/{pre_import_name}，可据此恢复）')
            return fail(f'导入失败：{e}')
        try:
            from utils.permission import invalidate_role
            from models import Role
            for r in Role.query.all():
                invalidate_role(r.code)
        except Exception:
            pass
        msg = (f'导入成功：恢复 {result["restored_rows"]} 行数据、'
               f'{result["restored_files"]} 个文件')
        if result['secret_key_restored']:
            msg += '，已还原加密密钥'
        else:
            msg += '（未还原加密密钥）'
        if result['warnings']:
            msg += '。警告：' + '；'.join(result['warnings'][:3])
        if pre_import_name:
            msg += f'。导入前已自动备份当前数据到 backups/{pre_import_name}'
        current_app.logger.info('用户 [%s] 导入备份：%s', current_user.username, msg)
        audit_log('backup:import', 'backup', None, '导入备份包（覆盖恢复）')
        return ok({'message': msg, 'pre_import_file': pre_import_name or None})
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@vue_api_bp.route('/api/system/backup/config', methods=['GET'])
@login_required
@admin_required
def api_backup_config_get():
    """读自动备份配置（启用开关/时间/保留份数）"""
    from utils.backup_config import get_backup_config
    return ok(get_backup_config())


@vue_api_bp.route('/api/system/backup/config', methods=['POST'])
@login_required
@admin_required
def api_backup_config_save():
    """保存自动备份配置；变更时间后重排调度器备份任务"""
    from utils.backup_config import save_backup_config
    data = request.get_json(silent=True) or {}
    ok_flag, errors = save_backup_config(data)
    if not ok_flag:
        return fail('；'.join(errors), 400)
    try:
        from utils.scheduler import reschedule_backup
        reschedule_backup()
    except Exception:
        current_app.logger.warning('备份任务重排失败')
    audit_log('backup:config', 'backup', None, '更新自动备份配置')
    current_app.logger.info('用户 [%s] 更新自动备份配置: %s', current_user.username, data)
    return ok(None)

# ==================== 权限管理 ====================
def _role_permission_map(role):
    from utils.permission import PERMISSION_MAP
    if role.code == 'admin':
        return set(PERMISSION_MAP.keys())
    return {rp.permission_code for rp in role.role_perms}


@vue_api_bp.route('/api/roles', methods=['GET'])
@login_required
@require_permission('permission:view')
def api_roles_list():
    from models import Role, User
    from utils.permission import PERMISSION_MAP
    # 含停用角色：停用后可再编辑启用；矩阵/下拉用 active_only 过滤
    roles = Role.query.order_by(Role.sort_order, Role.id).all()
    user_counts = dict(db.session.execute(
        db.select(User.role, db.func.count()).group_by(User.role)).all())
    return ok({
        'perm_map': [{'code': k, 'label': v} for k, v in PERMISSION_MAP.items()],
        'roles': [
            {
                'id': r.id, 'code': r.code, 'name': r.name, 'description': r.description or '',
                'is_system': bool(r.is_system), 'is_active': bool(r.is_active),
                'sort_order': r.sort_order or 0,
                'user_count': int(user_counts.get(r.code, 0)),
                'permissions': sorted(_role_permission_map(r)),
            }
            for r in roles
        ],
    })


@vue_api_bp.route('/api/roles', methods=['POST'])
@login_required
@require_permission('permission:edit')
def api_roles_add():
    from models import Role
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip().lower()
    name = (data.get('name') or '').strip()
    if not code or not name:
        return fail('角色代码和名称不能为空')
    if not code.replace('_', '').isalnum():
        return fail('角色代码仅允许字母/数字/下划线')
    if Role.query.filter_by(code=code).first():
        return fail(f'角色代码 {code} 已存在')
    role = Role(code=code, name=name, description=(data.get('description') or '').strip(),
                is_system=False, is_active=bool(data.get('is_active', True)),
                sort_order=int(data.get('sort_order') or 99))
    db.session.add(role)
    db.session.commit()
    return ok({'id': role.id})


@vue_api_bp.route('/api/roles/<int:rid>', methods=['PUT'])
@login_required
@require_permission('permission:edit')
def api_roles_update(rid):
    from models import Role
    from utils.permission import invalidate_role
    role = Role.query.get_or_404(rid)
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return fail('角色名称不能为空')
    role.name = name
    role.description = (data.get('description') or '').strip()
    role.sort_order = int(data.get('sort_order') or 0)
    role.is_active = bool(data.get('is_active', role.is_active))
    db.session.commit()
    invalidate_role(role.code)
    return ok(None)


@vue_api_bp.route('/api/roles/<int:rid>', methods=['DELETE'])
@login_required
@require_permission('permission:edit')
@admin_required
def api_roles_delete(rid):
    from models import Role, RolePermission, User
    from utils.permission import invalidate_role
    role = Role.query.get_or_404(rid)
    if role.is_system:
        return fail(f'角色 {role.name} 是系统内置角色，不可删除', 400)
    bound = User.query.filter(
        (User.role == role.code) | (User.role_codes.like(f'%"{role.code}"%')),
        User.is_active == True).count()
    if bound > 0:
        return fail(f'角色 {role.name} 还有 {bound} 个活跃用户，无法删除', 400)
    RolePermission.query.filter_by(role_id=role.id).delete()
    db.session.delete(role)
    db.session.commit()
    invalidate_role(role.code)
    return ok(None)


@vue_api_bp.route('/api/roles/<int:rid>/permissions', methods=['PUT'])
@login_required
@require_permission('permission:edit')
def api_roles_permissions_save(rid):
    from models import Role, RolePermission
    from utils.permission import invalidate_role
    role = Role.query.get_or_404(rid)
    if role.code == 'admin':
        return fail('admin 角色拥有系统全部权限，无需配置', 400)
    data = request.get_json(silent=True) or {}
    target = set(data.get('codes') or [])
    existing = {rp.permission_code for rp in role.role_perms}
    for code in target - existing:
        db.session.add(RolePermission(role_id=role.id, permission_code=code))
    for code in existing - target:
        rp = RolePermission.query.filter_by(role_id=role.id, permission_code=code).first()
        if rp:
            db.session.delete(rp)
    db.session.commit()
    invalidate_role(role.code)
    return ok(None)


@vue_api_bp.route('/api/users/<int:uid>/permissions', methods=['GET'])
@login_required
@require_permission('permission:view')
def api_user_permissions_get(uid):
    from models import User
    from utils.permission import PERMISSION_MAP
    user = User.query.get_or_404(uid)
    overrides = {}
    for up in user.extra_permissions:
        overrides[up.permission_code] = {
            'grant_type': up.grant_type,
            'expire_at': up.expire_at.strftime('%Y-%m-%d') if up.expire_at else '',
            'remark': up.remark or '',
        }
    return ok({
        'user': {'id': user.id, 'username': user.username, 'realname': user.realname or user.username},
        'perm_map': [{'code': k, 'label': v} for k, v in PERMISSION_MAP.items()],
        'overrides': overrides,
    })


@vue_api_bp.route('/api/users/<int:uid>/permissions', methods=['PUT'])
@login_required
@require_permission('permission:edit')
@admin_required
def api_user_permissions_save(uid):
    from models import User, UserPermission
    from datetime import datetime
    user = User.query.get_or_404(uid)
    data = request.get_json(silent=True) or {}
    overrides = data.get('overrides') or {}
    UserPermission.query.filter_by(user_id=user.id).delete()
    db.session.flush()
    for code, item in overrides.items():
        state = (item.get('grant_type') or '').strip()
        if state not in ('grant', 'deny'):
            continue
        expire_at = None
        expire_raw = (item.get('expire_at') or '').strip()
        if expire_raw:
            try:
                expire_at = datetime.strptime(expire_raw, '%Y-%m-%d')
            except ValueError:
                return fail(f'权限 {code} 的过期日期格式错误（应为 YYYY-MM-DD）', 400)
        db.session.add(UserPermission(
            user_id=user.id, permission_code=code, grant_type=state,
            granted_by_user_id=current_user.id, granted_at=datetime.utcnow(),
            expire_at=expire_at, remark=(item.get('remark') or '').strip(),
        ))
    db.session.commit()
    return ok(None)
