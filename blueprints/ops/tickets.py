# -*- coding: utf-8 -*-
"""工单管理 CRUD + 状态机动作 + 归档为故障案例"""
from flask import (render_template, request, redirect, url_for,
                   flash, current_app)
from flask_login import login_required, current_user
from models import (Ticket,
                    TicketLog, KnowledgeBase, FaultType, Customer, Device, db)
from utils.pagination import paginate, paginate_render_args
from utils.permission import require_permission
from services.ticket_service import (create_ticket, update_ticket, assign_ticket,
                                      accept_ticket, submit_ticket, audit_ticket,
                                      accept_check_ticket, close_ticket)
from blueprints.ops import ops_bp


# ============================ 工单管理 ============================
@ops_bp.route('/tickets')
@login_required
@require_permission('ticket:view')
def ticket_list():
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    query = Ticket.query
    if search:
        query = query.filter(Ticket.title.contains(search))
    if status:
        query = query.filter(Ticket.status == status)
    query = query.order_by(Ticket.id.desc())
    pag = paginate(query, page=page)
    return render_template('tickets/list.html', **paginate_render_args(pag),
                           search=search, status=status)


@ops_bp.route('/tickets/add', methods=['GET', 'POST'])
@login_required
@require_permission('ticket:add')
def ticket_add():
    if request.method == 'POST':
        try:
            t = create_ticket(request.form.to_dict(),
                              current_user.realname or current_user.username)
        except Exception as e:
            db.session.rollback()
            flash(str(e) or '工单创建失败', 'danger')
            return redirect(url_for('ops.ticket_add'))
        flash(f'工单 {t.number} 已创建', 'success')
        return redirect(url_for('ops.ticket_list'))
    return render_template('tickets/form.html', ticket=None,
                           customers=Customer.query.order_by(Customer.name).all(),
                           fault_types=FaultType.query.order_by(FaultType.sort_order, FaultType.id).all(),
                           devices=Device.query.filter_by(is_in_use=True).order_by(Device.device_name).all())


@ops_bp.route('/tickets/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@require_permission('ticket:edit')
def ticket_edit(id):
    t = Ticket.query.get_or_404(id)
    if request.method == 'POST':
        try:
            update_ticket(id, request.form.to_dict(),
                          current_user.realname or current_user.username)
        except Exception as e:
            db.session.rollback()
            flash(str(e) or '工单更新失败', 'danger')
            return redirect(url_for('ops.ticket_edit', id=id))
        flash('工单已更新', 'success')
        return redirect(url_for('ops.ticket_list'))
    return render_template('tickets/form.html', ticket=t,
                           customers=Customer.query.order_by(Customer.name).all(),
                           fault_types=FaultType.query.order_by(FaultType.sort_order, FaultType.id).all(),
                           devices=Device.query.filter_by(is_in_use=True).order_by(Device.device_name).all())


@ops_bp.route('/tickets/<int:id>')
@login_required
@require_permission('ticket:view')
def ticket_detail(id):
    t = Ticket.query.get_or_404(id)
    logs = TicketLog.query.filter_by(ticket_id=id).order_by(TicketLog.id.desc()).all()
    # V13: 派单从下拉改为文本输入；提供近期派过的姓名作为 datalist 提示
    suggested = [r[0] for r in db.session.query(Ticket.assigned_to)
                 .filter(Ticket.assigned_to != '')
                 .distinct().order_by(Ticket.id.desc()).limit(20).all() if r[0]]
    return render_template('tickets/detail.html', ticket=t, logs=logs,
                           suggested_assignees=suggested)


@ops_bp.route('/tickets/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('ticket:delete')
def ticket_delete(id):
    TicketLog.query.filter_by(ticket_id=id).delete()
    Ticket.query.filter_by(id=id).delete()
    db.session.commit()
    flash('工单已删除', 'success')
    return redirect(url_for('ops.ticket_list'))


# 工单状态流转
@ops_bp.route('/tickets/<int:id>/assign', methods=['POST'])
@login_required
@require_permission('ticket:edit')
def ticket_assign(id):
    try:
        assign_ticket(id, request.form.get('assignee', ''),
                      current_user.realname or current_user.username,
                      request.form.get('remark', ''))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '派单失败', 'danger')
    return redirect(url_for('ops.ticket_detail', id=id))


@ops_bp.route('/tickets/<int:id>/accept', methods=['POST'])
@login_required
@require_permission('ticket:edit')
def ticket_accept(id):
    try:
        accept_ticket(id, current_user.realname or current_user.username)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '接单失败', 'danger')
    return redirect(url_for('ops.ticket_detail', id=id))


