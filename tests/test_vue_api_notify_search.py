# -*- coding: utf-8 -*-
"""P3 通知中心 + 全局搜索 API"""
import pytest

from models import db, Customer, Device, Ticket, KnowledgeBase, User, Notification


@pytest.fixture()
def seed(app):
    with app.app_context():
        c = Customer(name='搜索客户A', contact_person='张三', phone='13800001111')
        db.session.add(c)
        db.session.flush()
        db.session.add(Device(customer_id=c.id, device_name='搜索交换机', ip_address='10.1.1.1'))
        db.session.add(Ticket(number='WO-SEARCH-1', title='搜索工单', customer_id=c.id))
        db.session.add(KnowledgeBase(title='搜索知识条目', category='故障案例'))
        op = User.query.filter_by(username='op').first()
        db.session.add(Notification(user_id=op.id, category='ticket', title='有新工单',
                                    content='测试工单', link='/app/tickets/1', is_read=False))
        db.session.add(Notification(user_id=op.id, category='system', title='已读通知',
                                    is_read=True))
        db.session.commit()
        yield {'c': c.id}


class TestNotifications:
    def test_control_identical(self, op_client, admin_client, seed, app):
        """回归：多角色 client 交替请求时身份隔离（Flask-Login g 缓存补丁）"""
        assert op_client.get('/api/auth/me').get_json()['data']['username'] == 'op'
        assert admin_client.get('/api/auth/me').get_json()['data']['username'] == 'admin'
        r = admin_client.post('/api/notifications/read', json={})
        assert r.status_code == 200
        assert op_client.get('/api/notifications/unread-count').get_json()['data']['unread'] == 1

    def test_list_and_unread(self, op_client, seed):
        r = op_client.get('/api/notifications')
        body = r.get_json()
        assert body['code'] == 0
        assert len(body['data']['items']) == 2
        r = op_client.get('/api/notifications/unread-count')
        assert r.get_json()['data']['unread'] == 1

    def test_mark_one_read(self, op_client, seed, app):
        with app.app_context():
            nid = Notification.query.filter_by(title='有新工单').first().id
        r = op_client.post('/api/notifications/read', json={'ids': [nid]})
        assert r.status_code == 200
        assert op_client.get('/api/notifications/unread-count').get_json()['data']['unread'] == 0

    def test_mark_all_read(self, op_client, seed, app):
        op_client.post('/api/notifications/read', json={})
        assert op_client.get('/api/notifications/unread-count').get_json()['data']['unread'] == 0

    def test_cannot_read_others(self, op_client, admin_client, seed, app):
        """只能已读自己的通知（admin 的已读不影响 op）"""
        r = admin_client.post('/api/notifications/read', json={})
        assert r.status_code == 200
        assert op_client.get('/api/notifications/unread-count').get_json()['data']['unread'] == 1

    def test_requires_login(self, client):
        assert client.get('/api/notifications').status_code == 401


class TestGlobalSearch:
    def test_search_all_types(self, op_client, seed):
        r = op_client.get('/api/search', query_string={'q': '搜索'})
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert len(data['devices']) == 1
        assert len(data['customers']) == 1
        assert len(data['tickets']) == 1
        assert len(data['knowledge']) == 1

    def test_short_query_empty(self, op_client):
        r = op_client.get('/api/search', query_string={'q': 'a'})
        assert r.get_json()['data']['devices'] == []

    def test_empty_query(self, op_client):
        r = op_client.get('/api/search', query_string={'q': ''})
        assert r.get_json()['code'] == 0

    def test_permission_filtered(self, viewer_client, seed):
        r = viewer_client.get('/api/search', query_string={'q': '搜索'})
        assert r.status_code == 200
        assert r.get_json()['code'] == 0

    def test_requires_login(self, client):
        assert client.get('/api/search', query_string={'q': 'x'}).status_code == 401


class TestTicketActionNotifiesAssignee:
    def test_assign_sends_notification(self, op_client, admin_client, seed, app):
        """admin 派单给 op → op 收到通知"""
        with app.app_context():
            t = Ticket(number='WO-NOTIFY-1', title='通知测试工单', status='待派单')
            db.session.add(t)
            db.session.commit()
            tid = t.id
        r = admin_client.post(f'/api/tickets/{tid}/action', json={
            'action': 'assign', 'assignee': 'op'})
        assert r.status_code == 200
        with app.app_context():
            op = User.query.filter_by(username='op').first()
            n = Notification.query.filter_by(user_id=op.id, category='ticket')\
                .order_by(Notification.id.desc()).first()
            assert n is not None
            assert '派' in n.title
            assert n.link == f'/app/tickets/{tid}'
