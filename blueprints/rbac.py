"""RBAC 蓝图（V14）

URL 前缀：/rbac
路由：
  GET  /rbac/roles                         角色列表
  GET  /rbac/roles/add                     新增角色 form
  POST /rbac/roles/add                     保存
  GET  /rbac/roles/<int:rid>/edit          编辑角色 form
  POST /rbac/roles/<int:rid>/edit          保存
  POST /rbac/roles/<int:rid>/delete        删除
  GET  /rbac/roles/<int:rid>/permissions   权限矩阵
  POST /rbac/roles/<int:rid>/permissions   保存勾选
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from datetime import datetime
from flask_login import login_required, current_user
from models import db, Role, RolePermission, Permission, UserPermission, User
from utils.permission import (
    require_permission, admin_required,
    PERMISSION_MAP, invalidate_role,
)

rbac_bp = Blueprint('rbac', __name__)


# ============================
# 角色 CRUD
# ============================

@rbac_bp.route('/roles')
@login_required
@require_permission('permission:view')
def role_list():
    roles = Role.query.order_by(Role.sort_order, Role.id).all()
    # 统计每个角色的权限码数
    perm_counts = {}
    for r in roles:
        perm_counts[r.id] = len([rp.permission_code for rp in r.role_perms])
    return render_template('rbac/role_list.html', roles=roles, perm_counts=perm_counts,
                          total_perms=len(PERMISSION_MAP))


@rbac_bp.route('/roles/add', methods=['GET', 'POST'])
@login_required
@require_permission('permission:edit')
def role_add():
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip().lower()
        name = (request.form.get('name') or '').strip()
        description = (request.form.get('description') or '').strip()
        sort_order = int(request.form.get('sort_order') or 99)
        is_active = bool(request.form.get('is_active'))

        if not code or not name:
            flash('角色代码和名称不能为空', 'danger')
            return redirect(url_for('rbac.role_add'))
        if not code.replace('_', '').isalnum():
            flash('角色代码仅允许字母/数字/下划线', 'danger')
            return redirect(url_for('rbac.role_add'))
        if Role.query.filter_by(code=code).first():
            flash(f'角色代码 {code} 已存在', 'danger')
            return redirect(url_for('rbac.role_add'))

        role = Role(code=code, name=name, description=description,
                   is_system=False, is_active=is_active, sort_order=sort_order)
        db.session.add(role)
        db.session.commit()
        flash(f'角色 {name} 已创建', 'success')
        return redirect(url_for('rbac.role_permissions_edit', rid=role.id))

    return render_template('rbac/role_form.html', role=None)


@rbac_bp.route('/roles/<int:rid>/edit', methods=['GET', 'POST'])
@login_required
@require_permission('permission:edit')
def role_edit(rid):
    role = Role.query.get_or_404(rid)
    if request.method == 'POST':
        # code 不可改（避免破坏 User.role 字符串外键）
        name = (request.form.get('name') or '').strip()
        description = (request.form.get('description') or '').strip()
        sort_order = int(request.form.get('sort_order') or 0)
        is_active = bool(request.form.get('is_active'))

        if not name:
            flash('角色名称不能为空', 'danger')
            return redirect(url_for('rbac.role_edit', rid=rid))

        role.name = name
        role.description = description
        role.sort_order = sort_order
        role.is_active = is_active
        db.session.commit()
        invalidate_role(role.code)
        flash(f'角色 {name} 已更新', 'success')
        return redirect(url_for('rbac.role_list'))

    return render_template('rbac/role_form.html', role=role)


@rbac_bp.route('/roles/<int:rid>/delete', methods=['POST'])
@login_required
@require_permission('permission:edit')
@admin_required
def role_delete(rid):
    role = Role.query.get_or_404(rid)
    if role.is_system:
        msg = f'角色 {role.name} 是系统内置角色，不可删除'
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in (request.headers.get('Accept') or ''):
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, 'danger')
        return redirect(url_for('rbac.role_list'))
    # 检查是否有用户绑定
    bound_users = User.query.filter_by(role=role.code, is_active=True).count()
    if bound_users > 0:
        msg = f'角色 {role.name} 还有 {bound_users} 个活跃用户，无法删除。请先将用户改到其他角色。'
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in (request.headers.get('Accept') or ''):
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, 'danger')
        return redirect(url_for('rbac.role_list'))
    # 删 role_permissions（级联）
    RolePermission.query.filter_by(role_id=role.id).delete()
    name = role.name
    code = role.code
    db.session.delete(role)
    db.session.commit()
    invalidate_role(code)
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in (request.headers.get('Accept') or ''):
        return jsonify({'success': True, 'message': f'角色 {name} 已删除'})
    flash(f'角色 {name} 已删除', 'success')
    return redirect(url_for('rbac.role_list'))


# ============================
# 角色-权限 矩阵
# ============================

@rbac_bp.route('/roles/<int:rid>/permissions', methods=['GET', 'POST'])
@login_required
@require_permission('permission:edit')
def role_permissions_edit(rid):
    role = Role.query.get_or_404(rid)

    if request.method == 'POST':
        # admin 短路：用户传什么都忽略（保证 admin 永远有所有权限）
        if role.code == 'admin':
            flash('admin 角色拥有系统全部权限，无需配置', 'info')
            return redirect(url_for('rbac.role_permissions_edit', rid=rid))

        # 期望表单：所有提交的 permission_code 即为勾选
        submitted = set(request.form.getlist('permission_codes'))
        existing = {rp.permission_code for rp in role.role_perms}

        # 新增
        for code in submitted - existing:
            db.session.add(RolePermission(role_id=role.id, permission_code=code))
        # 删除
        for code in existing - submitted:
            rp = RolePermission.query.filter_by(role_id=role.id, permission_code=code).first()
            if rp:
                db.session.delete(rp)
        db.session.commit()
        invalidate_role(role.code)
        flash(f'角色 {role.name} 的权限已更新', 'success')
        return redirect(url_for('rbac.role_permissions_edit', rid=rid))

    # GET：渲染矩阵
    all_perms = Permission.query.filter_by(is_active=True).order_by(
        Permission.category, Permission.sort_order, Permission.id
    ).all()
    current_perms = {rp.permission_code for rp in role.role_perms}
    return render_template('rbac/role_permissions.html',
                          role=role, all_perms=all_perms,
                          current_perms=current_perms)


# ============================
# 用户级权限覆盖
# ============================

@rbac_bp.route('/users/<int:uid>/permissions', methods=['GET', 'POST'])
@login_required
@require_permission('permission:edit')
@admin_required
def user_permissions(uid):
    """用户级权限覆盖：grant / deny / inherit 三态

    POST：表单字段
      - perms[<code>] = 'grant' | 'deny' | '' （空 = 删除覆盖 = 继承角色）
      - expire_at[<code>] = YYYY-MM-DD
      - remarks[<code>] = 备注
    """
    user = User.query.get_or_404(uid)

    if request.method == 'POST':
        # 清空该用户现有覆盖，重新写
        UserPermission.query.filter_by(user_id=user.id).delete()
        db.session.flush()

        perms = request.form.getlist('perms_keys')  # 所有被提交的权限码
        for code in perms:
            state = request.form.get(f'perms[{code}]', '')
            if state not in ('grant', 'deny'):
                continue
            expire_raw = request.form.get(f'expire_at[{code}]', '').strip()
            remark = (request.form.get(f'remarks[{code}]', '') or '').strip()
            expire_at = None
            if expire_raw:
                try:
                    expire_at = datetime.strptime(expire_raw, '%Y-%m-%d')
                except ValueError:
                    flash(f'权限 {code} 的过期日期格式错误（应为 YYYY-MM-DD）', 'danger')
                    continue
            up = UserPermission(
                user_id=user.id,
                permission_code=code,
                grant_type=state,
                granted_by_user_id=current_user.id,
                granted_at=datetime.utcnow(),
                expire_at=expire_at,
                remark=remark,
            )
            db.session.add(up)
        db.session.commit()
        flash(f'用户 {user.username} 的权限覆盖已更新', 'success')
        return redirect(url_for('rbac.user_permissions', uid=uid))

    # GET
    from utils.permission import PERMISSION_MAP
    from datetime import date
    all_perms = Permission.query.filter_by(is_active=True).order_by(
        Permission.category, Permission.sort_order, Permission.id
    ).all()
    overrides = {up.permission_code: up for up in user.extra_permissions}
    return render_template('users/permissions_tab.html',
                          user=user, all_perms=all_perms,
                          overrides=overrides, today=date.today().isoformat())