@ops_bp.route('/tickets/<int:id>/submit', methods=['POST'])
@login_required
@require_permission('ticket:edit')
def ticket_submit(id):
    try:
        submit_ticket(id, current_user.realname or current_user.username,
                      request.form.get('remark', ''),
                      diagnosis=request.form.get('diagnosis', ''),
                      solution=request.form.get('solution', ''))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '提交失败', 'danger')
    return redirect(url_for('ops.ticket_detail', id=id))


@ops_bp.route('/tickets/<int:id>/audit', methods=['POST'])
@login_required
@require_permission('ticket:edit')
def ticket_audit(id):
    approved = request.form.get('action') == '通过'
    try:
        audit_ticket(id, approved, current_user.realname or current_user.username,
                     request.form.get('comment', ''))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '审核失败', 'danger')
    return redirect(url_for('ops.ticket_detail', id=id))


@ops_bp.route('/tickets/<int:id>/accept-check', methods=['POST'])
@login_required
@require_permission('ticket:edit')
def ticket_accept_check(id):
    approved = request.form.get('action') == '通过'
    try:
        accept_check_ticket(id, current_user.realname or current_user.username,
                            request.form.get('comment', ''), approved=approved)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '验收失败', 'danger')
    return redirect(url_for('ops.ticket_detail', id=id))


@ops_bp.route('/tickets/<int:id>/close', methods=['POST'])
@login_required
@require_permission('ticket:edit')
def ticket_close(id):
    try:
        close_ticket(id, current_user.realname or current_user.username,
                     request.form.get('remark', ''))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '关闭失败', 'danger')
    return redirect(url_for('ops.ticket_detail', id=id))


# ============== V7 工单归档为故障案例 ==============
@ops_bp.route('/tickets/<int:id>/archive-as-case', methods=['POST'])
@login_required
@require_permission('kb:add')
def ticket_archive_as_case(id):
    t = Ticket.query.get_or_404(id)
    if t.status not in ('已关闭', '已验收', '已完成'):
        flash(f'仅已关闭/已验收/已完成工单可归档（当前状态：{t.status}）', 'danger')
        return redirect(url_for('ops.ticket_detail', id=id))
    # 构造 Markdown 内容
    content_parts = []
    if t.diagnosis:
        content_parts.append(f'## 诊断分析\n\n{t.diagnosis}\n')
    if t.solution:
        content_parts.append(f'## 解决方案\n\n{t.solution}\n')
    if t.description:
        content_parts.append(f'## 故障描述\n\n{t.description}\n')
    if t.fault_category_level1:
        rc = []
        rc.append(f'一级分类：{t.fault_category_level1}')
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
    kb = KnowledgeBase(
        title=f'【案例】{t.title}',
        category='故障处置',
        content=content,
        related_ticket_id=t.id,
        related_device_type='',
        tags=','.join(tags),
        created_by=current_user.realname or current_user.username,
    )
    db.session.add(kb); db.session.commit()
    flash(f'工单 #{t.number} 已归档为知识库案例 #{kb.id}', 'success')
    return redirect(url_for('ops.knowledge_base_detail', id=kb.id))


