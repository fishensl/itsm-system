# -*- coding: utf-8 -*-
"""客户管理蓝图：客户 CRUD / 详情 / 导入 / 导出 + 地区树管理

业务规则下沉到 services/customer_service.py，路由层只做参数接收和模板渲染。
"""
import os
import tempfile
from datetime import date
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, send_from_directory, jsonify, current_app)
from flask_login import login_required, current_user
from models import (Customer, CustomerCategory, Region,
                    Device, db)
from models import UserPermission, Permission
from sqlalchemy.orm import joinedload
from services.customer_service import (create_customer, update_customer, delete_customer,
                                        get_customer_with_regions,
                                        parse_extra_fields, serialize_extra_fields)
from services.customer_hierarchy import build_flat_nodes, candidate_parents
from utils.permission import require_permission, get_user_permissions


customer_bp = Blueprint('customer', __name__)


# ============================ 客户 ============================
@customer_bp.route('/customers')
@login_required
@require_permission('customer:view')
def customer_list():
    search = request.args.get('search', '')
    category_id = request.args.get('category_id', type=int)
    query = Customer.query
    if search:
        query = query.filter(
            Customer.name.contains(search) |
            Customer.contact_person.contains(search) |
            Customer.phone.contains(search)
        )
    if category_id:
        query = query.filter_by(category_id=category_id)
    # 树视图整体取出（与 departments 一致），不再分页
    query = query.options(
        joinedload(Customer.region_rel).joinedload(Region.parent),
        joinedload(Customer.category_rel),
    )
    customers = query.order_by(Customer.id.desc()).all()
    flat_nodes = build_flat_nodes(customers)
    categories = CustomerCategory.query.order_by(CustomerCategory.sort_order).all()
    return render_template('customers/list.html', flat_nodes=flat_nodes,
                           total=len(customers), search=search,
                           categories=categories,
                           current_category_id=category_id or 0)


@customer_bp.route('/customers/add', methods=['GET', 'POST'])
@login_required
@require_permission('customer:add')
def customer_add():
    if request.method == 'POST':
        try:
            data = request.form.to_dict()
            data['extra_fields'] = serialize_extra_fields(
                request.form.getlist('cf_name'), request.form.getlist('cf_value'))
            c = create_customer(data, device_count=0)
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception('客户添加失败')
            flash(str(e) or '客户添加失败', 'danger')
            return redirect(url_for('customer.customer_add'))
        # 新增客户后按其巡检频率自动生成本年度任务（失败不阻塞流程）
        gen_msg = ''
        if c.inspection_frequency:
            try:
                from utils.customer_task_generator import generate_for_customer
                n = generate_for_customer(c.id)
                if n:
                    gen_msg = f'，已生成 {n} 个本年度巡检任务'
            except Exception:
                current_app.logger.exception('客户 %s 任务自动生成失败', c.id)
        flash(f'客户添加成功（级别：{c.level}）{gen_msg}', 'success')
        return redirect(url_for('customer.customer_list'))
    ctx = get_customer_with_regions()
    categories = CustomerCategory.query.order_by(CustomerCategory.sort_order).all()
    return render_template('customers/form.html', customer=None,
                           categories=categories, custom_fields=[],
                           parent_candidates=[], **ctx)


