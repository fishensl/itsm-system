# -*- coding: utf-8 -*-
"""设备配置备份上传 API（SSR 页面与 CRUD 已由 Vue SPA /api/devices/config-backup/* 接管）"""
import os
from datetime import date
from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from models import (Device, db, DeviceConfigBackup)
from utils.permission import require_permission
from blueprints.asset import asset_bp


@asset_bp.route('/api/devices/<int:id>/config-backups/upload-from-inspection', methods=['POST'])
@login_required
@require_permission('device:edit')
def api_config_backup_upload(id):
    """巡检表单中 config_backup 字段类型上传配置文件时调用，自动创建一条 DeviceConfigBackup 记录。"""
    import hashlib
    from werkzeug.utils import secure_filename
    from utils.customer_scope import require_device_access
    require_device_access(current_user, Device.query.get_or_404(id))
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': '未选择文件'}), 400
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'configs', str(id))
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = secure_filename(f.filename) or 'config.txt'
    from datetime import datetime as _dt
    ts = _dt.now().strftime('%Y%m%d_%H%M%S')
    name_base, name_ext = os.path.splitext(safe_name)
    safe_name = f'{name_base}_{ts}{name_ext}'
    full_path = os.path.join(upload_dir, safe_name)
    f.save(full_path)
    try:
        with open(full_path, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
    except Exception:
        content = ''
    checksum = hashlib.md5(content.encode('utf-8')).hexdigest() if content else ''
    version = (request.form.get('version') or '').strip()
    backup = DeviceConfigBackup(
        device_id=id,
        backup_type='运行配置',
        config_content=content,
        backup_method='巡检上传',
        backup_date=date.today(),
        file_path=f'uploads/configs/{id}/{safe_name}',
        checksum=checksum,
        created_by=(getattr(current_user, 'realname', None) or current_user.username) + (f' / {version}' if version else ''),
    )
    db.session.add(backup)
    db.session.commit()
    return jsonify({
        'success': True,
        'backup_id': backup.id,
        'checksum': checksum,
        'file_path': backup.file_path,
        'filename': safe_name,
    })
