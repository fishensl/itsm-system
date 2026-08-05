# -*- coding: utf-8 -*-
"""巡检记录：列表/增改/详情/审核/删除/导出"""
import os
from flask import (render_template, request, redirect, url_for,
                   flash, send_from_directory, current_app, jsonify)
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from models import (Inspection, Inspector, Customer, Device,
                    InspectionDeviceTemplate, InspectionTaskTemplate, db)
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
    task_templates = InspectionTaskTemplate.query.filter_by(is_active=True)\
        .order_by(InspectionTaskTemplate.name).all()
    from models import InspectionTask
    tasks = InspectionTask.query.order_by(InspectionTask.id.desc()).limit(300).all()
    return render_template('inspections/form.html', inspection=None, inspectors=inspectors,
                           task_templates=task_templates, tasks=tasks,
                           customers=Customer.query.order_by(Customer.name).all(),
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
    task_templates = InspectionTaskTemplate.query.filter_by(is_active=True)\
        .order_by(InspectionTaskTemplate.name).all()
    from models import InspectionTask
    tasks = InspectionTask.query.order_by(InspectionTask.id.desc()).limit(300).all()
    return render_template('inspections/form.html', inspection=i, inspectors=inspectors,
                           task_templates=task_templates, tasks=tasks,
                           customers=Customer.query.order_by(Customer.name).all())


@ops_bp.route('/inspections/<int:id>')
@login_required
@require_permission('inspection:view')
def inspection_detail(id):
    from models import SubmissionVersion
    i = Inspection.query.get_or_404(id)
    versions = (SubmissionVersion.query
                .filter_by(entity_type='inspection', entity_id=i.id)
                .order_by(SubmissionVersion.version_no.asc()).all())
    return render_template('inspections/detail.html', inspection=i, versions=versions)


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
@require_permission('inspection:review')
def inspection_review(id):
    approved = request.form.get('approved') == '1'
    remark = request.form.get('remark', '')
    requirements = request.form.get('requirements', '')
    try:
        review_inspection(id, approved, current_user.realname or current_user.username,
                          remark, requirements)
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


@ops_bp.route('/api/customers/<int:cid>/devices-with-templates')
@login_required
@require_permission('inspection:view')
def api_devices_with_templates(cid):
    """客户设备 + 匹配的检查模板检查项（新模板体系 InspectionDeviceTemplate 标准化检查项）。

    - 默认模式：按 device_type 自动匹配同 device_category 的启用设备检查模板
    - ?task_template_id=<id>：用该任务模板关联的设备检查模板（task_device_template_link
      排序）驱动——新建巡检选择任务模板快速创建的支撑端点
    响应 items 为 get_normalized_items()（含 sub_items），前端直接渲染，无需二次请求。
    """
    Customer.query.get_or_404(cid)
    task_template_id = request.args.get('task_template_id', type=int)

    devices = Device.query.filter_by(customer_id=cid, is_in_use=True)\
        .order_by(Device.device_type, Device.id).all()

    # 模板池
    tt = None
    if task_template_id:
        tt = InspectionTaskTemplate.query.get(task_template_id)
        pool = tt.get_ordered_device_templates() if tt else []
    else:
        pool = InspectionDeviceTemplate.query.filter_by(is_active=True)\
            .order_by(InspectionDeviceTemplate.id).all()

    def _match(dev):
        """返回 (模板, match_type)；任务模板模式优先精确，再兜底'其他/通用'类模板"""
        dtype = (dev.device_type or '').strip()
        for t in pool:
            if (t.device_category or '').strip() == dtype and dtype:
                return t, 'task_template' if tt else 'device_type'
        for t in pool:
            if (t.device_category or '').strip() in ('其他', '通用'):
                return t, 'fallback'
        return None, 'none'

    out = []
    for d in devices:
        tpl, mtype = _match(d)
        items = tpl.get_normalized_items() if tpl else []
        out.append({
            'device_id': d.id,
            'device_name': d.device_name,
            'device_type': d.device_type or '',
            'location': d.location or '',
            'model': d.model or '',
            'brand': d.brand or '',
            'ip_address': d.ip_address or '',
            'os_version': d.os_version or '',
            'matched_template_id': tpl.id if tpl else None,
            'matched_template_name': tpl.name if tpl else '未匹配',
            'matched_template_category': (tpl.device_category or '其他') if tpl else '其他',
            'match_type': mtype,
            'items': items,
        })

    resp = {'devices': out, 'task_template': None}
    if tt:
        resp['task_template'] = {
            'id': tt.id, 'name': tt.name, 'category': tt.category or '',
            'sections_json': tt.sections_json or '{}',
        }
    return jsonify(resp)


@ops_bp.route('/inspections/export')
@login_required
@require_permission('inspection:view')
def inspection_export():
    """巡检记录导出 Excel（?customer_id=&date_from=&date_to= 按客户/时间段筛选）"""
    from datetime import date
    from utils.excel_export import export_xlsx
    rows = _inspection_export_rows(request.args)
    path, download_name = export_xlsx(
        ['标题', '客户', '巡检员', '巡检日期', '总体状态', '审核状态', '现场报告',
         '正式报告', '审核意见', '结论', '资料完整'], rows,
        f'巡检导出_{date.today().isoformat()}.xlsx', sheet_name='巡检记录')
    return send_from_directory(os.path.dirname(path), os.path.basename(path),
                               as_attachment=True, download_name=download_name)


@ops_bp.route('/inspections/reports-zip')
@login_required
@require_permission('inspection:view')
def inspection_reports_zip():
    """巡检记录+报告文件打包下载（按客户/时间段筛选）"""
    from datetime import date
    from utils.excel_export import export_xlsx
    from utils.report_zip import build_records_zip
    from flask import send_file
    from models import SubmissionVersion, InspectionTask
    from services.inspection_service import inspection_completeness

    q = _inspection_export_query(request.args)
    records = q.options(joinedload(Inspection.customer_rel)).all()
    if not records:
        flash('当前筛选条件下没有可导出的巡检记录', 'warning')
        return redirect(request.referrer or url_for('ops.inspection_list'))

    headers = ['标题', '客户', '巡检员', '巡检日期', '总体状态', '审核状态', '现场报告',
               '正式报告', '审核意见', '结论', '资料完整']
    rows = []
    files = []
    task_ids = {r.task_id for r in records if r.task_id}
    task_map = {t.id: t.title for t in InspectionTask.query.filter(InspectionTask.id.in_(task_ids)).all()} if task_ids else {}
    for i in records:
        cust = i.customer_rel.name if i.customer_rel else '未知客户'
        versions = SubmissionVersion.query \
            .filter_by(entity_type='inspection', entity_id=i.id) \
            .order_by(SubmissionVersion.version_no.asc()).all()
        for v in versions:
            if v.report_file:
                full = os.path.realpath(os.path.join('static', v.report_file))
                if os.path.isfile(full):
                    fname = os.path.basename(v.report_file)
                    files.append((full, f'{cust}/巡检{i.id}_{task_map.get(i.task_id, "")[:30]}/v{v.version_no}_{fname}'))
        if i.report_file:
            full = os.path.realpath(os.path.join('reports', i.report_file))
            if os.path.isfile(full):
                files.append((full, f'{cust}/巡检{i.id}_{task_map.get(i.task_id, "")[:30]}/正式报告_{i.report_file}'))
        complete, missing = inspection_completeness(i)
        rows.append([
            i.title, cust, i.inspector_name or i.inspector or '',
            i.inspection_date.isoformat() if i.inspection_date else '',
            i.overall_status or '', i.review_status or '草稿',
            '有' if i.submitted_report else '无',
            '有' if i.report_file else '无',
            i.review_comment or '', i.conclusion or '',
            '完整' if complete else '缺失:' + '、'.join(missing),
        ])
    excel_path, _ = export_xlsx(headers, rows, '巡检明细.xlsx', sheet_name='巡检记录')
    zip_path = build_records_zip(excel_path, files, '巡检报告包')
    return send_file(zip_path, as_attachment=True,
                     download_name=f'巡检报告包_{date.today().isoformat()}.zip')


def _inspection_export_query(args):
    """解析导出筛选参数 → 巡检记录 query"""
    from datetime import date as _date
    q = Inspection.query
    customer_id = args.get('customer_id', type=int)
    date_from = args.get('date_from') or ''
    date_to = args.get('date_to') or ''
    if customer_id:
        q = q.filter(Inspection.customer_id == customer_id)
    if date_from:
        try:
            q = q.filter(Inspection.inspection_date >= _date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(Inspection.inspection_date <= _date.fromisoformat(date_to))
        except ValueError:
            pass
    return q


def _inspection_export_rows(args):
    """按筛选参数导出巡检记录行（列表/报告包共用）"""
    from services.inspection_service import inspection_completeness
    records = _inspection_export_query(args) \
        .options(joinedload(Inspection.customer_rel)) \
        .order_by(Inspection.inspection_date.desc(), Inspection.id.desc()).all()
    rows = []
    for i in records:
        cust = i.customer_rel.name if i.customer_rel else '-'
        complete, missing = inspection_completeness(i)
        rows.append([
            i.title, cust, i.inspector_name or i.inspector or '',
            i.inspection_date.isoformat() if i.inspection_date else '',
            i.overall_status or '', i.review_status or '草稿',
            '有' if i.submitted_report else '无',
            '有' if i.report_file else '无',
            i.review_comment or '', i.conclusion or '',
            '完整' if complete else '缺失:' + '、'.join(missing),
        ])
    return rows


