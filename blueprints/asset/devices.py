# -*- coding: utf-8 -*-
"""设备密码兼容 API（设备详情与导出已由 Vue SPA /api/v2/* 接管）。"""
from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from models import (Device, PasswordHistory)
from utils.crypto import decrypt_password
from utils.permission import require_permission
from utils.decorators import api_view
from utils.access_control import client_ip
from utils.operation_token import require_op_token
from blueprints.asset import asset_bp


@asset_bp.route('/api/devices/<int:id>/reveal-password', methods=['POST'])
@login_required
@require_permission('device:reveal')
@require_op_token()
def api_device_reveal_password(id):
    """按需查看设备明文密码（当前密码或指定历史密码）。

    安全设计：
    - 独立权限码 device:reveal（admin/operator 默认持有）
    - POST + CSRF 保护（不豁免），Vue 请求拦截器自动带 X-CSRFToken
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
        current_user.username, d.device_name, d.id, kind, client_ip())
    from blueprints.vue_api_sys import audit_log
    audit_log('device:reveal', 'device', d.id, f'查看设备「{d.device_name}」{kind}(legacy)')
    from utils.security_events import note_password_reveal
    note_password_reveal(current_user.id, current_user.username, d.id, client_ip())
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
