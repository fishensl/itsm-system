# -*- coding: utf-8 -*-
"""数据备份/恢复蓝图：全局配置 + 数据导出/导入

挂到系统设置页，admin 权限。导出包含全量业务数据 + 上传文件 + AES 密钥，
便于服务器迁移后一键恢复。属高敏感操作，必须 admin + 二次确认 + CSRF。
"""
import os
import io
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, send_file, current_app, jsonify, abort)
from flask_login import login_required, current_user
from models import db
from utils.permission import admin_required
from utils.data_io import build_export_zip, perform_import

backup_bp = Blueprint('backup', __name__)


@backup_bp.route('/system/backup')
@login_required
@admin_required
def backup_page():
    """备份/恢复页面"""
    # 当前库概要
    from models import (User, Customer, Device, Ticket, Inspection, Fault,
                        KnowledgeBase, SparePart, Topology)
    stats = {
        'user': User.query.count(),
        'customer': Customer.query.count(),
        'device': Device.query.count(),
        'ticket': Ticket.query.count(),
        'inspection': Inspection.query.count(),
        'fault': Fault.query.count(),
        'kb': KnowledgeBase.query.count(),
        'spare': SparePart.query.count(),
        'topology': Topology.query.count(),
    }
    # 上传文件体积概估
    root = os.path.abspath(current_app.root_path)
    file_size = 0
    for _, disk_rel in [('reports', 'reports'), ('uploads', 'uploads'),
                        ('static_uploads', os.path.join('static', 'uploads'))]:
        d = os.path.join(root, disk_rel)
        if os.path.isdir(d):
            for dp, _ds, fs in os.walk(d):
                for fn in fs:
                    try:
                        file_size += os.path.getsize(os.path.join(dp, fn))
                    except OSError:
                        pass
    return render_template('system/backup.html', stats=stats,
                           file_size_mb=round(file_size / 1024 / 1024, 1))


@backup_bp.route('/system/backup/export', methods=['POST'])
@login_required
@admin_required
def backup_export():
    """导出全量备份包（zip，流式下载）"""
    buf, size, manifest = build_export_zip()
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    download_name = f'itsm_backup_{ts}.zip'
    current_app.logger.info('用户 [%s] 导出数据备份包 %s（%s 字节，%d 表）',
                            current_user.username, download_name, size,
                            sum(manifest.get('table_counts', {}).values()))
    return send_file(
        buf,
        mimetype='application/zip',
        as_attachment=True,
        download_name=download_name,
    )


@backup_bp.route('/system/backup/import', methods=['POST'])
@login_required
@admin_required
def backup_import():
    """导入备份包：清空并覆盖现有数据（危险操作，需二次确认）"""
    confirm = request.form.get('confirm')
    if confirm != '我确认覆盖':
        flash('请输入"我确认覆盖"以二次确认，导入未执行', 'danger')
        return redirect(url_for('backup.backup_page'))

    f = request.files.get('backup_file')
    if not f or not f.filename or not f.filename.lower().endswith('.zip'):
        flash('请选择 .zip 备份包', 'danger')
        return redirect(url_for('backup.backup_page'))

    restore_key = request.form.get('restore_secret_key') == '1'
    zip_bytes = f.read()

    try:
        result = perform_import(zip_bytes, restore_secret_key=restore_key)
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        current_app.logger.exception('导入备份失败')
        flash(f'导入失败：{e}', 'danger')
        return redirect(url_for('backup.backup_page'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('导入备份失败')
        flash(f'导入失败：{e}', 'danger')
        return redirect(url_for('backup.backup_page'))

    # 清空权限缓存（数据已全量替换）
    try:
        from utils.permission import invalidate_role
        from models import Role
        for r in Role.query.all():
            invalidate_role(r.code)
    except Exception:
        pass

    msg = (f'导入成功：恢复 {result["restored_rows"]} 行数据、'
           f'{result["restored_files"]} 个文件')
    if result['secret_key_restored']:
        msg += '，已还原加密密钥'
    else:
        msg += '（未还原加密密钥，如设备密码无法解密请重新导入并勾选）'
    if result['warnings']:
        msg += '。警告：' + '；'.join(result['warnings'][:3])
    flash(msg, 'success')
    current_app.logger.info('用户 [%s] 导入备份：%s', current_user.username, msg)
    return redirect(url_for('backup.backup_page'))
