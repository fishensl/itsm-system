# -*- coding: utf-8 -*-
"""多渠道通知平台（P3）：规则种子 / 接收人合并 / 用户账号 JSON / 渠道 mock 推送"""
import pytest

from models import db, User, NotifyChannelConfig, NotifyRule
from utils.notify_channels import send_all_channels
from utils.wecom_notify import (seed_default_notify_rules, EVENT_TICKET_ASSIGN,
                                EVENT_TICKET_COMPLETED,
                                EVENT_TICKET_SUSPENDED_TIMEOUT,
                                EVENT_INSPECTION_STATUS_CHANGED, wecom_broadcast)


@pytest.fixture()
def seeded(app):
    """种入默认规则并给用户配置通知账号"""
    with app.app_context():
        seed_default_notify_rules()
        admin = User.query.filter_by(username='admin').first()
        admin.set_notify_accounts({'wecom': 'admin_wecom'})
        db.session.commit()
        yield


class TestUserNotifyAccounts:
    def test_set_and_get(self, app):
        with app.app_context():
            admin = User.query.filter_by(username='admin').first()
            admin.set_notify_accounts({'wecom': 'zhangsan', 'dingtalk': '13800138000'})
            db.session.commit()
            acc = User.query.get(admin.id).notify_accounts()
            assert acc == {'wecom': 'zhangsan', 'dingtalk': '13800138000'}

    def test_empty_default(self, app):
        with app.app_context():
            u = User.query.filter_by(username='viewer').first()
            assert u.notify_accounts() == {}


class TestRuleSeed:
    def test_seed_defaults(self, app, seeded):
        with app.app_context():
            completed = NotifyRule.query.filter_by(event_type=EVENT_TICKET_COMPLETED).first()
            assert completed is not None and completed.is_enabled
            assert completed.recipients_json and 'sales' in completed.recipients_json
            status_changed = NotifyRule.query.filter_by(
                event_type=EVENT_INSPECTION_STATUS_CHANGED).first()
            assert status_changed is not None and status_changed.is_enabled
            assert status_changed.label == '巡检任务状态变更'

    def test_seed_idempotent(self, app, seeded):
        with app.app_context():
            seed_default_notify_rules()
            count = NotifyRule.query.filter_by(event_type=EVENT_TICKET_COMPLETED).count()
            assert count == 1

    def test_seed_channels_three_default_disabled(self, app, seeded):
        """渠道种子：wecom/dingtalk/feishu 三条，默认停用（填凭据后启用）"""
        with app.app_context():
            from models import NotifyChannelConfig
            rows = NotifyChannelConfig.query.order_by(NotifyChannelConfig.sort_order).all()
            types = [r.channel_type for r in rows]
            assert types == ['wecom', 'dingtalk', 'feishu']
            assert all(r.is_enabled is False for r in rows)
            assert all((r.config_json or '') == '{}' for r in rows)

    def test_seed_channels_idempotent(self, app, seeded):
        with app.app_context():
            from models import NotifyChannelConfig
            seed_default_notify_rules()
            assert NotifyChannelConfig.query.count() == 3


