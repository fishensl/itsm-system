# -*- coding: utf-8 -*-
"""运维管理蓝图：巡检/工单/故障/知识库/报表

所有业务规则下沉到 services/，路由层只做参数接收和模板渲染。
"""
import os
from datetime import datetime, timedelta
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, send_from_directory, jsonify, current_app, abort, session)
from flask_login import login_required, current_user
from sqlalchemy import text as sa_text
from sqlalchemy.orm import joinedload
from models import (Inspection, InspectionTemplate, Fault, Ticket,
                    TicketLog, KnowledgeBase, KnowledgeAttachment, Inspector, InspectionDeviceTemplate,
                    InspectionTaskTemplate, FaultType, Customer, Device, db)
from utils.pagination import paginate, paginate_render_args
from utils.permission import require_permission
from utils.customer_task_generator import QUARTER_CN
from services.ticket_service import (create_ticket, update_ticket, assign_ticket,
                                      accept_ticket, submit_ticket, audit_ticket,
                                      accept_check_ticket, close_ticket)
from services.inspection_service import (create_inspection, update_inspection,
                                          submit_for_review, review_inspection)
from services.fault_service import (create_fault, update_fault)

ops_bp = Blueprint('ops', __name__)


# V7 知识库附件保存目录（目录由 create_app 的 _ensure_runtime_dirs 统一创建，消除导入副作用）
KB_ATTACH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'static', 'uploads', 'knowledge')
ALLOWED_KB_EXTS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx',
                   '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.txt'}


def _save_kb_attachments(files, kb_id, uploader):
    """保存知识库多个附件，返回 [(file_name, file_path, ext, size), ...]"""
    saved = []
    if not files:
        return saved
    sub_dir = os.path.join(KB_ATTACH_DIR, str(kb_id))
    os.makedirs(sub_dir, exist_ok=True)
    import uuid as _uuid
    for f in files:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_KB_EXTS:
            continue
        safe_name = f'{_uuid.uuid4().hex}{ext}'
        full = os.path.join(sub_dir, safe_name)
        f.save(full)
        rel_path = f'uploads/knowledge/{kb_id}/{safe_name}'
        size = os.path.getsize(full)
        saved.append((f.filename, rel_path, ext, size))
    return saved


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


# ============================ 巡检任务（V18: 已并入 task_schedule，仅保留 URL 301 兼容） ============================
@ops_bp.route('/inspection-tasks')
@login_required
def inspection_task_list():
    """老列表 → 任务安排列表视图"""
    return redirect(url_for('task_schedule.list_view', **request.args), code=301)


@ops_bp.route('/inspection-tasks/<int:id>')
@login_required
def inspection_task_detail(id):
    """老详情 → task_schedule.task_detail"""
    return redirect(url_for('task_schedule.task_detail', task_id=id), code=301)


# ============================ 巡检模板 ============================
@ops_bp.route('/inspection-templates')
@login_required
@require_permission('inspection:view')
def inspection_template_list():
    from models import DeviceType
    templates = InspectionTemplate.query.order_by(InspectionTemplate.id.desc()).all()
    device_types = DeviceType.query.order_by(DeviceType.sort_order, DeviceType.id).all()
    return render_template('inspection_templates/list.html',
                           templates=templates, device_types=device_types)


@ops_bp.route('/api/inspection-templates', methods=['GET'])
@login_required
@require_permission('inspection:view')
def api_inspection_templates():
    """供编辑弹窗和巡检表单引用：返回所有巡检模板的完整 V11 字段。"""
    import json
    out = []
    for t in InspectionTemplate.query.order_by(InspectionTemplate.id.desc()).all():
        try:
            items = json.loads(t.items_json or '[]')
        except Exception:
            items = []
        out.append({
            'id': t.id,
            'name': t.name,
            'device_type': t.device_type or '',
            'device_model': t.device_model or '',
            'template_category': t.template_category or '',
            'report_section_name': t.report_section_name or '',
            'is_active': bool(t.is_active),
            'items': items,
        })
    return jsonify(out)


