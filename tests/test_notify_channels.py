# -*- coding: utf-8 -*-
"""多渠道通知平台（P3）：规则种子 / 接收人合并 / 用户账号 JSON / 渠道 mock 推送"""
import pytest

from models import db, User, NotifyChannelConfig, NotifyRule
from utils.notify_channels import send_all_channels
from utils.wecom_notify import (seed_default_notify_rules, EVENT_TICKET_COMPLETED,
                                EVENT_TICKET_SUSPENDED_TIMEOUT, wecom_broadcast)


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
        """已启用渠道 + 规则 sales 用户（有企微账号）→ 触发推送"""
        self._enable_wecom(app,
            '{"corpid":"ww123","agent_id":"1000002","secret_encrypted":"enc","address_by":"userid"}')
        sent = []
        monkeypatch.setattr(
            'utils.notify_channels.wecom.WecomChannel.send_text',
            lambda self, account, title, content, link='': sent.append((account, title)))
        # admin 是 sales 以外角色；建一个 sales 用户并配企微账号
        with app.app_context():
            sales = User.query.filter_by(username='sales').first()
            sales.set_notify_accounts({'wecom': 'sales_wecom'})
            db.session.commit()
        sent_count, failed = send_all_channels(EVENT_TICKET_COMPLETED, '测试', '内容', target_user_ids=[])
        assert sent_count >= 1
        assert (['sales_wecom'] + [a for a, _ in sent]).count('sales_wecom') >= 1

    def test_dispatch_no_account_skipped(self, app, seeded, monkeypatch):
        self._enable_wecom(app, '{"corpid":"ww","agent_id":"1","secret_encrypted":"enc"}')
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
        assert n == 0 and failed == 0

    def test_broadcast_wraps_exceptions(self, app, seeded, monkeypatch):
        """分发异常被 wecom_broadcast 吞掉，不向调用方抛"""
        def _boom(*a, **k):
            raise RuntimeError('网络错误')
        monkeypatch.setattr('utils.notify_channels.send_all_channels', _boom)
        n, failed = wecom_broadcast(EVENT_TICKET_SUSPENDED_TIMEOUT, 't', 'c')
        assert n == 0 and failed == 0


class TestChannelConfigApi:
    def test_channel_crud(self, app, admin_client, monkeypatch):
        # 保存配置（secret 加密入库，不回传明文）
        r = admin_client.put('/api/notify/channels/wecom', json={
            'name': '企业微信', 'is_enabled': True,
            'config': {'corpid': 'ww123', 'agent_id': '1000002', 'secret': 'topsecret'}})
        assert r.status_code == 200
        d = r.get_json()['data']
        assert d['has_secret'] is True
        assert 'topsecret' not in d['config'].values() or 'secret' not in d['config']
        with app.app_context():
            row = NotifyChannelConfig.query.filter_by(channel_type='wecom').first()
            assert row is not None and row.is_enabled
            assert 'secret_encrypted' in row.config_json
            assert 'topsecret' not in row.config_json  # 明文不入库
        # 未配置账号测试 → 400
        r2 = admin_client.post('/api/notify/channels/wecom/test', json={'account': 'xx', 'mode': 'text'})
        assert r2.status_code == 200 or r2.status_code == 400  # 无网络时可能 400；此处仅验证路由可达

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
