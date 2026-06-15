# -*- coding: utf-8 -*-
"""机柜管理蓝图：位置 / 机柜 / 设备上架（V6.1）"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, abort)
from flask_login import login_required, current_user
from models import (Rack, RackLocation, RackInstall, Device, Customer, db)
from utils.permission import require_permission

rack_bp = Blueprint('rack', __name__)


# ============================ 主页面 ============================
@rack_bp.route('/rack')
@login_required
@require_permission('device:view')
def rack_index():
    """机柜管理主页：左侧位置树 + 右侧机柜可视化"""
    locations = RackLocation.query.order_by(RackLocation.id.desc()).all()
    customers = Customer.query.order_by(Customer.name).all()
    return render_template('rack/index.html', locations=locations, customers=customers)


# ============================ 位置 API ============================
@rack_bp.route('/api/rack/locations', methods=['GET'])
@login_required
def api_locations():
    items = []
    for loc in RackLocation.query.order_by(RackLocation.id.desc()).all():
        items.append({
            'id': loc.id,
            'customer_id': loc.customer_id,
            'customer_name': loc.customer_rel.name if loc.customer_rel else '',
            'building': loc.building,
            'floor': loc.floor,
            'remark': loc.remark,
            'rack_count': len(loc.racks),
        })
    return jsonify({'items': items})


@rack_bp.route('/api/rack/locations', methods=['POST'])
@login_required
@require_permission('device:edit')
def api_location_create():
    data = request.get_json(silent=True) or request.form.to_dict()
    if not data.get('building'):
        return jsonify({'error': '楼栋不能为空'}), 400
    loc = RackLocation(
        customer_id=int(data['customer_id']) if data.get('customer_id') else None,
        building=data.get('building', ''),
        floor=data.get('floor', ''),
        remark=data.get('remark', ''),
    )
    db.session.add(loc); db.session.commit()
    return jsonify({'id': loc.id, 'ok': True})


@rack_bp.route('/api/rack/locations/<int:loc_id>', methods=['DELETE'])
@login_required
@require_permission('device:delete')
def api_location_delete(loc_id):
    loc = RackLocation.query.get_or_404(loc_id)
    if loc.racks:
        return jsonify({'error': '该位置下还有机柜，无法删除'}), 400
    db.session.delete(loc); db.session.commit()
    return jsonify({'ok': True})


# ============================ 机柜 API ============================
@rack_bp.route('/api/rack/cabinets', methods=['GET'])
@login_required
def api_cabinets():
    """获取机柜列表（可按 location_id 过滤）"""
    location_id = request.args.get('location_id', type=int)
    q = Rack.query
    if location_id:
        q = q.filter_by(location_id=location_id)
    items = []
    for r in q.order_by(Rack.id.desc()).all():
        # 计算 U 占用
        used = sum(i.occupy_u or 0 for i in r.installs)
        used_pct = round(used * 100 / r.total_u, 1) if r.total_u else 0
        # 总功率
        used_w = sum(i.rated_w or 0 for i in r.installs)
        items.append({
            'id': r.id,
            'location_id': r.location_id,
            'location_name': f'{r.location_rel.building} {r.location_rel.floor}'.strip() if r.location_rel else '',
            'name': r.name,
            'total_u': r.total_u,
            'used_u': used,
            'used_pct': used_pct,
            'color': r.color,
            'pdu_total_w': r.pdu_total_w,
            'used_w': used_w,
            'remark': r.remark,
            'install_count': len(r.installs),
        })
    return jsonify({'items': items})


@rack_bp.route('/api/rack/cabinets/<int:rack_id>', methods=['GET'])
@login_required
def api_cabinet_detail(rack_id):
    """获取单个机柜详情（含设备布局）"""
    r = Rack.query.get_or_404(rack_id)
    installs = []
    for i in sorted(r.installs, key=lambda x: x.start_u or 0):
        if i.device_id and i.device_rel:
            name = i.device_rel.device_name
            brand = i.device_rel.brand or ''
            model = i.device_rel.model or ''
            ip = i.device_rel.ip_address or ''
            kind = '托管'
        else:
            name = i.manual_name or '(未命名)'
            brand = i.manual_brand or ''
            model = i.manual_model or ''
            ip = i.manual_ip or ''
            kind = '手动'
        installs.append({
            'id': i.id,
            'device_id': i.device_id,
            'name': name,
            'brand': brand,
            'model': model,
            'ip': ip,
            'kind': kind,
            'start_u': i.start_u,
            'occupy_u': i.occupy_u,
            'rated_w': i.rated_w,
            'remark': i.remark,
        })
    return jsonify({
        'id': r.id,
        'name': r.name,
        'total_u': r.total_u,
        'color': r.color,
        'pdu_total_w': r.pdu_total_w,
        'remark': r.remark,
        'location_name': f'{r.location_rel.building} {r.location_rel.floor}'.strip() if r.location_rel else '',
        'installs': installs,
    })


@rack_bp.route('/api/rack/cabinets', methods=['POST'])
@login_required
@require_permission('device:edit')
def api_cabinet_create():
    data = request.get_json(silent=True) or request.form.to_dict()
    if not data.get('name'):
        return jsonify({'error': '机柜名称不能为空'}), 400
    r = Rack(
        location_id=int(data['location_id']) if data.get('location_id') else None,
        name=data.get('name', ''),
        total_u=int(data.get('total_u') or 42),
        color=data.get('color', '#0d6efd'),
        pdu_total_w=int(data.get('pdu_total_w') or 0),
        remark=data.get('remark', ''),
    )
    db.session.add(r); db.session.commit()
    return jsonify({'id': r.id, 'ok': True})


@rack_bp.route('/api/rack/cabinets/<int:rack_id>', methods=['PUT'])
@login_required
@require_permission('device:edit')
def api_cabinet_update(rack_id):
    r = Rack.query.get_or_404(rack_id)
    data = request.get_json(silent=True) or request.form.to_dict()
    r.name = data.get('name', r.name)
    r.total_u = int(data.get('total_u') or r.total_u)
    r.color = data.get('color', r.color)
    r.pdu_total_w = int(data.get('pdu_total_w') or 0)
    r.remark = data.get('remark', '')
    db.session.commit()
    return jsonify({'ok': True})


@rack_bp.route('/api/rack/cabinets/<int:rack_id>', methods=['DELETE'])
@login_required
@require_permission('device:delete')
def api_cabinet_delete(rack_id):
    r = Rack.query.get_or_404(rack_id)
    # 删除时一并清理 installs
    for i in list(r.installs):
        db.session.delete(i)
    db.session.delete(r); db.session.commit()
    return jsonify({'ok': True})


# ============================ 设备上架 API ============================
@rack_bp.route('/api/rack/devices/all', methods=['GET'])
@login_required
def api_all_devices():
    """获取所有设备（用于上架时下拉选择）"""
    items = []
    # 已上架设备 ID 集
    installed = {i.device_id for i in RackInstall.query.filter(RackInstall.device_id.isnot(None)).all()}
    for d in Device.query.order_by(Device.device_name).all():
        items.append({
            'id': d.id,
            'name': d.device_name,
            'brand': d.brand or '',
            'model': d.model or '',
            'ip': d.ip_address or '',
            'installed': d.id in installed,
        })
    return jsonify({'items': items})


@rack_bp.route('/api/rack/installs', methods=['POST'])
@login_required
@require_permission('device:edit')
def api_install_create():
    """设备上架"""
    data = request.get_json(silent=True) or request.form.to_dict()
    rack_id = int(data['rack_id']) if data.get('rack_id') else None
    if not rack_id:
        return jsonify({'error': '请指定机柜'}), 400
    r = Rack.query.get_or_404(rack_id)
    start_u = int(data.get('start_u') or 1)
    occupy_u = int(data.get('occupy_u') or 1)
    if start_u < 1 or start_u + occupy_u - 1 > r.total_u:
        return jsonify({'error': f'U 位超出范围（机柜共 {r.total_u}U）'}), 400
    # U 位冲突检查
    for inst in r.installs:
        s, e = inst.start_u, inst.start_u + inst.occupy_u - 1
        ns, ne = start_u, start_u + occupy_u - 1
        if not (ne < s or ns > e):
            return jsonify({'error': f'U 位冲突：{s}U-{e}U 已被占用'}), 400

    install = RackInstall(
        rack_id=rack_id,
        device_id=int(data['device_id']) if data.get('device_id') else None,
        manual_name=data.get('manual_name', ''),
        manual_brand=data.get('manual_brand', ''),
        manual_model=data.get('manual_model', ''),
        manual_ip=data.get('manual_ip', ''),
        start_u=start_u,
        occupy_u=occupy_u,
        rated_w=int(data.get('rated_w') or 0),
        remark=data.get('remark', ''),
    )
    db.session.add(install); db.session.commit()
    return jsonify({'id': install.id, 'ok': True})


@rack_bp.route('/api/rack/installs/<int:install_id>', methods=['PUT'])
@login_required
@require_permission('device:edit')
def api_install_update(install_id):
    """调整安装位置"""
    inst = RackInstall.query.get_or_404(install_id)
    data = request.get_json(silent=True) or request.form.to_dict()
    new_start = int(data.get('start_u') or inst.start_u)
    new_occupy = int(data.get('occupy_u') or inst.occupy_u)
    r = inst.rack_rel
    if new_start < 1 or new_start + new_occupy - 1 > r.total_u:
        return jsonify({'error': f'U 位超出范围'}), 400
    # 冲突检查（排除自身）
    for other in r.installs:
        if other.id == inst.id:
            continue
        s, e = other.start_u, other.start_u + other.occupy_u - 1
        ns, ne = new_start, new_start + new_occupy - 1
        if not (ne < s or ns > e):
            return jsonify({'error': f'U 位冲突：{s}U-{e}U 已被占用'}), 400
    inst.start_u = new_start
    inst.occupy_u = new_occupy
    inst.rated_w = int(data.get('rated_w') or 0)
    inst.remark = data.get('remark', '')
    db.session.commit()
    return jsonify({'ok': True})


@rack_bp.route('/api/rack/installs/<int:install_id>', methods=['DELETE'])
@login_required
@require_permission('device:delete')
def api_install_delete(install_id):
    """下架"""
    inst = RackInstall.query.get_or_404(install_id)
    db.session.delete(inst); db.session.commit()
    return jsonify({'ok': True})
