# -*- coding: utf-8 -*-
"""设备 CRUD / 详情 / 导入 / 导出 / 设备 JSON API"""
import os
from datetime import date
from flask import (render_template, request, redirect, url_for,
                   flash, send_from_directory, jsonify, current_app)
from flask_login import login_required, current_user
from models import (Device, Customer, PasswordHistory, db, DeviceType, Brand,
                    Region)
from sqlalchemy.orm import joinedload
from utils.pagination import paginate, paginate_render_args
from utils.crypto import decrypt_password
from services.device_service import (create_device_from_form, update_device_from_form,
                                      delete_device)
from utils.upload import validate_upload, save_temp_upload, open_excel, cleanup_temp_file, ALLOWED_EXCEL_EXT
from utils.permission import require_permission
from utils.decorators import api_view
from blueprints.asset import asset_bp


# ============================ 设备列表 ============================
@asset_bp.route('/devices')
@login_required
@require_permission('device:view')
def device_list():
    model_filter = request.args.get('model', '')
    brand_filter = request.args.get('brand', '')
    type_filter = request.args.get('device_type', '')
    customer_filter = request.args.get('customer_id', '', type=int)
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    query = Device.query
    if search:
        query = query.filter(
            Device.device_name.contains(search) |
            Device.ip_address.contains(search) |
            Device.brand.contains(search)
        )
    if model_filter:
        query = query.filter(Device.model == model_filter)
    if brand_filter:
        query = query.filter(Device.brand == brand_filter)
    if type_filter:
        query = query.filter(Device.device_type == type_filter)
    if customer_filter:
        query = query.filter(Device.customer_id == customer_filter)
    # 预加载关联：customer / region_rel（详情/地区列） / region.parent（地区名拼接）
    query = query.options(
        joinedload(Device.customer).joinedload(Customer.region_rel).joinedload(Region.parent),
        joinedload(Device.region_rel).joinedload(Region.parent),
    )
    query = query.order_by(Device.id.desc())
    pag = paginate(query, page=page)
    customers = Customer.query.order_by(Customer.name).all()
    models_list = db.session.query(Device.model).distinct().filter(Device.model != '').all()
    brands_list = db.session.query(Device.brand).distinct().filter(Device.brand != '').all()
    types_list = db.session.query(Device.device_type).distinct().filter(Device.device_type != '').all()
    # 当前页按客户分组，再按父子单位嵌套（不再按地市分组 —— 客户名里已含市/县）
    # 父子关系来自 services/customer_hierarchy.derive_parent_id：
    #   Customer.parent_id（手动覆盖）> 同类别+父市的市级客户
    from services.customer_hierarchy import derive_parent_id, build_parent_index
    # 1. 当前页设备按客户分组
    by_customer = {}
    for d in pag['items']:
        if d.license_expiry:
            d._days_to_expiry = (d.license_expiry - date.today()).days
        else:
            d._days_to_expiry = None
        by_customer.setdefault(d.customer_id, []).append(d)
    # 2. 取出本页所涉客户（用于决定父子归属）。父客户即便本页无设备，也要拉进来。
    cust_ids = [cid for cid in by_customer.keys() if cid is not None]
    cust_map = {}
    if cust_ids:
        page_customers = Customer.query.options(
            joinedload(Customer.region_rel).joinedload(Region.parent),
            joinedload(Customer.category_rel),
        ).filter(Customer.id.in_(cust_ids)).all()
        extra_parent_keys = set()
        for c in page_customers:
            if c.region_rel and c.region_rel.parent_id and c.category_id:
                extra_parent_keys.add((c.region_rel.parent_id, c.category_id))
        extra_parents = []
        if extra_parent_keys:
            from sqlalchemy import and_, or_
            cond = None
            for rid, catid in extra_parent_keys:
                term = and_(Customer.region_id == rid, Customer.category_id == catid,
                            ~Customer.id.in_(cust_ids))
                cond = term if cond is None else or_(cond, term)
            if cond is not None:
                extra_parents = Customer.query.options(
                    joinedload(Customer.region_rel).joinedload(Region.parent),
                    joinedload(Customer.category_rel),
                ).filter(cond).all()
        for c in list(page_customers) + list(extra_parents):
            cust_map[c.id] = c
    # 3. 父子映射
    parent_index = build_parent_index(list(cust_map.values()))
    parent_of = {}
    children_of = {}
    for c in cust_map.values():
        pid = derive_parent_id(c, parent_index)
        if pid and pid in cust_map:
            parent_of[c.id] = pid
            children_of.setdefault(pid, []).append(c.id)
    # 4. 平铺为顶层节点列表（父行 → children），按客户名排序
    customer_groups = []
    top_ids = sorted([cid for cid in cust_map.keys() if cid not in parent_of],
                     key=lambda i: cust_map[i].name)
    for top_id in top_ids:
        c = cust_map[top_id]
        node = {
            'customer': c,
            'devices': by_customer.get(top_id, []),
            'children': [
                {'customer': cust_map[child_id], 'devices': by_customer.get(child_id, []),
                 'children': []}
                for child_id in sorted(children_of.get(top_id, []),
                                       key=lambda i: cust_map[i].name)
            ],
        }
        # 父客户若本页既无设备又无子单位的设备 → 跳过
        if not node['devices'] and not any(ch['devices'] for ch in node['children']):
            continue
        customer_groups.append(node)
    # 「未分配客户」兜底：customer_id 为 None 的设备
    if None in by_customer:
        customer_groups.append({
            'customer': None,
            'devices': by_customer[None],
            'children': [],
        })
    return render_template(
        'devices/list.html', **paginate_render_args(pag),
        customers=customers,
        all_customers=customers,
        regions=Region.query.order_by(Region.parent_id.is_(None).desc(), Region.sort_order, Region.id).all(),
        device_types=DeviceType.query.order_by(DeviceType.sort_order, DeviceType.id).all(),
        brands=Brand.query.order_by(Brand.sort_order, Brand.id).all(),
        models_list=[m[0] for m in models_list if m[0]],
        brands_list=[b[0] for b in brands_list if b[0]],
        types_list=[t[0] for t in types_list if t[0]],
        customer_groups=customer_groups,
        filters={
            'model': model_filter, 'brand': brand_filter,
            'device_type': type_filter, 'customer_id': customer_filter,
            'search': search,
        }
    )


