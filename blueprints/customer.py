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
from utils.pagination import paginate, paginate_render_args
from services.customer_service import (create_customer, update_customer, delete_customer,
                                        get_customer_with_regions,
                                        parse_extra_fields, serialize_extra_fields)
from utils.permission import require_permission, get_user_permissions


customer_bp = Blueprint('customer', __name__)


# ============================ 客户 ============================
@customer_bp.route('/customers')
@login_required
@require_permission('customer:view')
def customer_list():
    search = request.args.get('search', '')
    category_id = request.args.get('category_id', type=int)
    page = request.args.get('page', 1, type=int)
    query = Customer.query
    if search:
        query = query.filter(
            Customer.name.contains(search) |
            Customer.contact_person.contains(search) |
            Customer.phone.contains(search)
        )
    if category_id:
        query = query.filter_by(category_id=category_id)
    query = query.options(joinedload(Customer.region_rel).joinedload(Region.parent))
    query = query.order_by(Customer.id.desc())
    pag = paginate(query, page=page)
    categories = CustomerCategory.query.order_by(CustomerCategory.sort_order).all()
    return render_template('customers/list.html', **paginate_render_args(pag), search=search,
                          categories=categories, current_category_id=category_id or 0)


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
        flash(f'客户添加成功（级别：{c.level}）', 'success')
        return redirect(url_for('customer.customer_list'))
    ctx = get_customer_with_regions()
    categories = CustomerCategory.query.order_by(CustomerCategory.sort_order).all()
    return render_template('customers/form.html', customer=None,
                           categories=categories, custom_fields=[], **ctx)


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
        flash(f'客户信息已更新（级别：{c.level}）', 'success')
        return redirect(url_for('customer.customer_list'))
    ctx = get_customer_with_regions(id)
    categories = CustomerCategory.query.order_by(CustomerCategory.sort_order).all()
    return render_template('customers/form.html', customer=c,
                           categories=categories,
                           custom_fields=parse_extra_fields(c), **ctx)


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

        for r in range(2, ws.max_row + 1):
            name = str(ws.cell(r, col_map.get('客户名称', 0) + 1).value or '').strip()
            if not name:
                continue
            c = Customer.query.filter_by(name=name).first()
            if not c:
                region_name = str(ws.cell(r, col_map.get('所属地区', 0) + 1).value or '').strip()
                region_id = None
                if region_name:
                    region = Region.query.filter_by(name=region_name).first()
                    if region:
                        region_id = region.id
                c = Customer(
                    name=name,
                    contact_person=str(ws.cell(r, col_map.get('联系人', 0) + 1).value or '').strip() or None,
                    phone=str(ws.cell(r, col_map.get('电话', 0) + 1).value or '').strip() or None,
                    email=str(ws.cell(r, col_map.get('邮箱', 0) + 1).value or '').strip() or None,
                    region_id=region_id,
                    city=str(ws.cell(r, col_map.get('地市', 0) + 1).value or '').strip() or None,
                    address=str(ws.cell(r, col_map.get('地址', 0) + 1).value or '').strip() or None,
                    level=str(ws.cell(r, col_map.get('客户等级', 0) + 1).value or '').strip() or '普通',
                    source=str(ws.cell(r, col_map.get('来源', 0) + 1).value or '').strip() or None,
                    remark=str(ws.cell(r, col_map.get('备注', 0) + 1).value or '').strip() or None,
                )
                db.session.add(c)
                success += 1
        db.session.commit()
        flash(f'导入完成：成功 {success} 条', 'success')
    finally:
        cleanup_temp_file(tmp)
    return redirect(url_for('customer.customer_list'))


@customer_bp.route('/customers/export')
@login_required
@require_permission('customer:view')
def customer_export():
    """导出客户列表到 Excel"""
    from utils.excel_export import export_xlsx
    headers = ['客户名称', '联系人', '电话', '邮箱', '所属地市', '地址', '备注']
    rows = []
    for c in Customer.query.order_by(Customer.name).all():
        region_label = c.city or ''
        if c.region_rel:
            if c.region_rel.parent:
                region_label = f"{c.region_rel.parent.name} - {c.region_rel.name}"
            else:
                region_label = c.region_rel.name
        rows.append([c.name, c.contact_person, c.phone, c.email, region_label, c.address, c.remark])

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