@customer_bp.route('/customers/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@require_permission('customer:edit')
def customer_edit(id):
    c = Customer.query.get_or_404(id)
    if request.method == 'POST':
        try:
            data = request.form.to_dict()
            data['extra_fields'] = serialize_extra_fields(
                request.form.getlist('cf_name'), request.form.getlist('cf_value'))
            update_customer(id, data)
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception('客户更新失败: id=%s', id)
            flash(str(e) or '客户更新失败', 'danger')
            return redirect(url_for('customer.customer_edit', id=id))
        c = Customer.query.get(id)
        # 客户更新后：若已配置巡检频率，幂等补打本年度任务（频率未变则什么都不会新建）
        gen_msg = ''
        if c and c.inspection_frequency:
            try:
                from utils.customer_task_generator import generate_for_customer
                n = generate_for_customer(c.id)
                if n:
                    gen_msg = f'，新增 {n} 个本年度巡检任务'
            except Exception:
                current_app.logger.exception('客户 %s 任务自动生成失败', c.id)
        flash(f'客户信息已更新（级别：{c.level}）{gen_msg}', 'success')
        return redirect(url_for('customer.customer_list'))
    ctx = get_customer_with_regions(id)
    categories = CustomerCategory.query.order_by(CustomerCategory.sort_order).all()
    return render_template('customers/form.html', customer=c,
                           categories=categories,
                           custom_fields=parse_extra_fields(c),
                           parent_candidates=candidate_parents(c.category_id, exclude_id=c.id),
                           **ctx)


@customer_bp.route('/customers/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('customer:delete')
def customer_delete(id):
    try:
        delete_customer(id)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('客户删除失败: id=%s', id)
        flash(str(e) or '客户删除失败', 'danger')
        return redirect(url_for('customer.customer_list'))
    flash('客户已删除', 'success')
    return redirect(url_for('customer.customer_list'))


@customer_bp.route('/customers/<int:id>')
@login_required
@require_permission('customer:view')
def customer_detail(id):
    c = Customer.query.get_or_404(id)
    devices = Device.query.filter_by(customer_id=id).all()
    from models import Inspection, Fault, Topology
    inspections = Inspection.query.filter_by(customer_id=id).order_by(Inspection.id.desc()).limit(10).all()
    faults = Fault.query.filter_by(customer_id=id).order_by(Fault.id.desc()).limit(10).all()
    topo_raw = Topology.query.filter_by(customer_id=id).order_by(Topology.id.desc()).all()
    # V6.1.1：相同名称合并为一行（不同文件类型用图标列表展示）
    topo_groups = {}
    for t in topo_raw:
        merged = topo_groups.setdefault(t.name, {'first': t, 'files': []})
        merged['files'].append(t)
        if (merged['first'].created_at or merged['first'].id) > (t.created_at or t.id):
            merged['first'] = t
    order = {'image': 0, 'pdf': 1, 'visio': 2, 'other': 3}
    topologies = []
    for name, m in topo_groups.items():
        topologies.append({
            'name': name,
            'first': m['first'],
            'files': sorted(m['files'], key=lambda x: (order.get(x.file_type, 9), x.id)),
        })
    topologies.sort(key=lambda x: x['first'].id, reverse=True)
    # 自定义字段（该客户自己的字段列表）
    custom_field_items = [(f['name'], f['value']) for f in parse_extra_fields(c)]
    return render_template('customers/detail.html', customer=c,
                           devices=devices, inspections=inspections, faults=faults,
                           topologies=topologies, custom_field_items=custom_field_items)


@customer_bp.route('/customers/import', methods=['POST'])
@login_required
@require_permission('customer:add')
def customer_import():
    """批量导入客户"""
    from utils.upload import validate_upload, save_temp_upload, open_excel, cleanup_temp_file, ALLOWED_EXCEL_EXT
    if 'importFile' not in request.files:
        flash('请选择Excel文件', 'danger')
        return redirect(url_for('customer.customer_list'))
    f = request.files['importFile']
    ok, err, _ = validate_upload(f, ALLOWED_EXCEL_EXT, max_size_mb=20)
    if not ok:
        flash(err, 'danger')
        return redirect(url_for('customer.customer_list'))
    tmp = save_temp_upload(f, suffix='.xlsx')
    success = 0
    unknown_categories = set()  # 模板里写了但 CustomerCategory 表里没有的名字，行仍导入但 category_id 留空
    try:
        wb, ws, err = open_excel(tmp, app=current_app)
        if err:
            flash(err[0], err[1])
            return redirect(url_for('customer.customer_list'))

        col_map = {}
        header = [c.value for c in ws[1]]
        for i, h in enumerate(header):
            if h:
                col_map[str(h).strip()] = i

        def _cell(r, name):
            idx = col_map.get(name)
            if idx is None:
                return ''
            v = ws.cell(r, idx + 1).value
            return str(v).strip() if v is not None else ''

        TRUE_SET = {'是', '1', 'true', 'True', 'Y', 'y', '有'}

        for r in range(2, ws.max_row + 1):
            name = _cell(r, '客户名称')
            if not name:
                continue
            c = Customer.query.filter_by(name=name).first()
            if not c:
                region_name = _cell(r, '所属地区')
                region_id = None
                if region_name:
                    region = Region.query.filter_by(name=region_name).first()
                    if region:
                        region_id = region.id

                category_id = None
                cat_name = _cell(r, '单位类别')
                if cat_name:
                    cat = CustomerCategory.query.filter_by(name=cat_name).first()
                    if cat:
                        category_id = cat.id
                    else:
                        unknown_categories.add(cat_name)

                c = Customer(
                    name=name,
                    contact_person=_cell(r, '联系人') or None,
                    phone=_cell(r, '电话') or None,
                    email=_cell(r, '邮箱') or None,
                    region_id=region_id,
                    category_id=category_id,
                    city=_cell(r, '地市') or None,
                    address=_cell(r, '地址') or None,
                    office=_cell(r, '办公室') or '',
                    level=_cell(r, '客户等级') or '常规',
                    has_onsite=_cell(r, '有无驻场') in TRUE_SET,
                    onsite_contact=_cell(r, '驻场联系人') or '',
                    onsite_phone=_cell(r, '驻场联系方式') or '',
                    onsite_office=_cell(r, '驻场办公室') or '',
                    has_drill=_cell(r, '有无攻防演练') in TRUE_SET,
                    inspection_frequency=_cell(r, '巡检频率') or '',
                    source=_cell(r, '来源') or None,
                    remark=_cell(r, '备注') or None,
                )
                db.session.add(c)
                success += 1
        db.session.commit()
        msg = f'导入完成：成功 {success} 条'
        if unknown_categories:
            msg += '；未识别单位类别（已留空，请在「客户类别」管理中维护后重新导入）：' + '、'.join(sorted(unknown_categories))
        flash(msg, 'success' if not unknown_categories else 'warning')
    finally:
        cleanup_temp_file(tmp)
    return redirect(url_for('customer.customer_list'))


@customer_bp.route('/customers/export')
@login_required
@require_permission('customer:view')
def customer_export():
    """导出客户列表到 Excel（列序与导入模板保持一致，便于导出后修改再导入）"""
    from utils.excel_export import export_xlsx
    headers = ['客户名称', '联系人', '电话', '邮箱', '所属地区', '地市', '地址',
               '单位类别', '客户等级',
               '办公室', '有无驻场', '驻场联系人', '驻场联系方式', '驻场办公室',
               '有无攻防演练', '巡检频率',
               '来源', '备注']
    rows = []
    for c in Customer.query.order_by(Customer.name).all():
        # 所属地区：父级 + 自身（拼接给人看）；地市单独一列
        region_label = ''
        if c.region_rel:
            if c.region_rel.parent:
                region_label = f"{c.region_rel.parent.name} - {c.region_rel.name}"
            else:
                region_label = c.region_rel.name
        rows.append([
            c.name, c.contact_person or '', c.phone or '', c.email or '',
            region_label, c.city or '', c.address or '',
            (c.category_rel.name if c.category_rel else ''),
            c.level or '',
            c.office or '',
            '是' if c.has_onsite else '否',
            c.onsite_contact or '', c.onsite_phone or '', c.onsite_office or '',
            '是' if c.has_drill else '否',
            c.inspection_frequency or '',
            c.source or '', c.remark or '',
        ])

    tmp_path, download_name = export_xlsx(
        headers, rows,
        filename=f'客户导出_{date.today().isoformat()}.xlsx',
        sheet_name='客户信息',
    )
    return send_from_directory(
        os.path.dirname(tmp_path), os.path.basename(tmp_path),
        as_attachment=True, download_name=download_name,
    )


# ============================ 地区管理 ============================
@customer_bp.route('/regions')
@login_required
@require_permission('region:view')
def region_list():
    """按地市分组展示地区，区/县折叠在地市下"""
    cities = Region.query.options(joinedload(Region.children))\
        .filter_by(parent_id=None).order_by(Region.sort_order, Region.id).all()
    for c in cities:
        c.children = sorted(c.children, key=lambda d: (d.sort_order, d.id))
    return render_template('regions/list.html', cities=cities)


@customer_bp.route('/regions/add', methods=['POST'])
@login_required
@require_permission('region:add')
def region_add():
    name = request.form.get('name', '').strip()
    if not name:
        flash('地区名称不能为空', 'danger')
        return redirect(url_for('customer.region_list'))
    parent_id = request.form.get('parent_id', type=int) or None
    if Region.query.filter_by(name=name, parent_id=parent_id).first():
        flash(f'同级已存在同名地区 "{name}"', 'danger')
        return redirect(url_for('customer.region_list'))
    from sqlalchemy import func
    max_so = db.session.query(func.max(Region.sort_order)).filter_by(parent_id=parent_id).scalar() or 0
    r = Region(name=name, parent_id=parent_id, sort_order=max_so + 1)
    db.session.add(r)
    db.session.commit()
    flash(f'地区 "{name}" 已添加', 'success')
    return redirect(url_for('customer.region_list'))


@customer_bp.route('/regions/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('region:edit')
def region_edit(id):
    r = Region.query.get_or_404(id)
    name = request.form.get('name', '').strip()
    if not name:
        flash('地区名称不能为空', 'danger')
        return redirect(url_for('customer.region_list'))
    parent_id = request.form.get('parent_id', type=int) or None
    r.name = name
    r.parent_id = parent_id
    r.sort_order = int(request.form.get('sort_order', 0))
    db.session.commit()
    flash(f'地区 "{name}" 已更新', 'success')
    return redirect(url_for('customer.region_list'))


@customer_bp.route('/regions/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('region:delete')
def region_delete(id):
    r = Region.query.get_or_404(id)
    if Region.query.filter_by(parent_id=id).count() > 0:
        flash('该地区下还有子地区，请先删除子地区', 'danger')
        return redirect(url_for('customer.region_list'))
    name = r.name
    db.session.delete(r)
    db.session.commit()
    flash(f'地区 "{name}" 已删除', 'success')
    return redirect(url_for('customer.region_list'))


@customer_bp.route('/api/regions/children/<int:parent_id>')
@login_required
def api_region_children(parent_id):
    """返回指定地区的直接子地区列表（JSON），用于客户表单的市→区/县级联"""
    children = Region.query.filter_by(parent_id=parent_id)\
        .order_by(Region.sort_order, Region.id).all()
    return jsonify({'success': True, 'items': [{'id': r.id, 'name': r.name} for r in children]})


@customer_bp.route('/api/customers/parent-candidates')
@login_required
def api_parent_candidates():
    """返回指定类别下可作为「上级单位」的市级客户（JSON）。

    Query 参数：
      - category_id（必填）
      - exclude_id（可选，编辑场景排除自己 + 自己的后代）
    """
    cat_id = request.args.get('category_id', type=int)
    exclude_id = request.args.get('exclude_id', type=int)
    if not cat_id:
        return jsonify({'success': True, 'items': []})
    items = candidate_parents(cat_id, exclude_id=exclude_id)
    return jsonify({'success': True,
                    'items': [{'id': c.id, 'name': c.name} for c in items]})
