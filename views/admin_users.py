# -*- coding: utf-8 -*-
"""用户管理 / 权限对照 / AI 配置"""
from flask import (render_template, request, redirect, url_for,
                   flash, current_app)
from flask_login import (login_required, current_user)
from sqlalchemy.orm import joinedload
from models import db
from models import AIConfig
from models import Department
from models import Role
from models import User
from utils.permission import require_permission, admin_required


@login_required
@require_permission('user:view')
@admin_required
def user_list():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        if username and not User.query.filter_by(username=username).first():
            from utils.cert_options import parse_cert_form
            u = User.create_with_password(
                username=username,
                password=request.form.get('password', 'changeme'),
                realname=request.form.get('realname', ''),
                role=request.form.get('role', 'viewer'),
                department_id=request.form.get('department_id', type=int),
            )
            # V13: 人员主数据扩展
            u.phone = (request.form.get('phone') or '').strip()
            u.email = (request.form.get('email') or '').strip()
            u.set_cert_list(parse_cert_form(request.form.getlist('certifications')))
            db.session.add(u); db.session.commit()
            flash(f'用户 {username} 已创建', 'success')
        return redirect(url_for('user_list'))
    users = User.query.options(joinedload(User.department_rel)).order_by(User.id).all()
    departments = Department.query.order_by(Department.sort_order).all()
    roles = Role.query.filter_by(is_active=True).order_by(Role.sort_order, Role.id).all()
    return render_template('users/list.html', users=users, departments=departments, roles=roles,
                           page=1, total_pages=1, has_prev=False, has_next=False,
                           prev_page=None, next_page=None,
                           total=len(users), start=1 if users else 0, end=len(users))


@login_required
@require_permission('user:delete')
@admin_required
def user_delete(id):
    User.query.filter_by(id=id).delete()
    db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('user_list'))


@login_required
@require_permission('user:add')
@admin_required
def user_add():
    return redirect(url_for('user_list'))


# ==================== 用户编辑（V6.1.4） ====================
@login_required
@require_permission('user:edit')
@admin_required
def user_edit(id):
    """编辑用户：用户名（unique）、姓名、角色、密码、状态、部门、电话、邮箱、证书"""
    u = User.query.get_or_404(id)
    if request.method == 'POST':
        new_username = (request.form.get('username') or '').strip()
        if not new_username:
            flash('用户名不能为空', 'danger')
            return redirect(url_for('user_edit', id=id))
        # 用户名唯一性校验
        if new_username != u.username:
            if User.query.filter_by(username=new_username).first():
                flash(f'用户名 "{new_username}" 已被其他账号占用', 'danger')
                return redirect(url_for('user_edit', id=id))
        from utils.cert_options import parse_cert_form
        pwd = request.form.get('password', '').strip()
        u.username = new_username
        u.realname = (request.form.get('realname') or '').strip()
        u.role = request.form.get('role', u.role or 'operator')
        u.department_id = request.form.get('department_id', type=int)
        u.is_active = bool(request.form.get('is_active'))
        # V13: 人员主数据扩展
        u.phone = (request.form.get('phone') or '').strip()
        u.email = (request.form.get('email') or '').strip()
        u.set_cert_list(parse_cert_form(request.form.getlist('certifications')))
        if pwd:
            u.set_password(pwd)
        db.session.commit()
        flash(f'用户 {u.username} 已更新', 'success')
        return redirect(url_for('user_list'))

    # GET：渲染编辑页（用 modal 模式：直接回 user_list 弹窗）
    departments = Department.query.order_by(Department.sort_order).all()
    roles = Role.query.filter_by(is_active=True).order_by(Role.sort_order, Role.id).all()
    return render_template('users/edit.html', u=u, departments=departments, roles=roles)


# ==================== V13: 管理员重置密码 ====================
@login_required
@require_permission('user:edit')
@admin_required
def user_reset_password(id):
    """管理员强制重置任意账号密码（无需原密码）"""
    u = User.query.get_or_404(id)
    new_pwd = (request.form.get('new_password') or '').strip()
    if len(new_pwd) < 6:
        flash('新密码长度至少 6 位', 'danger')
        return redirect(url_for('user_list'))
    u.set_password(new_pwd)
    db.session.commit()
    current_app.logger.info(f'管理员 [{current_user.username}] 重置了用户 [{u.username}] 的密码')
    flash(f'用户 {u.username} 的密码已重置', 'success')
    return redirect(url_for('user_list'))


@login_required
@require_permission('permission:view')
def permission_list():
    """权限管理：展示各角色权限对照（数据来自 DB，自定义角色自动出现）"""
    from utils.permission import PERMISSION_MAP
    # 从 DB 拉所有活跃角色（包含自定义）
    roles = Role.query.filter_by(is_active=True).order_by(Role.sort_order, Role.id).all()
    role_perms = {}
    role_list = []
    # [(code, name, rid), ...] 给模板做"点格子跳到该角色配置"用
    role_meta = {}
    for r in roles:
        perms = frozenset(rp.permission_code for rp in r.role_perms)
        # admin 短路：显示全量
        if r.code == 'admin':
            perms = set(PERMISSION_MAP.keys())
        role_perms[r.code] = list(perms)
        role_list.append((r.code, r.name))
        role_meta[r.code] = r.id
    return render_template('permissions/list.html',
                           role_perms=role_perms,
                           perm_map=PERMISSION_MAP,
                           role_list=role_list,
                           role_meta=role_meta)


@login_required
def ai_config_page():
    configs = AIConfig.query.order_by(AIConfig.id.desc()).all()
    return render_template('ai_config/list.html', configs=configs)


@login_required
@admin_required
def ai_config_delete(id):
    AIConfig.query.filter_by(id=id).delete()
    db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('ai_config_page'))


# /dashboard/reports 路由已删除（与运维管理 /reports 重复，且本路由是空壳）
# 旧链接重定向到统一的 /reports