class TestChannelDispatch:
    @staticmethod
    def _enable_wecom(app, config_json):
        """更新已种入的 wecom 渠道为启用（种子已存在，唯一约束下不能重复 INSERT）"""
        with app.app_context():
            from models import NotifyChannelConfig
            row = NotifyChannelConfig.query.filter_by(channel_type='wecom').first()
            row.is_enabled = True
            row.config_json = config_json
            db.session.commit()

    def test_send_all_channels_mock(self, app, seeded, monkeypatch):
        """企业微信群 Webhook 按渠道广播，同一事件只发送一次。"""
        self._enable_wecom(app,
            '{"webhook_url_encrypted":"enc"}')
        sent = []
        monkeypatch.setattr(
            'utils.notify_channels.wecom.WecomChannel.send_text',
            lambda self, account, title, content, link='': sent.append((account, title)))
        # admin 是 sales 以外角色；建一个 sales 用户并配企微账号
        with app.app_context():
            sales = User.query.filter_by(username='sales').first()
            sales.set_notify_accounts({'wecom': 'sales_wecom'})
            db.session.commit()
        with app.app_context():
            admin_id = User.query.filter_by(username='admin').first().id
        sent_count, failed = send_all_channels(
            EVENT_TICKET_COMPLETED, '测试', '内容', target_user_ids=[admin_id])
        assert sent_count == 1 and failed == 0
        assert sent == [('', '测试')]

    def test_wecom_group_webhook_does_not_require_user_account(
            self, app, seeded, monkeypatch):
        self._enable_wecom(app, '{"webhook_url_encrypted":"enc"}')
        sent = []
        monkeypatch.setattr(
            'utils.notify_channels.wecom.WecomChannel.send_text',
            lambda self, account, title, content, link='': sent.append(account))
        # 无人配企微账号 → 跳过
        with app.app_context():
            for u in User.query.all():
                u.set_notify_accounts({})
            db.session.commit()
        n, failed = send_all_channels(EVENT_TICKET_COMPLETED, 't', 'c', target_user_ids=[])
        assert n == 1 and failed == 0
        assert sent == ['']

    def test_wecom_group_webhook_skips_missing_target_user(
            self, app, seeded, monkeypatch):
        self._enable_wecom(app, '{"webhook_url_encrypted":"enc"}')
        sent = []
        monkeypatch.setattr(
            'utils.notify_channels.wecom.WecomChannel.send_text',
            lambda self, account, title, content, link='': sent.append(account))
        n, failed = send_all_channels(
            EVENT_TICKET_ASSIGN, 't', 'c', target_user_ids=[999999])
        assert n == 0 and failed == 0
        assert sent == []

    def test_broadcast_wraps_exceptions(self, app, seeded, monkeypatch):
        """分发异常被 wecom_broadcast 吞掉，不向调用方抛"""
        def _boom(*a, **k):
            raise RuntimeError('网络错误')
        monkeypatch.setattr('utils.notify_channels.send_all_channels', _boom)
        n, failed = wecom_broadcast(EVENT_TICKET_SUSPENDED_TIMEOUT, 't', 'c')
        assert n == 0 and failed == 0

    def test_broadcast_expands_relative_link_from_current_request(self, app, monkeypatch):
        captured = []
        monkeypatch.setattr(
            'utils.notify_channels.send_all_channels',
            lambda *args, **kwargs: captured.append((args, kwargs)) or (1, 0))
        with app.test_request_context(
                '/api/tickets/1/action', base_url='http://172.16.123.124:5000'):
            wecom_broadcast(
                EVENT_TICKET_ASSIGN, '标题', '正文', '/app/tickets/1',
                target_user_ids=[1], mode='markdown')
        assert captured[0][0][3] == 'http://172.16.123.124:5000/app/tickets/1'


