# -*- coding: utf-8 -*-
"""设备固件版本库匹配 API（SSR 页面与 CRUD 已由 Vue SPA /api/firmwares/* 接管）"""
from flask import jsonify
from flask_login import login_required
from models import (Device, DeviceFirmware)
from utils.permission import require_permission
from blueprints.asset import asset_bp


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
