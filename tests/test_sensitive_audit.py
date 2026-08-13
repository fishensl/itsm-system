# -*- coding: utf-8 -*-
"""P0 敏感配置与 RBAC 操作必须写入 audit_logs。"""
from models import AuditLog, User


def _actions(app):
    with app.app_context():
        return {row.action: row.detail for row in AuditLog.query.all()}


def test_ai_config_crud_and_test_are_audited(admin_client, app, monkeypatch):
    created = admin_client.post('/api/ai-config', json={
        'provider': 'OpenAI', 'model_name': 'audit-model',
        'api_endpoint': 'https://example.invalid/v1', 'api_key': 'super-secret-key',
    })
    cid = created.get_json()['data']['id']
    assert admin_client.put(
        f'/api/ai-config/{cid}', json={'model_name': 'audit-model-2'}).status_code == 200
    monkeypatch.setattr(
        'utils.ai_client.AIClient.test_connection', lambda self: (True, 'ok'))
    assert admin_client.post(f'/api/ai-config/{cid}/test').status_code == 200
    assert admin_client.delete(f'/api/ai-config/{cid}').status_code == 200
    actions = _actions(app)
    assert {'ai:create', 'ai:update', 'ai:test', 'ai:delete'} <= set(actions)
    assert all('super-secret-key' not in detail for detail in actions.values())


def test_role_matrix_and_user_overrides_are_audited(admin_client, app):
    created = admin_client.post('/api/roles', json={
        'code': 'audit_role', 'name': '审计测试角色'})
    role_id = created.get_json()['data']['id']
    assert admin_client.put(f'/api/roles/{role_id}', json={
        'name': '审计测试角色2', 'description': '', 'sort_order': 90,
        'is_active': True}).status_code == 200
    assert admin_client.put(f'/api/roles/{role_id}/permissions', json={
        'codes': ['dashboard:view', 'device:view']}).status_code == 200
    with app.app_context():
        uid = User.query.filter_by(username='op').first().id
    assert admin_client.put(f'/api/users/{uid}/permissions', json={
        'overrides': {'customer:view': {'grant_type': 'grant', 'remark': '临时授权'}}
    }).status_code == 200
    assert admin_client.delete(f'/api/roles/{role_id}').status_code == 200
    actions = _actions(app)
    assert {'role:create', 'role:update', 'role:permissions', 'role:delete',
            'user:permissions'} <= set(actions)


def test_access_control_and_notification_config_are_audited(
        admin_client, app, monkeypatch):
    assert admin_client.put('/api/system/access-control', json={
        'trusted_networks': ['10.0.0.0/8']}).status_code == 200
    assert admin_client.put('/api/notify/channels/wecom', json={
        'name': '企业微信', 'is_enabled': False,
        'config': {'corp_id': 'corp', 'secret': 'notify-secret'},
    }).status_code == 200

    class FakeChannel:
        def __init__(self, *_args, **_kwargs):
            pass

        def send_test(self, _account, _mode):
            return True, 'ok'

    monkeypatch.setattr('utils.notify_channels.channel_class', lambda _kind: FakeChannel)
    assert admin_client.post('/api/notify/channels/wecom/test', json={
        'account': 'audit-user', 'mode': 'text'}).status_code == 200
    assert admin_client.post('/api/notify/rules', json={
        'event_type': 'contract_review', 'is_enabled': True,
        'roles': ['admin'], 'users': [],
    }).status_code == 200
    actions = _actions(app)
    assert {'system:access_control', 'notify:channel_save',
            'notify:channel_test', 'notify:rule_save'} <= set(actions)
    assert all('notify-secret' not in detail for detail in actions.values())
