# -*- coding: utf-8 -*-
"""P2 设备 Vue API：列表/筛选/增删改/密码 reveal/字典"""
import pytest

from models import db, Customer, Device
from utils.crypto import encrypt_password


@pytest.fixture()
def seed(app):
    with app.app_context():
        from models import DeviceType
        c1 = Customer(name='设备API客户A')
        c2 = Customer(name='设备API客户B')
        db.session.add_all([c1, c2])
        db.session.flush()
        d1 = Device(customer_id=c1.id, device_name='SW-A', device_type='交换机',
                    brand='华为', ip_address='10.0.0.1', is_in_use=True,
                    password_encrypted=encrypt_password('Sec#1'))
        d2 = Device(customer_id=c2.id, device_name='FW-B', device_type='防火墙',
                    brand='深信服', ip_address='10.0.0.2', is_in_use=False)
        db.session.add_all([d1, d2])
        # 字典种子（conftest 不种 DeviceType）
        if not DeviceType.query.first():
            db.session.add(DeviceType(name='交换机'))
            db.session.add(DeviceType(name='防火墙'))
        db.session.commit()
        yield {'c1': c1.id, 'c2': c2.id, 'd1': d1.id, 'd2': d2.id}


class TestDeviceList:
    def test_list_shape(self, op_client, seed):
        r = op_client.get('/api/devices')
        assert r.status_code == 200
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['total'] == 2
        assert data['page'] == 1
        # 列表不含明文密码
        assert all('password' not in d for d in data['items'])
        assert any(d['has_password'] for d in data['items'])

    def test_search(self, op_client, seed):
        r = op_client.get('/api/devices', query_string={'search': 'FW-B'})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['device_name'] == 'FW-B'

    def test_filter_by_customer(self, op_client, seed):
        r = op_client.get('/api/devices', query_string={'customer_id': seed['c1']})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['customer_name'] == '设备API客户A'

    def test_filter_is_in_use(self, op_client, seed):
        r = op_client.get('/api/devices', query_string={'is_in_use': 1})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['is_in_use'] is True

    def test_pagination(self, op_client, seed):
        r = op_client.get('/api/devices', query_string={'page': 1, 'page_size': 1})
        data = r.get_json()['data']
        assert data['total'] == 2
        assert len(data['items']) == 1


class TestDeviceCrud:
    def test_create(self, op_client, seed, app):
        r = op_client.post('/api/devices', json={
            'device_name': 'SW-C', 'customer_id': seed['c1'], 'device_type': '交换机',
            'brand': 'H3C', 'ip_address': '10.0.0.3', 'is_in_use': True,
            'interface': ['G0/0/1', 'G0/0/2'], 'password': 'Pwd#123',
        })
        assert r.status_code == 200
        with app.app_context():
            d = Device.query.filter_by(device_name='SW-C').first()
            assert d is not None
            assert d.customer_id == seed['c1']
            assert 'G0/0/1' in d.interface
            assert d.password_encrypted

    def test_create_duplicate_name(self, op_client, seed):
        r = op_client.post('/api/devices', json={'device_name': 'SW-A'})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1

    def test_update(self, op_client, seed, app):
        r = op_client.put(f"/api/devices/{seed['d1']}", json={
            'device_name': 'SW-A-EDITED', 'customer_id': seed['c2'],
            'device_type': '交换机', 'brand': '华为', 'is_in_use': True,
        })
        assert r.status_code == 200
        with app.app_context():
            d = Device.query.get(seed['d1'])
            assert d.device_name == 'SW-A-EDITED'
            assert d.customer_id == seed['c2']
            # 客户 device_count 同步
            c = Customer.query.get(seed['c2'])
            assert c.device_count == 2  # FW-B + SW-A-EDITED

    def test_delete(self, admin_client, seed, app):
        """删除需 device:delete（operator 无此权限，admin 走短路）"""
        r = admin_client.delete(f"/api/devices/{seed['d2']}")
        assert r.status_code == 200
        with app.app_context():
            assert Device.query.get(seed['d2']) is None


class TestRevealPassword:
    def test_reveal_with_permission(self, op_client, seed):
        r = op_client.post(f"/api/v2/devices/{seed['d1']}/reveal-password")
        assert r.status_code == 200
        assert r.get_json()['data']['password'] == 'Sec#1'

    def test_reveal_forbidden_without_permission(self, viewer_client, seed):
        r = viewer_client.post(f"/api/v2/devices/{seed['d1']}/reveal-password")
        assert r.status_code == 403

    def test_requires_login(self, client, seed):
        assert client.post(f"/api/v2/devices/{seed['d1']}/reveal-password").status_code == 401


class TestDeviceDicts:
    def test_dicts_shape(self, op_client, seed):
        r = op_client.get('/api/dicts/devices')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert '华为' in data['brands']
        assert any(t['name'] == '交换机' for t in data['device_types'])
        assert len(data['customers']) >= 2
