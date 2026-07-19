# -*- coding: utf-8 -*-
"""巡检模板 / 设备检查模板 / 任务模板 CRUD + 自动匹配 API"""
from flask import (render_template, request, redirect, url_for,
                   flash, jsonify, current_app)
from flask_login import login_required
from models import (InspectionTemplate, InspectionDeviceTemplate,
                    InspectionTaskTemplate, Customer, Device, db)
from utils.permission import require_permission
from blueprints.ops import ops_bp


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


