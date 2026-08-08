# -*- coding: utf-8 -*-
"""功能1+2：工单录入「自己接单处置」+ 表单内快速新增故障类别"""
import pytest

from models import db, Customer, Ticket, TicketLog, FaultType, Fault


@pytest.fixture()
def customer(app):
    with app.app_context():
        c = Customer(name='工单客户')
        db.session.add(c)
        db.session.commit()
        yield c.id


class TestSelfAcceptOnCreate:
    def test_create_with_self_accept(self, op_client, customer, app):
        """录单时选「我自己接单处置」→ 直接到处理中（派单+接单一体，日志完整）"""
        r = op_client.post('/api/tickets', json={
            'title': '防火墙策略异常', 'customer_id': customer,
            'priority': '高', 'dispatch_mode': 'self_accept',
        })
        assert r.status_code == 200
        with app.app_context():
            t = Ticket.query.filter_by(title='防火墙策略异常').first()
            assert t.status == '处理中'
            assert t.assigned_to == 'op'  # 录单人（operator 登录，realname=op）
            actions = [l.action for l in TicketLog.query.filter_by(ticket_id=t.id)
                       .order_by(TicketLog.id).all()]
            assert any('派单' in a or '状态变更: 待派单 → 已派单' in a for a in actions)
            assert any('状态变更: 已派单 → 处理中' in a for a in actions)

    def test_create_default_pending_assign(self, op_client, customer, app):
        """默认仍为待派单（流程不破坏）"""
        r = op_client.post('/api/tickets', json={
            'title': '普通工单', 'customer_id': customer, 'priority': '中'})
        assert r.status_code == 200
        with app.app_context():
            t = Ticket.query.filter_by(title='普通工单').first()
            assert t.status == '待派单'


class TestQuickAddFaultType:
    def test_add_success(self, op_client, app):
        r = op_client.post('/api/fault-types/add', json={'name': '机房空调故障'})
        assert r.status_code == 200
        body = r.get_json()
        assert body['success'] is True and body['name'] == '机房空调故障'
        with app.app_context():
            assert FaultType.query.filter_by(name='机房空调故障').first() is not None

    def test_duplicate_rejected(self, op_client, app):
        op_client.post('/api/fault-types/add', json={'name': '重复类别'})
        r = op_client.post('/api/fault-types/add', json={'name': '重复类别'})
        assert r.status_code == 409
        assert r.get_json()['success'] is False

    def test_empty_rejected(self, op_client):
        r = op_client.post('/api/fault-types/add', json={'name': '  '})
        assert r.status_code == 400

    def test_viewer_forbidden(self, viewer_client):
        r = viewer_client.post('/api/fault-types/add', json={'name': 'X'})
        assert r.status_code == 403

    def test_anonymous_401(self, client):
        r = client.post('/api/fault-types/add', json={'name': 'X'})
        assert r.status_code == 401


class TestFaultToTicket:
    def test_convert_fault_to_ticket(self, op_client, customer, app):
        """故障实时转工单：复制字段 + 桥接 ticket_id + source_type=故障转单"""
        from models import Fault
        with app.app_context():
            f = Fault(title='交换机离线', customer_id=customer,
                      fault_description='端口down，业务中断', result='待观察')
            db.session.add(f)
            db.session.commit()
            fid = f.id
        r = op_client.post(f'/api/faults/{fid}/convert', json={})
        assert r.status_code == 200, r.get_json()
        d = r.get_json()['data']
        assert d['ticket_number'].startswith('WO-')
        with app.app_context():
            f2 = Fault.query.get(fid)
            t = Ticket.query.get(d['ticket_id'])
            assert f2.ticket_id == t.id
            assert t.source_type == '故障转单'
            assert t.title == '交换机离线'
            assert t.description == '端口down，业务中断'
            assert t.customer_id == customer

    def test_convert_idempotent(self, op_client, customer, app):
        """已转单的故障拒绝重复转单"""
        with app.app_context():
            f = Fault(title='重复转单', customer_id=customer)
            db.session.add(f)
            db.session.flush()
            from services.fault_service import convert_fault_to_ticket
            convert_fault_to_ticket(f.id, 'op')
            db.session.commit()
            fid = f.id
        r = op_client.post(f'/api/faults/{fid}/convert', json={})
        assert r.status_code == 400
        assert '已转工单' in r.get_json()['message']

    def test_convert_requires_ticket_perm(self, viewer_client, customer, app):
        """viewer 无 ticket:add → 403"""
        with app.app_context():
            f = Fault(title='无权限转单', customer_id=customer)
            db.session.add(f)
            db.session.commit()
            fid = f.id
        r = viewer_client.post(f'/api/faults/{fid}/convert', json={})
        assert r.status_code == 403