# ============================ 设备检查模板 ============================
@ops_bp.route('/device-check-templates')
@login_required
@require_permission('inspection:view')
def device_check_template_list():
    from collections import OrderedDict
    templates = InspectionDeviceTemplate.query.order_by(
        InspectionDeviceTemplate.device_category, InspectionDeviceTemplate.id).all()
    cat_order = ['服务器', '网络设备', '安全设备', '环控设备', '会议设备', '空调', 'UPS', '存储设备', '其他']
    grouped = OrderedDict()
    for t in templates:
        cat = t.device_category or '其他'
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(t)
    sorted_grouped = OrderedDict()
    for cat in cat_order:
        if cat in grouped:
            sorted_grouped[cat] = grouped[cat]
    return render_template('device_check_templates/list.html',
                           templates=templates, grouped=sorted_grouped)


# ============================ 任务模板 ============================
@ops_bp.route('/task-templates')
@login_required
@require_permission('inspection:view')
def task_template_list():
    templates = InspectionTaskTemplate.query.order_by(InspectionTaskTemplate.id.desc()).all()
    device_templates = InspectionDeviceTemplate.query.filter_by(is_active=True).order_by(
        InspectionDeviceTemplate.device_category, InspectionDeviceTemplate.id).all()
    customers = Customer.query.order_by(Customer.name).all()
    return render_template('task_templates/list.html',
                           templates=templates, device_templates=device_templates,
                           customers=customers)


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


# ============================ 知识库 ============================
@ops_bp.route('/knowledge-base')
@login_required
@require_permission('kb:view')
def knowledge_base_list():
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    page = request.args.get('page', 1, type=int)
    query = KnowledgeBase.query
    if search:
        query = query.filter(KnowledgeBase.title.contains(search) | KnowledgeBase.content.contains(search))
    if category:
        query = query.filter(KnowledgeBase.category == category)
    query = query.order_by(KnowledgeBase.id.desc())
    pag = paginate(query, page=page)
    return render_template('knowledge_base/list.html', **paginate_render_args(pag),
                           search=search, category=category)


@ops_bp.route('/knowledge-base/add', methods=['GET', 'POST'])
@login_required
@require_permission('kb:add')
def knowledge_base_add():
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        if not title:
            flash('标题不能为空', 'danger')
            return redirect(url_for('ops.knowledge_base_add'))
        kb = KnowledgeBase(
            title=title,
            category=request.form.get('category', '其他'),
            content=request.form.get('content', ''),
            tags=request.form.get('tags', ''),
            related_device_type=request.form.get('related_device_type', ''),
            related_ticket_id=int(request.form['related_ticket_id']) if request.form.get('related_ticket_id') else None,
            related_fault_id=int(request.form['related_fault_id']) if request.form.get('related_fault_id') else None,
            is_published=bool(request.form.get('is_published')),
            created_by=current_user.realname or current_user.username,
        )
        db.session.add(kb); db.session.commit()
        # V7：保存附件
        files = request.files.getlist('attachments')
        for fname, fpath, ext, size in _save_kb_attachments(files, kb.id,
                                                             current_user.realname or current_user.username):
            db.session.add(KnowledgeAttachment(
                knowledge_id=kb.id, file_name=fname, file_path=fpath,
                file_ext=ext, file_size=size,
                uploaded_by=current_user.realname or current_user.username,
            ))
        if files:
            db.session.commit()
        flash('知识条目已添加', 'success')
        return redirect(url_for('ops.knowledge_base_list'))
    return render_template('knowledge_base/form.html', kb=None)


