# -*- coding: utf-8 -*-
"""巡检人员管理"""
from flask import (render_template, request, redirect, url_for,
                   flash)
from flask_login import login_required
from models import (Inspector, db)
from utils.permission import require_permission
from blueprints.ops import ops_bp


# ============================ 巡检人员 ============================
@ops_bp.route('/inspectors')
@login_required
@require_permission('inspection:view')
def inspector_list():
    """V13: 巡检人员退化为 User 关联 — 只显示已勾选为巡检人员的用户。"""
    from models import User as UserM
    from sqlalchemy import select
    inspectors = Inspector.query.order_by(Inspector.id.desc()).all()
    # 可勾选为巡检人员的候选 User：active 且尚未被关联
    linked_uids = select(Inspector.user_id)
    available = UserM.query.filter(
        UserM.is_active == True,
        UserM.role.in_(['operator', 'admin']),
        ~UserM.id.in_(linked_uids),
    ).order_by(UserM.realname).all()
    return render_template('inspectors/list.html', inspectors=inspectors, available_users=available)


@ops_bp.route('/inspectors/add', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def inspector_add():
    """V13: 仅勾选 user_id + remark；姓名/手机/邮箱/证书全在用户管理维护。"""
    from models import User as UserM
    user_id = request.form.get('user_id', type=int)
    if not user_id:
        flash('请选择用户', 'danger')
        return redirect(url_for('ops.inspector_list'))
    u = UserM.query.get(user_id)
    if not u:
        flash('用户不存在', 'danger')
        return redirect(url_for('ops.inspector_list'))
    if Inspector.query.filter_by(user_id=user_id).first():
        flash(f'用户 {u.realname or u.username} 已是巡检人员', 'warning')
        return redirect(url_for('ops.inspector_list'))
    i = Inspector(user_id=user_id,
                  remark=request.form.get('remark', ''),
                  is_active=True)
    db.session.add(i)
    db.session.commit()
    flash(f'巡检人员 {u.realname or u.username} 已添加', 'success')
    return redirect(url_for('ops.inspector_list'))


@ops_bp.route('/inspectors/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def inspector_edit(id):
    """V13: 仅可改 is_active / remark；要换人请先删再加。"""
    i = Inspector.query.get_or_404(id)
    i.remark = request.form.get('remark', '')
    i.is_active = bool(request.form.get('is_active'))
    db.session.commit()
    flash('已更新', 'success')
    return redirect(url_for('ops.inspector_list'))


@ops_bp.route('/inspectors/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('inspection:delete')
def inspector_delete(id):
    i = Inspector.query.get_or_404(id)
    db.session.delete(i)
    db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('ops.inspector_list'))