class TestChannelConfigApi:
    def test_channel_crud(self, app, admin_client, monkeypatch):
        # Webhook 加密入库，不回传明文。
        webhook = ('https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key='
                   '12345678-1234-1234-1234-123456789012')
        r = admin_client.put('/api/notify/channels/wecom', json={
            'name': '企业微信', 'is_enabled': True,
            'config': {'webhook_url': webhook}})
        assert r.status_code == 200
        d = r.get_json()['data']
        assert d['has_secret'] is True
        assert 'webhook_url' not in d['config']
        with app.app_context():
            row = NotifyChannelConfig.query.filter_by(channel_type='wecom').first()
            assert row is not None and row.is_enabled
            assert 'webhook_url_encrypted' in row.config_json
            assert webhook not in row.config_json
        monkeypatch.setattr(
            'utils.notify_channels.wecom.WecomChannel.send_test',
            lambda self, account, mode: (True, '发送成功'))
        # 群机器人测试无需指定 userid。
        r2 = admin_client.post(
            '/api/notify/channels/wecom/test', json={'account': '', 'mode': 'text'})
        assert r2.status_code == 200

    def test_wecom_rejects_non_official_webhook(self, admin_client):
        r = admin_client.put('/api/notify/channels/wecom', json={
            'name': '企业微信', 'is_enabled': True,
            'config': {'webhook_url': 'https://example.com/webhook?key=leak'},
        })
        assert r.status_code == 400
        assert '企业微信群机器人' in r.get_json()['message']

    def test_requires_permission(self, app, op_client):
        assert op_client.get('/api/notify/channels').status_code == 403
        assert op_client.get('/api/notify/rules').status_code == 403

    def test_rules_save(self, app, admin_client):
        r = admin_client.post('/api/notify/rules', json={
            'event_type': EVENT_TICKET_COMPLETED, 'is_enabled': True,
            'roles': ['sales'], 'users': [1]})
        assert r.status_code == 200
        with app.app_context():
            rule = NotifyRule.query.filter_by(event_type=EVENT_TICKET_COMPLETED).first()
            assert 'sales' in rule.recipients_json and '"users"' in rule.recipients_json

    def test_rules_list_returns_chinese_role_options(self, admin_client):
        response = admin_client.get('/api/notify/rules')
        assert response.status_code == 200
        labels = {item['code']: item['name']
                  for item in response.get_json()['data']['role_options']}
        assert labels['admin'] == '系统管理员'
        assert labels['operator'] == '运维工程师'

    def test_rules_batch_save_is_atomic(self, app, admin_client):
        response = admin_client.put('/api/notify/rules', json={'rules': [
            {'event_type': EVENT_TICKET_COMPLETED, 'is_enabled': False,
             'roles': ['sales'], 'users': []},
            {'event_type': EVENT_TICKET_ASSIGN, 'is_enabled': True,
             'roles': ['operator'], 'users': []},
        ]})
        assert response.status_code == 200
        assert response.get_json()['data']['count'] == 2
        with app.app_context():
            completed = NotifyRule.query.filter_by(event_type=EVENT_TICKET_COMPLETED).one()
            assert completed.is_enabled is False
            before = completed.recipients_json
        rejected = admin_client.put('/api/notify/rules', json={'rules': [
            {'event_type': EVENT_TICKET_COMPLETED, 'is_enabled': True,
             'roles': ['sales'], 'users': []},
            {'event_type': 'unknown_event', 'is_enabled': True,
             'roles': [], 'users': []},
        ]})
        assert rejected.status_code == 400
        with app.app_context():
            completed = NotifyRule.query.filter_by(event_type=EVENT_TICKET_COMPLETED).one()
            assert completed.is_enabled is False
            assert completed.recipients_json == before

    def test_rules_invalid_type(self, app, admin_client):
        r = admin_client.post('/api/notify/rules', json={'event_type': 'not_exist'})
        assert r.status_code == 400