# ============================ 设备新增 ============================
@asset_bp.route('/devices/add', methods=['POST'])
@login_required
@require_permission('device:add')
def device_add():
    try:
        d = create_device_from_form(request.form)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('设备添加失败')
        flash(str(e) or '设备添加失败', 'danger')
        return redirect(url_for('asset.device_list'))
    _sync_customer_device_count(d.customer_id)
    flash('设备添加成功', 'success')
    return redirect(url_for('asset.device_list'))


@asset_bp.route('/devices/edit-page/<int:id>', methods=['GET'])
@login_required
@require_permission('device:edit')
def device_edit_page(id):
    # 编辑已改为 AJAX 弹窗，此页面仅保留兼容重定向
    return redirect(url_for('asset.device_list'))


@asset_bp.route('/devices/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('device:edit')
def device_edit(id):
    try:
        form = request.form.copy()
        form['changed_by_name'] = current_user.realname or current_user.username
        d = update_device_from_form(id, form)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('设备编辑失败')
        flash(str(e) or '设备更新失败', 'danger')
        return redirect(url_for('asset.device_list'))
    new_cid = d.customer_id
    _sync_customer_device_count(new_cid)
    flash('设备信息已更新', 'success')
    return redirect(url_for('asset.device_list'))


@asset_bp.route('/devices/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('device:delete')
def device_delete(id):
    try:
        cid = delete_device(id)
    except Exception as e:
        db.session.rollback()
        flash(str(e) or '设备删除失败', 'danger')
        return redirect(url_for('asset.device_list'))
    _sync_customer_device_count(cid)
    flash('设备已删除', 'success')
    return redirect(url_for('asset.device_list'))


# ============================ 设备详情 ============================
@asset_bp.route('/devices/<int:id>')
@login_required
@require_permission('device:view')
def device_detail(id):
    import json as _json
    d = Device.query.get_or_404(id)
    customer = Customer.query.get(d.customer_id) if d.customer_id else None
    # 安全：不再把明文密码渲染进 HTML，由前端按需调 reveal API（带审计）
    has_password = bool(d.password_encrypted)
    remaining = (d.license_expiry - date.today()).days if d.license_expiry else None
    interface_list = _json.loads(d.interface) if d.interface and d.interface.startswith('[') else (
        [d.interface] if d.interface else []
    )
    histories = PasswordHistory.query.filter_by(device_id=id)\
        .order_by(PasswordHistory.id.desc()).limit(20).all()
    return render_template('devices/detail.html',
                           device=d, customer=customer, has_password=has_password,
                           remaining=remaining, interface_list=interface_list,
                           histories=histories)


# ============================ API: 设备 JSON ============================
@asset_bp.route('/api/devices/<int:id>')
@login_required
@require_permission('device:view')
@api_view
def api_device_get(id):
    import json as _json
    d = Device.query.get_or_404(id)
    # 安全：明文密码不随设备 JSON 下发，需单独调 reveal-password（device:reveal 权限 + 审计）
    return jsonify({
        'id': d.id,
        'customer_id': d.customer_id,
        'region_id': d.region_id,
        'device_name': d.device_name,
        'device_type': d.device_type,
        'brand': d.brand,
        'model': d.model,
        'serial_number': d.serial_number or '',
        'ip_address': d.ip_address,
        'port': d.port,
        'username': d.username,
        'has_password': bool(d.password_encrypted),
        'login_method': d.login_method,
        'location': d.location,
        'interface': _json.loads(d.interface) if d.interface and d.interface.startswith('[') else (
            [d.interface] if d.interface else []
        ),
        'os_version': d.os_version,
        'rule_version': d.rule_version,
        'is_maintenance': d.is_maintenance,
        'is_in_use': d.is_in_use,
        'license_expiry': d.license_expiry.strftime('%Y-%m-%d') if d.license_expiry else '',
        'license_start': d.license_start.strftime('%Y-%m-%d') if d.license_start else '',
        'remark': d.remark,
    })


@asset_bp.route('/api/devices/<int:id>/reveal-password', methods=['POST'])
@login_required
@require_permission('device:reveal')
def api_device_reveal_password(id):
    """按需查看设备明文密码（当前密码或指定历史密码）。

    安全设计：
    - 独立权限码 device:reveal（admin/operator 默认持有）
    - POST + CSRF 保护（不豁免），前端 fetch 经 base.html 自动带 X-CSRFToken
    - 每次调用写审计日志（操作人/设备/来源 IP/是否历史密码）
    """
    d = Device.query.get_or_404(id)
    history_id = request.form.get('history_id', type=int)
    if history_id:
        h = PasswordHistory.query.filter_by(id=history_id, device_id=id).first_or_404()
        pwd = decrypt_password(h.password_encrypted) if h.password_encrypted else ''
        kind = f'历史密码(history_id={history_id})'
    else:
        pwd = decrypt_password(d.password_encrypted) if d.password_encrypted else ''
        kind = '当前密码'
    current_app.logger.info(
        '密码查看审计: 用户[%s] 查看设备[%s](id=%s) %s, IP=%s',
        current_user.username, d.device_name, d.id, kind, request.remote_addr)
    return jsonify({'password': pwd})


@asset_bp.route('/api/devices/<int:id>/password-history')
@login_required
@require_permission('device:view')
@api_view
def api_device_password_history(id):
    """历史密码列表（不含明文；明文经 reveal-password?history_id= 单独查看并审计）"""
    Device.query.get_or_404(id)
    rows = PasswordHistory.query.filter_by(device_id=id)\
        .order_by(PasswordHistory.id.desc()).limit(50).all()
    return jsonify([{
        'id': h.id,
        'changed_by': h.changed_by or '-',
        'created_at': h.created_at.strftime('%Y-%m-%d %H:%M') if h.created_at else '-',
        'remark': h.remark or '-',
    } for h in rows])


# ============================ 设备导入/导出 ============================
@asset_bp.route('/devices/export', methods=['POST'])
@login_required
@require_permission('device:view')
def device_export():
    search = request.args.get('search', '')
    customer_filter = request.args.get('customer_id', '', type=int)
    query = Device.query
    if search:
        query = query.filter(
            Device.device_name.contains(search) |
            Device.ip_address.contains(search) |
            Device.brand.contains(search)
        )
    if customer_filter:
        query = query.filter(Device.customer_id == customer_filter)
    devices = query.order_by(Device.id.desc()).all()
    selected_cols = request.form.getlist('export_columns')
    all_columns = {
        'customer_name': '所属客户', 'device_name': '设备名称', 'device_type': '设备类型',
        'brand': '品牌', 'model': '型号', 'serial_number': '序列号', 'ip_address': 'IP地址',
        'port': '端口', 'username': '登录用户名', 'password': '登录密码',
        'license_expiry': '授权截止日期', 'license_start': '授权开始日期', 'login_method': '登录方式', 'location': '安装位置',
        'os_version': '系统版本', 'rule_version': '规则库版本',
        'is_maintenance': '是否维修', 'is_in_use': '是否在用',
        'license_remaining_days': '剩余天数', 'remark': '备注',
    }
    # 安全：密码列仅 device:reveal 权限可见/可选；含密码导出写审计日志
    from utils.permission import has_permission
    if not has_permission('device:reveal'):
        all_columns.pop('password', None)
        selected_cols = [c for c in selected_cols if c != 'password']
    elif 'password' in selected_cols:
        current_app.logger.info(
            '密码导出审计: 用户[%s] 导出含明文密码的设备清单(%d台), IP=%s',
            current_user.username, len(devices), request.remote_addr)
    if not selected_cols:
        selected_cols = list(all_columns.keys())
    # 统一走 utils.excel_export（替代手写 openpyxl 样式代码）
    from utils.excel_export import export_xlsx
    headers = [all_columns[c] for c in selected_cols]
    rows = []
    for d in devices:
        data_map = {
            'customer_name': d.customer.name if d.customer else '',
            'device_name': d.device_name, 'device_type': d.device_type,
            'brand': d.brand, 'model': d.model,
            'serial_number': d.serial_number or '',
            'ip_address': d.ip_address, 'port': d.port,
            'username': d.username,
            'password': decrypt_password(d.password_encrypted) if d.password_encrypted else '',
            'license_expiry': d.license_expiry.strftime('%Y-%m-%d') if d.license_expiry else '',
            'license_start': d.license_start.strftime('%Y-%m-%d') if d.license_start else '',
            'login_method': d.login_method, 'location': d.location or '',
            'os_version': d.os_version or '', 'rule_version': d.rule_version or '',
            'is_maintenance': '是' if d.is_maintenance else '否',
            'is_in_use': '是' if d.is_in_use else '否',
            'license_remaining_days': (d.license_expiry - date.today()).days if d.license_expiry else '',
            'remark': d.remark or '',
        }
        rows.append([data_map.get(c, '') for c in selected_cols])
    path, download_name = export_xlsx(
        headers, rows, f'设备导出_{date.today().isoformat()}.xlsx', sheet_name='设备信息')
    return send_from_directory(
        os.path.dirname(path), os.path.basename(path),
        as_attachment=True, download_name=download_name
    )


@asset_bp.route('/devices/import', methods=['POST'])
@login_required
@require_permission('device:add')
def device_import():
    """批量导入设备信息"""
    if 'import_file' not in request.files:
        flash('请选择要导入的 Excel 文件', 'danger')
        return redirect(url_for('asset.device_list'))
    f = request.files['import_file']
    ok, err, _ = validate_upload(f, ALLOWED_EXCEL_EXT, max_size_mb=20)
    if not ok:
        flash(err, 'danger')
        return redirect(url_for('asset.device_list'))
    tmp = save_temp_upload(f, suffix='.xlsx')
    success_count = 0
    error_count = 0
    errors = []
    try:
        wb, ws, err = open_excel(tmp, app=current_app)
        if err:
            flash(err[0], err[1])
            return redirect(url_for('asset.device_list'))

        header_row = [cell.value for cell in ws[1]]
        col_map = {}
        for idx, h in enumerate(header_row):
            if h:
                col_map[str(h).strip()] = idx

        field_mapping = {
            '所属客户': 'customer_name', '设备名称': 'device_name', '设备类型': 'device_type',
            '品牌': 'brand', '型号': 'model', '序列号': 'serial_number', 'IP地址': 'ip_address',
            '端口': 'port', '登录用户名': 'username', '登录密码': 'password',
            '授权截止日期': 'license_expiry', '授权开始日期': 'license_start', '登录方式': 'login_method', '安装位置': 'location',
            '系统版本': 'os_version', '规则库版本': 'rule_version', '备注': 'remark',
        }

        for row_idx in range(2, ws.max_row + 1):
            row_data = {}
            for cn, idx in col_map.items():
                val = ws.cell(row=row_idx, column=idx + 1).value
                field = field_mapping.get(cn)
                if field:
                    row_data[field] = str(val).strip() if val else ''

            device_name = row_data.get('device_name', '')
            if not device_name:
                error_count += 1
                errors.append(f'第{row_idx}行：设备名称为空，跳过')
                continue

            customer = None
            if 'customer_name' in row_data and row_data['customer_name']:
                customer = Customer.query.filter_by(name=row_data['customer_name']).first()
                if not customer:
                    flash(f'客户 "{row_data["customer_name"]}" 不存在', 'warning')
            try:
                from services.device_service import _parse_date
                from utils.crypto import encrypt_password as _ep
                plain_password = row_data.get('password', '')
                encrypted = _ep(plain_password) if plain_password else ''
                license_expiry = _parse_date(row_data.get('license_expiry'))
                license_start = _parse_date(row_data.get('license_start'))

                d = Device(
                    customer_id=customer.id if customer else None,
                    device_name=device_name,
                    device_type=row_data.get('device_type', ''),
                    brand=row_data.get('brand', ''),
                    model=row_data.get('model', ''),
                    serial_number=row_data.get('serial_number', ''),
                    ip_address=row_data.get('ip_address', ''),
                    port=int(row_data.get('port', 22)) if row_data.get('port') else 22,
                    username=row_data.get('username', ''),
                    password_encrypted=encrypted,
                    login_method=row_data.get('login_method', ''),
                    os_version=row_data.get('os_version', ''),
                    rule_version=row_data.get('rule_version', ''),
                    is_maintenance=row_data.get('is_maintenance', '') in ('是', '1', 'true', 'True'),
                    is_in_use=row_data.get('is_in_use', '') in ('是', '1', 'true', 'True'),
                    license_expiry=license_expiry,
                    license_start=license_start,
                    remark=row_data.get('remark', ''),
                )
                db.session.add(d)
                db.session.commit()
                success_count += 1
            except Exception as e:
                db.session.rollback()
                error_count += 1
                errors.append(f'第{row_idx}行（{device_name}）：{e}')

        msg = f'导入完成：成功 {success_count} 条'
        if error_count:
            msg += f'，失败 {error_count} 条'
            for err in errors[:5]:
                flash(err, 'danger')
        flash(msg, 'success' if success_count else 'danger')
    finally:
        cleanup_temp_file(tmp)
    return redirect(url_for('asset.device_list'))


# ============================ 内部工具 ============================
def _sync_customer_device_count(customer_id):
    """同步客户的 device_count 冗余字段（蓝图内部使用）"""
    if not customer_id:
        return
    from models import Customer
    # 直接走服务层，消除 blueprints → app 的反向依赖
    from services.customer_service import _calculate_tier
    cnt = Device.query.filter_by(customer_id=customer_id).count()
    c = Customer.query.get(customer_id)
    if c:
        c.device_count = cnt
        auto_tier = _calculate_tier(cnt, c.has_onsite, c.has_drill)
        if c.level not in ('核心', '重点', '常规') or not c.level:
            c.level = auto_tier
        db.session.commit()

