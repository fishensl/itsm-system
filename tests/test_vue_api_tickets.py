# -*- coding: utf-8 -*-
"""P2 工单 Vue API：列表/详情/创建(自接单)/状态机动作/删除"""
import pytest

from models import db, Customer, Ticket, TicketLog


@pytest.fixture()
def seed(app):
    with app.app_context():
        c = Customer(name='工单API客户')
        db.session.add(c)
        db.session.flush()
        t = Ticket(number='WO-TEST-001', title='测试工单', customer_id=c.id,
                   priority='高', status='待派单', created_by='admin')
        db.session.add(t)
        db.session.commit()
        yield {'c': c.id, 't': t.id}


class TestTicketList:
    def test_list_shape(self, op_client, seed):
        r = op_client.get('/api/tickets')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['total'] == 1
        assert data['items'][0]['customer_name'] == '工单API客户'
        assert data['items'][0]['status'] == '待派单'

    def test_filter_status(self, op_client, seed):
        r = op_client.get('/api/tickets', query_string={'status': '处理中'})
        assert r.get_json()['data']['total'] == 0
        r = op_client.get('/api/tickets', query_string={'status': '待派单'})
        assert r.get_json()['data']['total'] == 1

    def test_search(self, op_client, seed):
        r = op_client.get('/api/tickets', query_string={'search': 'WO-TEST'})
        assert r.get_json()['data']['total'] == 1


class TestTicketDetailAndLogs:
    def test_detail_includes_logs(self, op_client, seed):
        r = op_client.get(f"/api/tickets/{seed['t']}")
        body = r.get_json()
        assert body['code'] == 0
        assert body['data']['title'] == '测试工单'
        assert isinstance(body['data']['logs'], list)


class TestTicketStateMachine:
    def test_full_flow(self, op_client, seed, app):
        """派单→接单→提交→审核通过→验收通过→关闭"""
        steps = [
            ('assign', {'action': 'assign', 'assignee': 'op'}),
            ('accept', {'action': 'accept'}),
            ('submit', {'action': 'submit', 'diagnosis': '光模块故障', 'solution': '更换'}),
            ('audit', {'action': 'audit', 'approved': True}),
            ('accept_check', {'action': 'accept_check', 'approved': True}),
        ]
        for _, payload in steps:
            r = op_client.post(f"/api/tickets/{seed['t']}/action", json=payload)
            assert r.status_code == 200, f'{payload} -> {r.get_json()}'
        with app.app_context():
            assert Ticket.query.get(seed['t']).status == '已关闭'
            # 5 次状态流转日志（fixture 直插无"创建"日志）
            assert TicketLog.query.filter_by(ticket_id=seed['t']).count() >= 5

    def test_illegal_transition_rejected(self, op_client, seed):
        """待派单直接提交审核 → 400"""
        r = op_client.post(f"/api/tickets/{seed['t']}/action", json={'action': 'submit'})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1

    def test_unknown_action_rejected(self, op_client, seed):
        r = op_client.post(f"/api/tickets/{seed['t']}/action", json={'action': 'boom'})
        assert r.status_code == 400

    def test_audit_reject_returns_processing(self, op_client, seed, app):
        for payload in ({'action': 'assign', 'assignee': 'op'}, {'action': 'accept'},
                        {'action': 'submit'}, {'action': 'audit', 'approved': False}):
            assert op_client.post(f"/api/tickets/{seed['t']}/action", json=payload).status_code == 200
        with app.app_context():
            assert Ticket.query.get(seed['t']).status == '处理中'


class TestTicketCreate:
    def test_create_default_pending(self, op_client, seed, app):
        r = op_client.post('/api/tickets', json={
            'title': '新工单', 'customer_id': seed['c'], 'priority': '中'})
        assert r.status_code == 200
        with app.app_context():
            t = Ticket.query.filter_by(title='新工单').first()
            assert t.status == '待派单'

    def test_create_self_accept(self, op_client, seed, app):
        r = op_client.post('/api/tickets', json={
            'title': '自接工单', 'customer_id': seed['c'],
            'dispatch_mode': 'self_accept'})
        assert r.status_code == 200
        with app.app_context():
            t = Ticket.query.filter_by(title='自接工单').first()
            assert t.status == '处理中'
            assert t.assigned_to == 'op'

    def test_create_empty_title(self, op_client, seed):
        r = op_client.post('/api/tickets', json={'title': '  '})
        assert r.status_code == 400


class TestTicketDelete:
    def test_delete_by_admin(self, admin_client, seed, app):
        r = admin_client.delete(f"/api/tickets/{seed['t']}")
        assert r.status_code == 200
        with app.app_context():
            assert Ticket.query.get(seed['t']) is None
            assert TicketLog.query.filter_by(ticket_id=seed['t']).count() == 0

    def test_operator_forbidden(self, op_client, seed):
        assert op_client.delete(f"/api/tickets/{seed['t']}").status_code == 403


class TestTicketDicts:
    def test_dicts(self, op_client):
        r = op_client.get('/api/dicts/tickets')
        body = r.get_json()
        assert body['code'] == 0
        assert '待派单' in body['data']['statuses']
        assert '紧急' in body['data']['priorities']