class TestDingTalkFeishuAdapters:
    """钉钉/飞书适配器框架：消息体构造与鉴权请求（mock，不依赖外网）"""

    def test_dingtalk_token_and_send(self, monkeypatch):
        from utils.notify_channels.dingtalk import DingTalkChannel
        ch = DingTalkChannel({}, {
            'app_key': 'dk', 'app_secret_encrypted': 'x', 'agent_id': '1001',
            'address_by': 'userid'})
        calls = []
        get_calls = []
        import requests
        class FakeResp:
            def json(self):
                return {'access_token': 'TOK'}
        def fake_get(url, **kw):
            get_calls.append(url)
            return FakeResp()
        monkeypatch.setattr(requests, 'get', fake_get)
        def _req(url, payload=None, headers=None, method='POST'):
            calls.append((url, payload))
            return {}
        monkeypatch.setattr(ch, '_request_json', _req)
        ch.send_text('zhangsan', '标题', '内容')
        assert any('/gettoken' in u for u in get_calls)   # token 走 requests.get
        send_payload = calls[-1][1]                        # 最后一条 = asyncsend_v2
        assert send_payload['userid_list'] == 'zhangsan'
        assert send_payload['msg']['msgtype'] == 'text'

    def test_dingtalk_mobile_resolve(self, monkeypatch):
        from utils.notify_channels.dingtalk import DingTalkChannel
        ch = DingTalkChannel({}, {'app_key': 'k', 'app_secret_encrypted': 'x',
                                  'agent_id': '1', 'address_by': 'mobile'})
        monkeypatch.setattr(ch, 'get_access_token', lambda: 'T')
        monkeypatch.setattr(ch, '_mobile_to_userid', lambda m: 'uid_from_mobile')
        assert ch._resolve_userid('13800138000') == 'uid_from_mobile'

    def test_feishu_token_and_post(self, monkeypatch):
        from utils.notify_channels.feishu import FeishuChannel
        ch = FeishuChannel({}, {'app_id': 'fk', 'app_secret_encrypted': 'x'})
        calls = []
        def _req(url, payload=None, headers=None, method='POST'):
            calls.append((url, payload, headers or {}))
            if '/auth/v3/' in url:
                return {'tenant_access_token': 'FT', 'expire': 7200}
            return {'code': 0}
        monkeypatch.setattr(ch, '_request_json', _req)
        monkeypatch.setattr(ch, '_resolve_receive_id', lambda a: 'ou_123')
        ch.send_markdown('手机号', '标题', '正文', 'https://x')
        msgs = [(u, p, h) for u, p, h in calls if '/im/v1/messages' in u]
        assert msgs and 'Bearer FT' in msgs[0][2].get('Authorization', '')
        assert 'post' in msgs[0][1]['msg_type']

    def test_feishu_mobile_resolve(self, monkeypatch):
        from utils.notify_channels.feishu import FeishuChannel
        ch = FeishuChannel({}, {'app_id': 'k', 'app_secret_encrypted': 'x'})
        monkeypatch.setattr(ch, 'get_tenant_access_token', lambda: 'T')
        monkeypatch.setattr(ch, '_mobile_to_user_id', lambda m: 'u_1')
        assert ch._resolve_receive_id('138') == 'u_1'

    def test_registry_contains_three(self):
        from utils.notify_channels import CHANNEL_TYPES, channel_class
        assert set(CHANNEL_TYPES) == {'wecom', 'dingtalk', 'feishu'}
        for t in CHANNEL_TYPES:
            assert channel_class(t) is not None

    def test_disabled_channels_not_dispatched(self, app, seeded, monkeypatch):
        """未启用渠道（种子的 wecom/dingtalk/feishu 均默认停用）不参与分发"""
        from utils.notify_channels import send_all_channels
        monkeypatch.setattr('utils.notify_channels.wecom.WecomChannel.send_text',
                            lambda self, a, t, c, link='': None)
        n, _ = send_all_channels(EVENT_TICKET_COMPLETED, 't', 'c', target_user_ids=[])
        assert n == 0  # 无启用渠道 → 不发


class TestWecomWebhookAdapter:
    def test_text_and_markdown_use_group_robot_payload(self, monkeypatch):
        from utils.notify_channels.wecom import WecomChannel
        webhook = ('https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key='
                   '12345678-1234-1234-1234-123456789012')
        channel = WecomChannel({}, {'webhook_url_encrypted': 'encrypted'})
        calls = []
        monkeypatch.setattr(channel, '_webhook_url', lambda: webhook)
        monkeypatch.setattr(
            channel, '_request_json',
            lambda url, payload=None, **kwargs: calls.append((url, payload)) or {})

        channel.send_text('', '标题', '正文', '/app/tickets/1')
        channel.send_markdown('', '标题2', '正文2')

        assert calls[0][0] == webhook
        assert calls[0][1] == {
            'msgtype': 'text',
            'text': {'content': '标题\n正文\n查看详情：/app/tickets/1'},
        }
        assert calls[1][1]['msgtype'] == 'markdown'
        assert '**标题2**' in calls[1][1]['markdown']['content']

    @pytest.mark.parametrize('url', [
        'http://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x',
        'https://example.com/cgi-bin/webhook/send?key=x',
        'https://qyapi.weixin.qq.com/cgi-bin/webhook/send',
        'https://qyapi.weixin.qq.com@evil.example/cgi-bin/webhook/send?key=x',
    ])
    def test_webhook_validation_blocks_unsafe_urls(self, url):
        from utils.notify_channels.base import ChannelError
        from utils.notify_channels.wecom import validate_webhook_url
        with pytest.raises(ChannelError):
            validate_webhook_url(url)
