# -*- coding: utf-8 -*-
"""故障管理 CRUD + 故障类型 CRUD"""
import os
from flask import (render_template, request, redirect, url_for,
                   flash, send_from_directory, jsonify, current_app)
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from models import (Fault, Ticket,
                    FaultType, Customer, db)
from utils.pagination import paginate, paginate_render_args
from utils.permission import require_permission
from services.fault_service import (create_fault, update_fault)
from blueprints.ops import ops_bp


# ============================ 故障管理 ============================
@ops_bp.route('/faults')
@login_required
@require_permission('fault:view')
def fault_list():
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    query = Fault.query
    if search:
        query = query.filter(Fault.title.contains(search))
    if status:
        query = query.filter(Fault.result == status)
    query = query.order_by(Fault.fault_time.desc())
    pag = paginate(query, page=page)
    return render_template('faults/list.html', **paginate_render_args(pag),
                           search=search, status=status)


@ops_bp.route('/faults/add', methods=['GET', 'POST'])
@login_required
@require_permission('fault:add')
def fault_add():
    if request.method == 'POST':
        try:
            create_fault(request.form.to_dict(), current_user.realname or current_user.username)
        except Exception as e:
            db.session.rollback()
            flash(str(e) or '故障添加失败', 'danger')
            return redirect(url_for('ops.fault_add'))
        flash('故障记录已添加', 'success')
        return redirect(url_for('ops.fault_list'))
    return render_template('faults/form.html', fault=None,
                           customers=Customer.query.order_by(Customer.name).all(),
                           fault_types=FaultType.query.order_by(FaultType.sort_order, FaultType.id).all())


@ops_bp.route('/faults/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@require_permission('fault:edit')
def fault_edit(id):
    f = Fault.query.get_or_404(id)
    if request.method == 'POST':
        try:
            update_fault(id, request.form.to_dict())
        except Exception as e:
            db.session.rollback()
            flash(str(e) or '故障更新失败', 'danger')
            return redirect(url_for('ops.fault_edit', id=id))
        flash('故障记录已更新', 'success')
        return redirect(url_for('ops.fault_list'))
    return render_template('faults/form.html', fault=f,
                           customers=Customer.query.order_by(Customer.name).all(),
                           fault_types=FaultType.query.order_by(FaultType.sort_order, FaultType.id).all())


@ops_bp.route('/faults/<int:id>')
@login_required
@require_permission('fault:view')
def fault_detail(id):
    f = Fault.query.get_or_404(id)
    related_ticket = Ticket.query.get(f.ticket_id) if f.ticket_id else None
    return render_template('faults/detail.html', fault=f, related_ticket=related_ticket)


@ops_bp.route('/faults/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('fault:delete')
def fault_delete(id):
    from services.fault_service import delete_fault
    try:
        delete_fault(id)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '删除失败', 'danger')
        return redirect(url_for('ops.fault_list'))
    flash('已删除', 'success')
    return redirect(url_for('ops.fault_list'))


@ops_bp.route('/faults/export')
@login_required
@require_permission('fault:view')
def fault_export():
    # 统一走 utils.excel_export；joinedload 消除逐行 customer N+1
    from datetime import date
    from utils.excel_export import export_xlsx
    rows = [[f.title, f.customer_rel.name if f.customer_rel else '-', f.handler or '',
             f.fault_time.strftime('%Y-%m-%d %H:%M') if f.fault_time else '',
             f.result or '']
            for f in Fault.query.options(joinedload(Fault.customer_rel))
            .order_by(Fault.id.desc()).all()]
    path, download_name = export_xlsx(
        ['标题', '客户', '处理人', '故障时间', '结果'], rows,
        f'故障导出_{date.today().isoformat()}.xlsx', sheet_name='故障记录')
    return send_from_directory(os.path.dirname(path), os.path.basename(path),
                               as_attachment=True, download_name=download_name)


# ============================ 故障类型 ============================
@ops_bp.route('/fault-types')
@login_required
@require_permission('fault:view')
def fault_type_list():
    types = FaultType.query.order_by(FaultType.sort_order, FaultType.id).all()
    return render_template('fault_types/list.html', types=types) if os.path.exists('templates/fault_types/list.html') \
        else (jsonify([{'id': t.id, 'name': t.name, 'sort_order': t.sort_order} for t in types]))


# ============================ 故障类型 (CRUD) ============================
@ops_bp.route('/fault-types/add', methods=['POST'])
@login_required
@require_permission('fault:edit')
def fault_type_add():
    name = (request.form.get('name') or '').strip()
    if name:
        t = FaultType(name=name, sort_order=int(request.form.get('sort_order') or 0))
        db.session.add(t); db.session.commit()
        flash('已添加', 'success')
    return redirect(url_for('ops.fault_type_list'))


@ops_bp.route('/fault-types/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('fault:delete')
def fault_type_delete(id):
    FaultType.query.filter_by(id=id).delete()
    db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('ops.fault_type_list'))


