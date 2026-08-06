# -*- coding: utf-8 -*-
"""设备 JSON API / 导出（SSR CRUD 与导入已由 Vue SPA /api/v2/* 接管）"""
import json
import os
from datetime import date
from flask import request, jsonify, send_from_directory, current_app
from flask_login import login_required, current_user
from models import (Device, PasswordHistory)
from utils.crypto import decrypt_password
from utils.permission import require_permission
from utils.decorators import api_view
from blueprints.asset import asset_bp


# ============================ API: 设备 JSON ============================
@asset_bp.route('/api/devices/<int:id>')
@login_required
@require_permission('device:view')
@api_view
def api_device_get(id):
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
        'interface': json.loads(d.interface) if d.interface and d.interface.startswith('[') else (
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


# ============================ 设备导出 ============================
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
