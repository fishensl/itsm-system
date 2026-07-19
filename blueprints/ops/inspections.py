# -*- coding: utf-8 -*-
"""巡检记录：列表/增改/详情/审核/删除/导出"""
import os
from flask import (render_template, request, redirect, url_for,
                   flash, send_from_directory, current_app)
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from models import (Inspection, Inspector, db)
from utils.pagination import paginate, paginate_render_args
from utils.permission import require_permission
from services.inspection_service import (create_inspection, update_inspection,
                                          submit_for_review, review_inspection)
from blueprints.ops import ops_bp


# ============================ 巡检记录 ============================
@ops_bp.route('/inspections')
@login_required
@require_permission('inspection:view')
def inspection_list():
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    query = Inspection.query
    if search:
        query = query.filter(Inspection.title.contains(search))
    if status:
        query = query.filter(Inspection.overall_status == status)
    # 预加载 customer_rel 避免 N+1
    from sqlalchemy.orm import joinedload
    query = query.options(joinedload(Inspection.customer_rel))
    query = query.order_by(Inspection.inspection_date.desc())
    pag = paginate(query, page=page)
    return render_template('inspections/list.html', **paginate_render_args(pag), search=search, status=status)


@ops_bp.route('/inspections/add', methods=['GET', 'POST'])
@login_required
@require_permission('inspection:add')
def inspection_add():
    if request.method == 'POST':
        try:
            create_inspection(request.form.to_dict(), current_user.realname or current_user.username)
        except Exception as e:
            db.session.rollback()
            flash(str(e) or '巡检添加失败', 'danger')
            return redirect(url_for('ops.inspection_add'))
        flash('巡检记录已添加', 'success')
        return redirect(url_for('ops.inspection_list'))
    inspectors = Inspector.query.filter_by(is_active=True).order_by(Inspector.id).all()
    return render_template('inspections/form.html', inspection=None, inspectors=inspectors,
                           preselected_task_id=request.args.get('task_id', type=int),
                           preselected_customer_id=request.args.get('customer_id', type=int))


@ops_bp.route('/inspections/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@require_permission('inspection:edit')
def inspection_edit(id):
    i = Inspection.query.get_or_404(id)
    if request.method == 'POST':
        try:
            update_inspection(id, request.form.to_dict())
        except Exception as e:
            db.session.rollback()
            flash(str(e) or '巡检更新失败', 'danger')
            return redirect(url_for('ops.inspection_edit', id=id))
        flash('巡检记录已更新', 'success')
        return redirect(url_for('ops.inspection_list'))
    inspectors = Inspector.query.filter_by(is_active=True).order_by(Inspector.id).all()
    return render_template('inspections/form.html', inspection=i, inspectors=inspectors)


@ops_bp.route('/inspections/<int:id>')
@login_required
@require_permission('inspection:view')
def inspection_detail(id):
    i = Inspection.query.get_or_404(id)
    return render_template('inspections/detail.html', inspection=i)


@ops_bp.route('/inspections/<int:id>/submit', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def inspection_submit(id):
    try:
        submit_for_review(id, current_user.realname or current_user.username)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '操作失败', 'danger')
    return redirect(url_for('ops.inspection_detail', id=id))


@ops_bp.route('/inspections/<int:id>/review', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def inspection_review(id):
    approved = request.form.get('approved') == '1'
    remark = request.form.get('remark', '')
    try:
        review_inspection(id, approved, current_user.realname or current_user.username, remark)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '审核失败', 'danger')
    return redirect(url_for('ops.inspection_detail', id=id))


@ops_bp.route('/inspections/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('inspection:delete')
def inspection_delete(id):
    from services.inspection_service import delete_inspection
    try:
        delete_inspection(id)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '删除失败', 'danger')
        return redirect(url_for('ops.inspection_list'))
    flash('已删除', 'success')
    return redirect(url_for('ops.inspection_list'))


@ops_bp.route('/inspections/export')
@login_required
@require_permission('inspection:view')
def inspection_export():
    # 统一走 utils.excel_export；joinedload 消除逐行 customer_rel N+1
    from datetime import date
    from utils.excel_export import export_xlsx
    rows = [[i.title, i.customer_rel.name if i.customer_rel else '-', i.inspector,
             i.inspection_date.isoformat() if i.inspection_date else '',
             i.overall_status or '', i.conclusion or '']
            for i in Inspection.query.options(joinedload(Inspection.customer_rel))
            .order_by(Inspection.id.desc()).all()]
    path, download_name = export_xlsx(
        ['标题', '客户', '巡检员', '巡检日期', '结果', '结论'], rows,
        f'巡检导出_{date.today().isoformat()}.xlsx', sheet_name='巡检记录')
    return send_from_directory(os.path.dirname(path), os.path.basename(path),
                               as_attachment=True, download_name=download_name)


