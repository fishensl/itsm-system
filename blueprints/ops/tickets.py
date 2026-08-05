# -*- coding: utf-8 -*-
"""工单管理 CRUD + 状态机动作 + 归档为故障案例"""
import os
from flask import (render_template, request, redirect, url_for,
                   flash, current_app)
from flask_login import login_required, current_user
from models import (Ticket,
                    TicketLog, KnowledgeBase, FaultType, Customer, Device, db)
from utils.pagination import paginate, paginate_render_args
from utils.permission import require_permission
from utils.decorators import form_commit
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
        me = current_user.realname or current_user.username
        try:
            t = create_ticket(request.form.to_dict(), me)
            # 处置方式：self_accept = 工程师录单后直接自己接单处置（派单+接单一体完成）
            if request.form.get('dispatch_mode') == 'self_accept':
                assign_ticket(t.id, me, me, remark='录单时自行接单')
                accept_ticket(t.id, me, remark='录单即开工')
        except Exception as e:
            db.session.rollback()
            flash(str(e) or '工单创建失败', 'danger')
            return redirect(url_for('ops.ticket_add'))
        if request.form.get('dispatch_mode') == 'self_accept':
            flash(f'工单 {t.number} 已创建并由你接单，处置中', 'success')
        else:
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
@form_commit('工单已删除', 'ops.ticket_list', '工单删除失败')
def ticket_delete(id):
    """删除工单（连带日志）。form_commit 统一异常回滚；删除写审计日志。"""
    t = Ticket.query.get_or_404(id)
    current_app.logger.info(
        '工单删除审计: 用户[%s] 删除工单[%s](id=%s), IP=%s',
        current_user.username, t.number, t.id, request.remote_addr)
    TicketLog.query.filter_by(ticket_id=id).delete()
    Ticket.query.filter_by(id=id).delete()
    db.session.commit()


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
    """提交处理结果（待审核）；支持上传处理报告文件（V21 版本化闭环）。"""
    report_path = ''
    try:
        if request.files.get('report_file'):
            from utils.upload import validate_upload
            ALLOWED_REPORT_EXT = {'.doc', '.docx', '.pdf', '.xlsx', '.xls',
                                  '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.zip'}
            f = request.files['report_file']
            ok_flag, err, safe_name = validate_upload(f, ALLOWED_REPORT_EXT, max_size_mb=50)
            if not ok_flag:
                flash(err or '文件校验失败', 'danger')
                return redirect(url_for('ops.ticket_detail', id=id))
            import os
            os.makedirs(os.path.join('static', 'uploads', 'ticket_reports', str(id)), exist_ok=True)
            report_path = '/'.join(('uploads', 'ticket_reports', str(id), safe_name))
            f.save(os.path.join('static', report_path))
        submit_ticket(id, current_user.realname or current_user.username,
                      request.form.get('remark', ''),
                      diagnosis=request.form.get('diagnosis', ''),
                      solution=request.form.get('solution', ''),
                      report_path=report_path, submitter_user_id=current_user.id)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '提交失败', 'danger')
    return redirect(url_for('ops.ticket_detail', id=id))


@ops_bp.route('/tickets/<int:id>/audit', methods=['POST'])
@login_required
@require_permission('ticket:review')
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


# ============== V21 工单导出（按客户 + 自定义时间段） ==============
def _ticket_export_filter(args):
    """解析导出筛选参数 → (query, customer_map)"""
    from datetime import date as _date
    q = Ticket.query
    customer_id = args.get('customer_id', type=int)
    date_from = args.get('date_from') or ''
    date_to = args.get('date_to') or ''
    if customer_id:
        q = q.filter(Ticket.customer_id == customer_id)
    if date_from:
        try:
            q = q.filter(Ticket.created_at >= _date.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(Ticket.created_at <= _date.fromisoformat(date_to))
        except ValueError:
            pass
    return q.order_by(Ticket.id.desc()).all()


def _ticket_export_rows(tickets):
    """工单导出行 + 收集报告文件列表 [(完整路径, zip内名)]"""
    from models import SubmissionVersion
    customer_map = {c.id: c.name for c in Customer.query.all()}
    headers = ['单号', '标题', '客户', '状态', '优先级', '处理人', '创建时间',
               '诊断', '方案', '处理报告', '审核状态', '审核意见', '资料完整']
    rows = []
    files = []
    for t in tickets:
        cust = customer_map.get(t.customer_id, '-')
        versions = SubmissionVersion.query \
            .filter_by(entity_type='ticket', entity_id=t.id) \
            .order_by(SubmissionVersion.version_no.asc()).all()
        for v in versions:
            if v.report_file:
                full = os.path.realpath(os.path.join('static', v.report_file))
                if os.path.isfile(full):
                    fname = os.path.basename(v.report_file)
                    files.append((full, f'{cust}/工单{t.number}/v{v.version_no}_{fname}'))
        rows.append([
            t.number, t.title, cust, t.status, t.priority or '', t.assigned_to or '',
            t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else '',
            t.diagnosis or '', t.solution or '',
            '有' if t.report_file else '无',
            (t.audit_status or '') + (f'（{t.audit_comment}）' if t.audit_comment else ''),
            '完整' if not [x for x in [t.assigned_to, t.diagnosis, t.solution, t.report_file,
                                       t.audit_status] if not x] else '缺失',
        ])
    return headers, rows, files


@ops_bp.route('/tickets/export')
@login_required
@require_permission('ticket:view')
def ticket_export():
    """工单记录导出 Excel（?customer_id=&date_from=&date_to=）"""
    from datetime import date as _date
    from utils.excel_export import export_xlsx
    from flask import send_from_directory
    tickets = _ticket_export_filter(request.args)
    headers, rows, _files = _ticket_export_rows(tickets)
    path, download_name = export_xlsx(
        headers, rows, f'工单导出_{_date.today().isoformat()}.xlsx', sheet_name='工单记录')
    return send_from_directory(os.path.dirname(path), os.path.basename(path),
                               as_attachment=True, download_name=download_name)


@ops_bp.route('/tickets/reports-zip')
@login_required
@require_permission('ticket:view')
def ticket_reports_zip():
    """工单记录+处理报告打包下载（按客户/时间段筛选）"""
    from datetime import date as _date
    from utils.excel_export import export_xlsx
    from utils.report_zip import build_records_zip
    from flask import send_file
    tickets = _ticket_export_filter(request.args)
    headers, rows, files = _ticket_export_rows(tickets)
    if not rows:
        flash('当前筛选条件下没有可导出的工单记录', 'warning')
        return redirect(request.referrer or url_for('ops.ticket_list'))
    excel_path, _ = export_xlsx(headers, rows, '工单明细.xlsx', sheet_name='工单记录')
    zip_path = build_records_zip(excel_path, files, '工单报告包')
    return send_file(zip_path, as_attachment=True,
                     download_name=f'工单报告包_{_date.today().isoformat()}.zip')