@ops_bp.route('/knowledge-base/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@require_permission('kb:edit')
def knowledge_base_edit(id):
    kb = KnowledgeBase.query.get_or_404(id)
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        if not title:
            flash('标题不能为空', 'danger')
            return redirect(url_for('ops.knowledge_base_edit', id=id))
        kb.title = title
        kb.category = request.form.get('category', kb.category or '其他')
        kb.content = request.form.get('content', '')
        kb.tags = request.form.get('tags', '')
        kb.related_device_type = request.form.get('related_device_type', '')
        kb.is_published = bool(request.form.get('is_published'))
        # V7：追加附件
        files = request.files.getlist('attachments')
        for fname, fpath, ext, size in _save_kb_attachments(files, kb.id,
                                                             current_user.realname or current_user.username):
            db.session.add(KnowledgeAttachment(
                knowledge_id=kb.id, file_name=fname, file_path=fpath,
                file_ext=ext, file_size=size,
                uploaded_by=current_user.realname or current_user.username,
            ))
        db.session.commit()
        flash('知识条目已更新', 'success')
        return redirect(url_for('ops.knowledge_base_list'))
    return render_template('knowledge_base/form.html', kb=kb)


@ops_bp.route('/knowledge-base/<int:id>')
@login_required
@require_permission('kb:view')
def knowledge_base_detail(id):
    kb = KnowledgeBase.query.get_or_404(id)
    # 浏览次数 +1：原子 UPDATE，避免 read-modify-write 并发丢失；session 去重（1 小时内同人重复访问不计）
    viewed_key = f'kb_viewed_{id}'
    if not session.get(viewed_key):
        db.session.execute(
            sa_text('UPDATE knowledge_base SET view_count = COALESCE(view_count, 0) + 1 WHERE id = :kid'),
            {'kid': id})
        db.session.commit()
        session[viewed_key] = True
        kb.view_count = (kb.view_count or 0) + 1  # 页面展示同步
    ticket = Ticket.query.get(kb.related_ticket_id) if kb.related_ticket_id else None
    fault = Fault.query.get(kb.related_fault_id) if kb.related_fault_id else None
    return render_template('knowledge_base/detail.html', kb=kb, ticket=ticket, fault=fault)


@ops_bp.route('/knowledge-base/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('kb:delete')
def knowledge_base_delete(id):
    # V7：先删除物理附件
    kb = KnowledgeBase.query.get_or_404(id)
    for att in kb.attachments:
        full = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'static', att.file_path)
        try:
            if os.path.isfile(full):
                os.remove(full)
        except Exception:
            pass
    db.session.delete(kb)
    db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('ops.knowledge_base_list'))


# ============== V7 知识库附件端点 ==============
@ops_bp.route('/knowledge-base/<int:kb_id>/attachment/<int:att_id>/preview')
@login_required
@require_permission('kb:view')
def knowledge_base_attachment_preview(kb_id, att_id):
    """PDF/图片浏览器内嵌预览"""
    att = KnowledgeAttachment.query.get_or_404(att_id)
    if att.knowledge_id != kb_id:
        abort(404)
    static_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full = os.path.join(static_dir, 'static', att.file_path)
    if not os.path.isfile(full):
        abort(404)
    if att.file_ext in ('.pdf',):
        return send_from_directory(os.path.dirname(full), os.path.basename(full),
                                   mimetype='application/pdf')
    if att.file_ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'):
        # 用 send_file + as_attachment=False 内联
        from flask import send_file
        return send_file(full)
    abort(415)  # 不支持预览的类型


@ops_bp.route('/knowledge-base/<int:kb_id>/attachment/<int:att_id>/download')
@login_required
@require_permission('kb:view')
def knowledge_base_attachment_download(kb_id, att_id):
    att = KnowledgeAttachment.query.get_or_404(att_id)
    if att.knowledge_id != kb_id:
        abort(404)
    static_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_dir = os.path.join(static_dir, 'static', os.path.dirname(att.file_path))
    return send_from_directory(full_dir, os.path.basename(att.file_path),
                               as_attachment=True, download_name=att.file_name)


@ops_bp.route('/knowledge-base/<int:kb_id>/attachment/<int:att_id>/delete', methods=['POST'])
@login_required
@require_permission('kb:edit')
def knowledge_base_attachment_delete(kb_id, att_id):
    att = KnowledgeAttachment.query.get_or_404(att_id)
    if att.knowledge_id != kb_id:
        abort(404)
    static_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full = os.path.join(static_dir, 'static', att.file_path)
    try:
        if os.path.isfile(full):
            os.remove(full)
    except Exception:
        pass
    db.session.delete(att)
    db.session.commit()
    flash('附件已删除', 'success')
    return redirect(url_for('ops.knowledge_base_detail', id=kb_id))


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


# ============================ 故障类型 ============================
@ops_bp.route('/fault-types')
@login_required
@require_permission('fault:view')
def fault_type_list():
    types = FaultType.query.order_by(FaultType.sort_order, FaultType.id).all()
    return render_template('fault_types/list.html', types=types) if os.path.exists('templates/fault_types/list.html') \
        else (jsonify([{'id': t.id, 'name': t.name, 'sort_order': t.sort_order} for t in types]))


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


