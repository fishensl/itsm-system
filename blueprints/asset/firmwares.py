# -*- coding: utf-8 -*-
"""设备固件版本库 (V12)"""
from datetime import date
from flask import (render_template, request, redirect, url_for,
                   flash, jsonify)
from flask_login import login_required
from models import (Device, db, DeviceFirmware)
from utils.permission import require_permission
from blueprints.asset import asset_bp


# ============================ 设备固件版本库 (V12) ============================
def _parse_date_arg(s):
    if not s: return None
    try:
        return date.fromisoformat(s.strip())
    except Exception:
        return None


@asset_bp.route('/device-firmwares')
@login_required
@require_permission('device:view')
def firmware_list():
    """固件版本库列表 — 按 brand+model 分组展示，附带使用该型号的设备列表（用于版本对比）"""
    brand_filter = request.args.get('brand', '')
    model_filter = request.args.get('model', '')
    type_filter = request.args.get('firmware_type', '')

    q = DeviceFirmware.query
    if brand_filter:
        q = q.filter(DeviceFirmware.brand == brand_filter)
    if model_filter:
        q = q.filter(DeviceFirmware.model == model_filter)
    if type_filter:
        q = q.filter(DeviceFirmware.firmware_type == type_filter)
    firmwares = q.order_by(
        DeviceFirmware.brand, DeviceFirmware.model,
        DeviceFirmware.firmware_type, DeviceFirmware.is_latest.desc(),
        DeviceFirmware.release_date.desc()
    ).all()

    # 按 (brand, model) 分组：每组下再按 firmware_type 分组
    from collections import OrderedDict
    grouped = OrderedDict()
    for fw in firmwares:
        key = (fw.brand or '未分类', fw.model or '未分类型号')
        grouped.setdefault(key, OrderedDict()).setdefault(fw.firmware_type or '其他', []).append(fw)

    # 为每组挂上设备清单（同 brand+model 的所有设备，便于对比版本）
    # 性能：单条 OR 组合查询 + Python 分桶，替代逐组 N+1 查询
    group_devices = {k: [] for k in grouped.keys()}
    if grouped:
        from sqlalchemy import and_, or_
        pair_conds = []
        for brand, model in grouped.keys():
            # grouped 的 key 已做空值替换（'未分类'/'未分类型号'），还原为 DB 匹配条件
            b_cond = Device.brand == (brand if brand != '未分类' else '')
            m_cond = Device.model == (model if model != '未分类型号' else '')
            if brand == '未分类':
                b_cond = or_(Device.brand == '', Device.brand.is_(None))
            if model == '未分类型号':
                m_cond = or_(Device.model == '', Device.model.is_(None))
            pair_conds.append(and_(b_cond, m_cond))
        for dev in Device.query.filter(or_(*pair_conds)).all():
            key = (dev.brand or '未分类', dev.model or '未分类型号')
            if key in group_devices:
                group_devices[key].append(dev)

    # 筛选下拉
    all_brands = sorted(set(b for b, _ in grouped.keys() if b))
    all_models = sorted(set(m for _, m in grouped.keys() if m))
    all_types = ['系统固件', '规则库', 'BIOS', '其他']

    return render_template('device_firmwares/list.html',
                           grouped=grouped, group_devices=group_devices,
                           all_brands=all_brands, all_models=all_models, all_types=all_types,
                           brand_filter=brand_filter, model_filter=model_filter, type_filter=type_filter)


