# -*- coding: utf-8 -*-
"""故障记录恢复可编辑/删除：路由 + 权限 + 页面按钮回归"""
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
    def test_edit_page_renders(self, op_client, fault):
        assert op_client.get(f'/faults/edit/{fault}').status_code == 200

    def test_edit_post_updates(self, op_client, fault, app):
        r = op_client.post(f'/faults/edit/{fault}', data={
            'title': '核心交换机宕机（已定位）', 'handler': 'op',
            'fault_type': '设备故障', 'result': '已解决'})
        assert r.status_code == 302
        with app.app_context():
            f = Fault.query.get(fault)
            assert f.title == '核心交换机宕机（已定位）'
            assert f.result == '已解决'

    def test_viewer_cannot_edit(self, viewer_client, fault, app):
        """viewer 无 fault:edit → 重定向，不报 500"""
        assert viewer_client.get(f'/faults/edit/{fault}').status_code == 302
        r = viewer_client.post(f'/faults/edit/{fault}', data={'title': 'X'})
        assert r.status_code == 302
        with app.app_context():
            assert Fault.query.get(fault).title == '核心交换机宕机'


class TestFaultDelete:
    def test_operator_deletes(self, op_client, fault, app):
        """operator 现持有 fault:delete"""
        r = op_client.post(f'/faults/delete/{fault}')
        assert r.status_code == 302
        with app.app_context():
            assert Fault.query.get(fault) is None

    def test_viewer_cannot_delete(self, viewer_client, fault, app):
        viewer_client.post(f'/faults/delete/{fault}')
        with app.app_context():
            assert Fault.query.get(fault) is not None


class TestFaultListButtons:
    def test_list_shows_edit_delete_for_operator(self, op_client, fault):
        body = op_client.get('/faults').data.decode('utf-8')
        assert f'/faults/edit/{fault}' in body
        assert f'/faults/delete/{fault}' in body

    def test_list_hides_edit_delete_for_viewer(self, viewer_client, fault):
        body = viewer_client.get('/faults').data.decode('utf-8')
        assert f'/faults/edit/{fault}' not in body
        assert f'/faults/delete/{fault}' not in body

    def test_detail_shows_edit_delete_for_operator(self, op_client, fault):
        body = op_client.get(f'/faults/{fault}').data.decode('utf-8')
        assert f'/faults/edit/{fault}' in body
        assert f'/faults/delete/{fault}' in body