# ============================ 巡检模板 ============================
@ops_bp.route('/inspection-templates/add', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def inspection_template_add():
    """V11 接续：保存完整 V11 字段（items_json / device_type / device_model /
    template_category / report_section_name / is_active / remark）。"""
    import json
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('模板名称不能为空', 'danger')
        return redirect(url_for('ops.inspection_template_list'))
    items_json_raw = request.form.get('items_json', '[]')
    try:
        json.loads(items_json_raw)
    except Exception:
        items_json_raw = '[]'
    t = InspectionTemplate(
        name=name,
        device_type=request.form.get('device_type', ''),
        device_model=request.form.get('device_model', ''),
        template_category=request.form.get('template_category', '网络设备'),
        report_section_name=request.form.get('report_section_name', ''),
        items_json=items_json_raw,
        is_active=bool(request.form.get('is_active')),
        remark=request.form.get('remark', ''),
    )
    db.session.add(t)
    db.session.commit()
    flash('已添加', 'success')
    return redirect(url_for('ops.inspection_template_list'))


@ops_bp.route('/inspection-templates/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def inspection_template_edit(id):
    """V11 接续：编辑完整 V11 字段。"""
    import json
    t = InspectionTemplate.query.get_or_404(id)
    t.name = (request.form.get('name') or t.name).strip()
    t.device_type = request.form.get('device_type', t.device_type or '')
    t.device_model = request.form.get('device_model', t.device_model or '')
    t.template_category = request.form.get('template_category', t.template_category or '网络设备')
    t.report_section_name = request.form.get('report_section_name', t.report_section_name or '')
    items_json_raw = request.form.get('items_json', t.items_json or '[]')
    try:
        json.loads(items_json_raw)
        t.items_json = items_json_raw
    except Exception:
        pass  # 保留旧值，避免脏数据覆盖
    t.is_active = bool(request.form.get('is_active'))
    t.remark = request.form.get('remark', t.remark or '')
    db.session.commit()
    flash('已更新', 'success')
    return redirect(url_for('ops.inspection_template_list'))


@ops_bp.route('/inspection-templates/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('inspection:delete')
def inspection_template_delete(id):
    InspectionTemplate.query.filter_by(id=id).delete()
    db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('ops.inspection_template_list'))


# ============================ 巡检任务（V18: 兼容 POST 重定向） ============================
@ops_bp.route('/inspection-tasks/add', methods=['POST'])
@login_required
def inspection_task_add():
    """老 add → quick_add（307 保留方法 + body）"""
    return redirect(url_for('task_schedule.quick_add'), code=307)


def _parse_date(s):
    """Helper: 解析 YYYY-MM-DD 字符串为 date，失败返回 None（保留给其他调用方）"""
    if not s:
        return None
    try:
        from datetime import datetime as _dt
        return _dt.strptime(s.strip(), '%Y-%m-%d').date()
    except Exception:
        return None


@ops_bp.route('/inspection-tasks/edit/<int:id>', methods=['POST'])
@login_required
def inspection_task_edit(id):
    """老 edit：仅支持改状态字段（其余字段已迁到任务安排详情页）"""
    new_status = (request.form.get('status') or '').strip()
    if new_status:
        return redirect(
            url_for('task_schedule.change_status_form', task_id=id, status=new_status),
            code=307,
        )
    return redirect(url_for('task_schedule.task_detail', task_id=id))


@ops_bp.route('/inspection-tasks/delete/<int:id>', methods=['POST'])
@login_required
def inspection_task_delete(id):
    """老 delete → task_schedule.delete_task"""
    return redirect(url_for('task_schedule.delete_task', task_id=id), code=307)


# ============================ 设备检查模板 (CRUD) ============================
@ops_bp.route('/device-check-templates/add', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def device_check_template_add():
    import json
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('模板名称不能为空', 'danger')
        return redirect(url_for('ops.device_check_template_list'))
    items_json = request.form.get('items_json', '[]')
    try:
        parsed = json.loads(items_json)
        if not isinstance(parsed, list):
            raise ValueError('items_json must be a list')
    except Exception as e:
        flash(f'检查项 JSON 格式错误: {e}', 'danger')
        current_app.logger.exception("操作失败：%s", repr(e))
        return redirect(url_for('ops.device_check_template_list'))
    t = InspectionDeviceTemplate(
        name=name,
        device_category=request.form.get('device_category', '网络设备'),
        device_sub_type=request.form.get('device_sub_type', ''),
        items_json=items_json,
        remark=request.form.get('remark', ''),
    )
    db.session.add(t); db.session.commit()
    flash('已添加', 'success')
    return redirect(url_for('ops.device_check_template_list'))


@ops_bp.route('/device-check-templates/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def device_check_template_edit(id):
    import json
    t = InspectionDeviceTemplate.query.get_or_404(id)
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('模板名称不能为空', 'danger')
        return redirect(url_for('ops.device_check_template_list'))
    items_json = request.form.get('items_json', '[]')
    try:
        parsed = json.loads(items_json)
        if not isinstance(parsed, list):
            raise ValueError('items_json must be a list')
    except Exception as e:
        flash(f'检查项 JSON 格式错误: {e}', 'danger')
        current_app.logger.exception("操作失败：%s", repr(e))
        return redirect(url_for('ops.device_check_template_list'))
    t.name = name
    t.device_category = request.form.get('device_category', t.device_category)
    t.device_sub_type = request.form.get('device_sub_type', '')
    t.items_json = items_json
    t.remark = request.form.get('remark', '')
    db.session.commit()
    flash('已更新', 'success')
    return redirect(url_for('ops.device_check_template_list'))


@ops_bp.route('/device-check-templates/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('inspection:delete')
def device_check_template_delete(id):
    InspectionDeviceTemplate.query.filter_by(id=id).delete()
    db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('ops.device_check_template_list'))


# ============================ 任务模板 (CRUD) ============================
@ops_bp.route('/task-templates/add', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def task_template_add():
    import json
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('名称不能为空', 'danger')
        return redirect(url_for('ops.task_template_list'))
    sections_json = request.form.get('sections_json', '{}')
    try:
        json.loads(sections_json)
    except Exception:
        sections_json = '{}'
    t = InspectionTaskTemplate(
        name=name,
        category=request.form.get('category', '日常巡检'),
        inspection_type=request.form.get('inspection_type', '月度巡检'),
        frequency=request.form.get('frequency', ''),
        customer_tier=request.form.get('customer_tier', 'all'),
        sections_json=sections_json,
        is_active=True,
        remark=request.form.get('remark', ''),
    )
    db.session.add(t)
    db.session.flush()  # 拿到 id
    _save_task_template_devices(t, request.form)
    db.session.commit()
    flash('已添加', 'success')
    return redirect(url_for('ops.task_template_list'))


@ops_bp.route('/task-templates/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def task_template_edit(id):
    import json
    t = InspectionTaskTemplate.query.get_or_404(id)
    t.name = (request.form.get('name') or t.name).strip()
    t.category = request.form.get('category', t.category)
    t.inspection_type = request.form.get('inspection_type', t.inspection_type)
    t.frequency = request.form.get('frequency', '')
    t.customer_tier = request.form.get('customer_tier', 'all')
    sections_json = request.form.get('sections_json', '{}')
    try:
        json.loads(sections_json)
        t.sections_json = sections_json
    except Exception:
        pass
    t.remark = request.form.get('remark', '')
    _save_task_template_devices(t, request.form)
    db.session.commit()
    flash('已更新', 'success')
    return redirect(url_for('ops.task_template_list'))


def _save_task_template_devices(t, form):
    """V10: 按 device_template_ids_ordered 字段（逗号分隔的设备模板 ID 顺序）保存关联关系
    回退兼容：device_template_ids 多值表单字段。"""
    from models import task_device_template_link
    ordered_csv = (form.get('device_template_ids_ordered') or '').strip()
    if ordered_csv:
        ids = [int(x) for x in ordered_csv.split(',') if x.strip().isdigit()]
    else:
        ids = [int(x) for x in form.getlist('device_template_ids') if str(x).isdigit()]
    # 先用 ORM 清空关联（避免 ORM 跟踪状态错位），再 flush
    t.device_templates = []
    db.session.flush()
    # 按顺序插入（带 sort_order）
    for idx, dt_id in enumerate(ids):
        db.session.execute(task_device_template_link.insert().values(
            task_template_id=t.id, device_template_id=dt_id, sort_order=idx))


# ============================ 任务模板 — 自动匹配 API ============================
@ops_bp.route('/api/customers/<int:cid>/match-device-templates')
@login_required
@require_permission('inspection:view')
def api_match_device_templates(cid):
    """V10: 按客户设备清单自动匹配设备检查模板
    - 查客户所有在用设备 → 按 device_type 大类去重分组
    - 查所有启用的设备检查模板 → 按 device_category 匹配
    - 返回每个大类下的设备数 + 匹配到的模板列表（命中分越高越靠前）
    """
    from collections import defaultdict
    devices = Device.query.filter_by(customer_id=cid, is_in_use=True).all()
    # 按 device_type 分组
    by_cat = defaultdict(list)
    for d in devices:
        cat = (d.device_type or '其他').strip()
        by_cat[cat].append({
            'id': d.id, 'name': d.device_name,
            'brand': d.brand or '', 'model': d.model or '',
            'ip': d.ip_address or '', 'os_version': d.os_version or '',
        })
    # 加载所有设备模板
    all_templates = InspectionDeviceTemplate.query.filter_by(is_active=True).all()
    tpl_by_cat = defaultdict(list)
    for tpl in all_templates:
        tpl_by_cat[tpl.device_category or '其他'].append(tpl)

    out = []
    for cat, dev_list in sorted(by_cat.items()):
        # 同类匹配：device_category 完全一致 (高分) > device_sub_type 子串 (中分)
        candidates = []
        # 高分：device_category 完全等于 cat
        for tpl in tpl_by_cat.get(cat, []):
            candidates.append({
                'id': tpl.id, 'name': tpl.name,
                'category': tpl.device_category, 'sub_type': tpl.device_sub_type or '',
                'items_count': len(tpl.items_json or '[]'),
                'match_score': 100,
            })
        # 中分：其他模板里子类型包含此 cat
        for tpl in all_templates:
            if (tpl.device_category or '') == cat:
                continue
            if cat in (tpl.name or '') or cat in (tpl.device_sub_type or ''):
                candidates.append({
                    'id': tpl.id, 'name': tpl.name,
                    'category': tpl.device_category, 'sub_type': tpl.device_sub_type or '',
                    'items_count': 0,
                    'match_score': 50,
                })
        candidates.sort(key=lambda x: -x['match_score'])
        out.append({
            'device_category': cat,
            'devices_count': len(dev_list),
            'devices': dev_list,
            'matched_templates': candidates,
        })
    return {'groups': out, 'total_devices': len(devices)}


@ops_bp.route('/task-templates/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('inspection:delete')
def task_template_delete(id):
    t = InspectionTaskTemplate.query.get(id)
    if t:
        # 先清空 ORM 跟踪的关联
        t.device_templates = []
        db.session.flush()
        db.session.delete(t)
        db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('ops.task_template_list'))


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


# ============================ 报告 ============================
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reports')


def _safe_report_path(filename):
    """报告文件名安全校验：防路径穿越 + 扩展名白名单。返回绝对路径或 None。"""
    if not filename or not filename.lower().endswith(('.docx', '.pdf')):
        return None
    full = os.path.realpath(os.path.join(REPORTS_DIR, filename))
    base = os.path.realpath(REPORTS_DIR)
    if full.startswith(base + os.sep) and os.path.isfile(full):
        return full
    return None

@ops_bp.route('/reports')
@login_required
@require_permission('report:view')
def report_list():
    """报告管理：客户优先 + 类型徽章，tab 控制展示哪些类型"""
    scope = request.args.get('scope', 'all')               # all/mine
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    customer_id = request.args.get('customer_id', type=int)
    # 统一 tab：'all' / 'inspection' / 'fault' / 'ticket' / 'file'，单变量控制高亮
    valid_tabs = ('all', 'inspection', 'fault', 'ticket', 'file')
    tab = request.args.get('tab', 'all')
    if tab not in valid_tabs:
        tab = 'all'

    me = current_user.realname or current_user.username

    # 性能：首次进入（无任何过滤条件）默认只看近 12 个月，避免三表全量扫描；
    # 用户显式选择日期/客户后按条件查询（客户传 customer_id=0 视为全部）
    default_window = False
    if not date_from and not date_to and not customer_id:
        date_from = (datetime.now().date() - timedelta(days=365)).isoformat()
        default_window = True

    # --- 顶部"客户"下拉（预加载所有客户） ---
    customers_index = {c.id: c for c in Customer.query.order_by(Customer.name).all()}

    def _ensure_cust(cid, cname, unassigned):
        """获取或初始化一个客户桶"""
        if cid not in data:
            data[cid] = {
                'id': cid,
                'name': cname,
                'is_unassigned': unassigned,
                'counts': {'inspection': 0, 'fault': 0, 'ticket': 0, 'file': 0},
                'types': {
                    'inspection': {'subs': {}},
                    'fault':      {'subs': {}},
                    'ticket':     {'subs': {}},
                    'file':       {'files': []},
                }
            }
        return data[cid]

    def _push_record(cid, cname, rt, sub_key, sub_label, item, unassigned=False):
        bucket = _ensure_cust(cid, cname, unassigned)
        bucket['counts'][rt] += 1
        if rt == 'file':
            bucket['types']['file']['files'].append(item)
        else:
            # 键名 items_list 与 reports/list.html 渲染契约一致（曾用 items 导致明细行不渲染）
            sub = bucket['types'][rt]['subs'].setdefault(
                sub_key, {'label': sub_label, 'items_list': []}
            )
            sub['items_list'].append(item)

    data = {}  # customer_id | None -> payload

    # --- 巡检：按季度子分组 ---
    if tab in ('all', 'inspection'):
        q = Inspection.query.options(joinedload(Inspection.customer_rel))
        if date_from:
            q = q.filter(Inspection.inspection_date >= date_from)
        if date_to:
            q = q.filter(Inspection.inspection_date <= date_to)
        if customer_id:
            q = q.filter(Inspection.customer_id == customer_id)
        if scope == 'mine':
            q = q.filter(Inspection.inspector == me)
        for i in q.order_by(Inspection.inspection_date.desc(), Inspection.id.desc()).all():
            cust = i.customer_rel
            if cust is None:
                _push_record(None, '未关联客户', 'inspection', 'unknown', '未知时间', i, unassigned=True)
            else:
                if i.inspection_date:
                    qnum = (i.inspection_date.month - 1) // 3 + 1
                    sub_key = f'{i.inspection_date.year}-Q{qnum}'
                    sub_label = f'{i.inspection_date.year}年第{QUARTER_CN[qnum]}季度'
                else:
                    sub_key, sub_label = 'unknown', '未知时间'
                _push_record(cust.id, cust.name, 'inspection', sub_key, sub_label, i)

    # --- 故障：按一级分类子分组 ---
    if tab in ('all', 'fault'):
        q = Fault.query.options(joinedload(Fault.customer_rel))
        if date_from:
            q = q.filter(Fault.fault_time >= date_from)
        if date_to:
            q = q.filter(Fault.fault_time <= date_to)
        if customer_id:
            q = q.filter(Fault.customer_id == customer_id)
        if scope == 'mine':
            q = q.filter(Fault.handler == me)
        for f in q.order_by(Fault.fault_time.desc(), Fault.id.desc()).all():
            cust = f.customer_rel
            label_key = f.fault_category_level1 or '未分类'
            if cust is None:
                _push_record(None, '未关联客户', 'fault', label_key, label_key, f, unassigned=True)
            else:
                _push_record(cust.id, cust.name, 'fault', label_key, label_key, f)

    # --- 工单：按优先级子分组 ---
    if tab in ('all', 'ticket'):
        q = Ticket.query.options(joinedload(Ticket.customer_rel))
        if date_from:
            q = q.filter(Ticket.created_at >= date_from)
        if date_to:
            q = q.filter(Ticket.created_at <= date_to)
        if customer_id:
            q = q.filter(Ticket.customer_id == customer_id)
        if scope == 'mine':
            q = q.filter((Ticket.assigned_to == me) | (Ticket.created_by == me))
        for t in q.order_by(Ticket.created_at.desc(), Ticket.id.desc()).all():
            cust = t.customer_rel
            label_key = t.priority or '普通'
            if cust is None:
                _push_record(None, '未关联客户', 'ticket', label_key, label_key, t, unassigned=True)
            else:
                _push_record(cust.id, cust.name, 'ticket', label_key, label_key, t)

    # --- 文件式报告：扫描 REPORTS_DIR，反查 report_file 归属 ---
    if tab in ('all', 'file') and os.path.exists(REPORTS_DIR):
        # 反查索引：兼容多种 report_file 存储形态
        def _normkey(p):
            if not p:
                return ''
            return os.path.normcase(os.path.normpath(p))

        file_to_record = {}
        for Mdl in (Inspection, Fault, Ticket):
            # 只取有报告文件的记录（原实现三表全量扫描），并预加载 customer_rel
            for rec in Mdl.query.options(joinedload(Mdl.customer_rel)).filter(
                    Mdl.report_file.isnot(None), Mdl.report_file != '').all():
                v = (rec.report_file or '').strip()
                if not v:
                    continue
                cands = {
                    v,
                    os.path.basename(v),
                    _normkey(v),
                    _normkey(os.path.basename(v)),
                    _normkey(os.path.join('reports', v)),
                }
                for c in cands:
                    if c and c not in file_to_record:
                        file_to_record[c] = rec

        for fname in sorted(os.listdir(REPORTS_DIR), reverse=True):
            full = os.path.join(REPORTS_DIR, fname)
            if not os.path.isfile(full):
                continue
            ftype = '巡检' if '巡检' in fname else ('故障' if '故障' in fname else '其他')
            ftype_label = ftype + '报告' if ftype != '其他' else '其他'
            rec = (file_to_record.get(_normkey(full))
                   or file_to_record.get(_normkey(fname)))
            size = os.path.getsize(full)
            payload = {
                'filename': fname,
                'type': ftype_label,
                'size': size,
                'size_display': f'{size/1024:.1f} KB',
                'create_time': datetime.fromtimestamp(os.path.getmtime(full)).strftime('%Y-%m-%d %H:%M'),
                'source_record': rec,  # 模板可反查对应巡检/故障/工单
            }
            if rec and rec.customer_id:
                cust = customers_index.get(rec.customer_id) or rec.customer_rel
                _push_record(cust.id, cust.name, 'file', None, None, payload)
            else:
                _push_record(None, '未关联客户', 'file', None, None, payload,
                             unassigned=True)

    # --- 排序：真实客户按 name，未关联固定末位 ---
    real = sorted([v for k, v in data.items() if k is not None], key=lambda x: x['name'])
    unassigned = data.get(None)
    data_order = real + ([unassigned] if unassigned else [])

    # --- tab 统计：每个 tab 下的覆盖客户数 / 总记录数 ---
    def _tcount(p, t):
        return p['counts'].get(t, 0)

    def _has_any(p):
        return any(p['counts'].values())

    tab_stats = {
        'all': {
            'customers': sum(1 for p in data_order if _has_any(p)),
            'total': sum(sum(p['counts'].values()) for p in data_order),
        },
        'inspection': {
            'customers': sum(1 for p in data_order if _tcount(p, 'inspection')),
            'total': sum(_tcount(p, 'inspection') for p in data_order),
        },
        'fault': {
            'customers': sum(1 for p in data_order if _tcount(p, 'fault')),
            'total': sum(_tcount(p, 'fault') for p in data_order),
        },
        'ticket': {
            'customers': sum(1 for p in data_order if _tcount(p, 'ticket')),
            'total': sum(_tcount(p, 'ticket') for p in data_order),
        },
        'file': {
            'customers': sum(1 for p in data_order if _tcount(p, 'file')),
            'total': sum(_tcount(p, 'file') for p in data_order),
        },
    }

    return render_template(
        'reports/list.html',
        data_order=data_order,
        customers=customers_index,
        tab=tab,
        tab_stats=tab_stats,
        scope=scope, date_from=date_from, date_to=date_to, customer_id=customer_id,
        default_window=default_window,
    )


@ops_bp.route('/reports/delete/<path:filename>', methods=['POST'])
@login_required
@require_permission('report:delete')
def report_delete(filename):
    full = _safe_report_path(filename)
    if full is None:
        flash('非法的报告文件名', 'danger')
        current_app.logger.warning(
            '报告删除被拒绝: 用户[%s] 文件名[%s], IP=%s',
            current_user.username, filename, request.remote_addr)
        return redirect(url_for('ops.report_list'))
    os.remove(full)
    current_app.logger.info(
        '报告删除审计: 用户[%s] 删除报告[%s], IP=%s',
        current_user.username, os.path.basename(full), request.remote_addr)
    flash('已删除', 'success')
    return redirect(url_for('ops.report_list'))


@ops_bp.route('/reports/<path:filename>')
@login_required
@require_permission('report:view')
def report_download(filename):
    full = _safe_report_path(filename)
    if full is None:
        abort(404)
    return send_from_directory(os.path.dirname(full), os.path.basename(full), as_attachment=True)