@asset_bp.route('/device-firmwares/add', methods=['POST'])
@login_required
@require_permission('device:edit')
def firmware_add():
    is_latest = request.form.get('is_latest') == 'on'
    fw = DeviceFirmware(
        brand=(request.form.get('brand') or '').strip(),
        model=(request.form.get('model') or '').strip(),
        firmware_type=request.form.get('firmware_type', '系统固件'),
        version=(request.form.get('version') or '').strip(),
        release_date=_parse_date_arg(request.form.get('release_date')),
        changelog=request.form.get('changelog', ''),
        download_url=request.form.get('download_url', ''),
        file_size_mb=float(request.form.get('file_size_mb') or 0) if request.form.get('file_size_mb') else 0,
        md5_checksum=request.form.get('md5_checksum', ''),
        is_latest=is_latest,
        min_compatible_hardware=request.form.get('min_compatible_hardware', ''),
        upgrade_guide=request.form.get('upgrade_guide', ''),
        remark=request.form.get('remark', ''),
    )
    if not fw.brand or not fw.model or not fw.version:
        flash('品牌/型号/版本号为必填项', 'danger')
        return redirect(url_for('asset.firmware_list'))
    # 同 brand+model+firmware_type 仅一条 is_latest=True
    if is_latest:
        DeviceFirmware.query.filter_by(brand=fw.brand, model=fw.model, firmware_type=fw.firmware_type
                                       ).update({'is_latest': False})
    db.session.add(fw); db.session.commit()
    flash('已添加固件版本', 'success')
    return redirect(url_for('asset.firmware_list'))


@asset_bp.route('/device-firmwares/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('device:edit')
def firmware_edit(id):
    fw = DeviceFirmware.query.get_or_404(id)
    fw.brand = (request.form.get('brand') or fw.brand).strip()
    fw.model = (request.form.get('model') or fw.model).strip()
    fw.firmware_type = request.form.get('firmware_type', fw.firmware_type)
    fw.version = (request.form.get('version') or fw.version).strip()
    fw.release_date = _parse_date_arg(request.form.get('release_date')) or fw.release_date
    fw.changelog = request.form.get('changelog', fw.changelog)
    fw.download_url = request.form.get('download_url', fw.download_url)
    try:
        if request.form.get('file_size_mb'):
            fw.file_size_mb = float(request.form['file_size_mb'])
    except (TypeError, ValueError):
        pass
    fw.md5_checksum = request.form.get('md5_checksum', fw.md5_checksum)
    fw.min_compatible_hardware = request.form.get('min_compatible_hardware', fw.min_compatible_hardware)
    fw.upgrade_guide = request.form.get('upgrade_guide', fw.upgrade_guide)
    fw.remark = request.form.get('remark', fw.remark)
    new_is_latest = request.form.get('is_latest') == 'on'
    if new_is_latest and not fw.is_latest:
        # 切换为最新 → 清掉同组其他 latest
        DeviceFirmware.query.filter(
            DeviceFirmware.brand == fw.brand,
            DeviceFirmware.model == fw.model,
            DeviceFirmware.firmware_type == fw.firmware_type,
            DeviceFirmware.id != fw.id,
        ).update({'is_latest': False})
    fw.is_latest = new_is_latest
    db.session.commit()
    flash('已更新', 'success')
    return redirect(url_for('asset.firmware_list'))


@asset_bp.route('/device-firmwares/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('device:delete')
def firmware_delete(id):
    fw = DeviceFirmware.query.get(id)
    if fw:
        db.session.delete(fw); db.session.commit()
    flash('已删除', 'success')
    return redirect(url_for('asset.firmware_list'))


@asset_bp.route('/api/firmwares/match-device/<int:device_id>')
@login_required
@require_permission('device:view')
def api_firmware_match_device(device_id):
    """V12: 给定设备 id，返回该设备 brand+model 下所有固件版本（以及最新版本标记）"""
    d = Device.query.get_or_404(device_id)
    fws = DeviceFirmware.query.filter_by(brand=d.brand, model=d.model).order_by(
        DeviceFirmware.firmware_type, DeviceFirmware.is_latest.desc(), DeviceFirmware.release_date.desc()
    ).all()
    return jsonify({
        'device': {
            'id': d.id, 'name': d.device_name, 'brand': d.brand, 'model': d.model,
            'os_version': d.os_version or '', 'rule_version': d.rule_version or '',
        },
        'firmwares': [{
            'id': fw.id, 'firmware_type': fw.firmware_type, 'version': fw.version,
            'release_date': fw.release_date.isoformat() if fw.release_date else '',
            'is_latest': fw.is_latest,
            'changelog': fw.changelog, 'download_url': fw.download_url,
            'upgrade_guide': fw.upgrade_guide,
        } for fw in fws],
    })


