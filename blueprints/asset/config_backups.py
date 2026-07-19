# -*- coding: utf-8 -*-
"""设备配置备份 / 采集占位 (V14)"""
import os
from datetime import date
from flask import (render_template, request, redirect, url_for,
                   flash, jsonify, current_app)
from flask_login import login_required, current_user
from models import (Device, db, DeviceConfigBackup)
from utils.permission import require_permission
from utils.decorators import api_view
from blueprints.asset import asset_bp


# ============================ 配置备份（V14） ============================
def _compute_config_diff(text_a, text_b):
    """逐行差异：使用 difflib.SequenceMatcher 计算 equal/delete/insert/replace 标记，
    返回 [{tag, line_a, line_b}, ...]，与 templates/devices/config_backups.html 的渲染契约一致。"""
    import difflib
    lines_a = (text_a or '').splitlines()
    lines_b = (text_b or '').splitlines()
    result = []
    matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                result.append({'tag': 'equal', 'line_a': lines_a[i1 + k], 'line_b': lines_b[j1 + k]})
        elif tag == 'delete':
            for k in range(i1, i2):
                result.append({'tag': 'delete', 'line_a': lines_a[k], 'line_b': ''})
        elif tag == 'insert':
            for k in range(j1, j2):
                result.append({'tag': 'insert', 'line_a': '', 'line_b': lines_b[k]})
        elif tag == 'replace':
            max_len = max(i2 - i1, j2 - j1)
            for k in range(max_len):
                la = lines_a[i1 + k] if k < (i2 - i1) else ''
                lb = lines_b[j1 + k] if k < (j2 - j1) else ''
                result.append({'tag': 'replace', 'line_a': la, 'line_b': lb})
    return result


@asset_bp.route('/devices/<int:id>/config-backups')
@login_required
@require_permission('device:view')
def device_config_backups(id):
    d = Device.query.get_or_404(id)
    backups = DeviceConfigBackup.query.filter_by(device_id=id)\
        .order_by(DeviceConfigBackup.id.desc()).all()
    diff_lines = None
    a_id = request.args.get('a', type=int)
    b_id = request.args.get('b', type=int)
    if a_id and b_id and a_id != b_id:
        ba = DeviceConfigBackup.query.filter_by(id=a_id, device_id=id).first()
        bb = DeviceConfigBackup.query.filter_by(id=b_id, device_id=id).first()
        if ba and bb:
            diff_lines = _compute_config_diff(ba.config_content or '', bb.config_content or '')
    return render_template('devices/config_backups.html',
                           device=d, backups=backups,
                           diff_lines=diff_lines, a_id=a_id, b_id=b_id)


@asset_bp.route('/devices/<int:id>/config-backups/add', methods=['POST'])
@login_required
@require_permission('device:edit')
def device_config_backup_add(id):
    import hashlib
    from werkzeug.utils import secure_filename
    Device.query.get_or_404(id)  # 设备不存在则 404
    content = request.form.get('config_content', '')
    backup_type = request.form.get('backup_type', '运行配置')
    backup_method = request.form.get('backup_method', '手动输入')

    # 文件上传（可选）
    file_path = ''
    f = request.files.get('config_file')
    if f and f.filename:
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'configs', str(id))
        os.makedirs(upload_dir, exist_ok=True)
        safe_name = secure_filename(f.filename) or 'config.txt'
        # 防止重名覆盖：附加时间戳
        from datetime import datetime as _dt
        ts = _dt.now().strftime('%Y%m%d_%H%M%S')
        name_base, name_ext = os.path.splitext(safe_name)
        safe_name = f'{name_base}_{ts}{name_ext}'
        full_path = os.path.join(upload_dir, safe_name)
        f.save(full_path)
        file_path = f'uploads/configs/{id}/{safe_name}'
        backup_method = '文件上传'
        # 若用户没填内容，从文件读取
        if not content:
            try:
                with open(full_path, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
            except Exception:
                pass

    if not content and not file_path:
        flash('请填写配置内容或上传配置文件', 'warning')
        return redirect(url_for('asset.device_config_backups', id=id))

    checksum = hashlib.md5(content.encode('utf-8')).hexdigest() if content else ''

    backup = DeviceConfigBackup(
        device_id=id,
        backup_type=backup_type,
        config_content=content,
        backup_method=backup_method,
        backup_date=date.today(),
        file_path=file_path,
        checksum=checksum,
        created_by=getattr(current_user, 'realname', None) or current_user.username,
    )
    db.session.add(backup)
    db.session.commit()
    flash('配置备份已保存', 'success')
    return redirect(url_for('asset.device_config_backups', id=id))


@asset_bp.route('/devices/<int:id>/config-backups/<int:bid>/delete', methods=['POST'])
@login_required
@require_permission('device:delete')
def device_config_backup_delete(id, bid):
    backup = DeviceConfigBackup.query.filter_by(id=bid, device_id=id).first_or_404()
    # 删关联文件
    if backup.file_path:
        full = os.path.join(current_app.root_path, 'static', backup.file_path.replace('/', os.sep))
        if os.path.exists(full):
            try:
                os.remove(full)
            except Exception:
                pass
    db.session.delete(backup)
    db.session.commit()
    flash('配置备份已删除', 'success')
    return redirect(url_for('asset.device_config_backups', id=id))


@asset_bp.route('/devices/<int:id>/config-backups/compare')
@login_required
@require_permission('device:view')
def device_config_backup_compare(id):
    """compareForm 使用 GET 提交两个 v 复选框值；这里转成 ?a=&b= 重定向到列表页统一渲染。"""
    vs = request.args.getlist('v')
    a = vs[0] if len(vs) >= 1 else request.args.get('a')
    b = vs[1] if len(vs) >= 2 else request.args.get('b')
    if a and b:
        return redirect(url_for('asset.device_config_backups', id=id, a=a, b=b))
    flash('请勾选两个版本进行对比', 'warning')
    return redirect(url_for('asset.device_config_backups', id=id))


@asset_bp.route('/devices/<int:id>/collect')
@login_required
@require_permission('device:edit')
def device_collect(id):
    """从设备采集（SSH/Telnet/SNMP）— 占位实现，提示用户使用文件上传。"""
    d = Device.query.get_or_404(id)
    flash('远程采集功能尚未启用，请使用「文件上传」或「手动输入」方式新增备份。', 'info')
    return redirect(url_for('asset.device_config_backups', id=d.id))


@asset_bp.route('/api/devices/<int:id>/config-backups/upload-from-inspection', methods=['POST'])
@login_required
@require_permission('device:edit')
@api_view
def api_config_backup_upload(id):
    """巡检表单中 config_backup 字段类型上传配置文件时调用，自动创建一条 DeviceConfigBackup 记录。"""
    import hashlib
    from werkzeug.utils import secure_filename
    Device.query.get_or_404(id)
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
