# -*- coding: utf-8 -*-
"""批量业务导出必须写入 audit_logs。"""
import pytest

from models import AuditLog


@pytest.mark.parametrize(('url', 'action'), [
    ('/api/v2/devices/export', 'device:export'),
    ('/api/v2/customers/export', 'customer:export'),
    ('/api/inspections/export', 'inspection:export'),
    ('/api/tickets/export', 'ticket:export'),
    ('/api/faults/export', 'fault:export'),
    ('/api/spare-parts/export', 'spare:export'),
])
def test_bulk_export_writes_audit_log(app, admin_client, url, action):
    payload = {'preset': 'asset'} if url == '/api/v2/devices/export' else {}
    response = admin_client.post(url, json=payload)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['code'] == 0
    with app.app_context():
        row = AuditLog.query.filter_by(action=action).order_by(AuditLog.id.desc()).first()
        assert row is not None
        assert row.user_id is not None
        assert '"rows":' in row.detail
        assert '"columns":' in row.detail
        assert 'content' not in row.detail
