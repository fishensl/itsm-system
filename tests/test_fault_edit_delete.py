# -*- coding: utf-8 -*-
"""故障记录可编辑/删除：Vue API 路由 + 权限回归（SSR 页面已剥离）"""
import pytest

from models import db, Customer, Fault


@pytest.fixture()
def fault(app):
    with app.app_context():
        c = Customer(name='故障客户')
        db.session.add(c)
        db.session.flush()
        f = Fault(title='核心交换机宕机', customer_id=c.id, handler='op',
                  fault_type='设备故障', result='待观察')
        db.session.add(f)
        db.session.commit()
        yield f.id


class TestFaultEdit:
    def test_edit_page_gone(self, op_client, fault):
        """SSR 编辑页已剥离 → 404"""
        assert op_client.get(f'/faults/edit/{fault}').status_code == 404

    def test_put_updates(self, op_client, fault, app):
        r = op_client.put(f'/api/faults/{fault}', json={
            'title': '核心交换机宕机（已定位）', 'handler': 'op',
            'fault_type': '设备故障', 'result': '已解决'})
        assert r.status_code == 200
        with app.app_context():
            f = Fault.query.get(fault)
            assert f.title == '核心交换机宕机（已定位）'
            assert f.result == '已解决'

    def test_viewer_cannot_edit(self, viewer_client, fault, app):
        """viewer 无 fault:edit → 403 JSON"""
        r = viewer_client.put(f'/api/faults/{fault}', json={'title': 'X'})
        assert r.status_code == 403
        with app.app_context():
            assert Fault.query.get(fault).title == '核心交换机宕机'


class TestFaultDelete:
    def test_operator_deletes(self, op_client, fault, app):
        """operator 现持有 fault:delete"""
        r = op_client.delete(f'/api/faults/{fault}')
        assert r.status_code == 200
        with app.app_context():
            assert Fault.query.get(fault) is None

    def test_viewer_cannot_delete(self, viewer_client, fault, app):
        r = viewer_client.delete(f'/api/faults/{fault}')
        assert r.status_code == 403
        with app.app_context():
            assert Fault.query.get(fault) is not None


class TestFaultApiList:
    def test_list_returns_items(self, op_client, fault):
        r = op_client.get('/api/faults')
        assert r.status_code == 200
        items = r.get_json()['data']['items']
        assert any(i['id'] == fault for i in items)
