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

    def test_delete_syncs_device_count(self, admin_client, seed, app):
        """删除设备后客户 device_count 冗余快照同步（曾漏刷新导致客户删不掉）"""
        with app.app_context():
            c2 = Customer.query.get(seed['c2'])
            c2.device_count = 1  # 模拟已同步快照（FW-B 在用）
            db.session.commit()
        r = admin_client.delete(f"/api/devices/{seed['d2']}")
        assert r.status_code == 200
        with app.app_context():
            c2 = Customer.query.get(seed['c2'])
            assert c2.device_count == 0


class TestDeviceImportSync:
    def _make_xlsx(self, rows):
        import io
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['所属客户', '设备名称', '设备类型', 'IP地址', '是否在用'])
        for row in rows:
            ws.append(row)
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        return bio

    def test_import_syncs_device_count(self, op_client, seed, app):
        """批量导入后刷新受影响客户 device_count（曾漏刷新）"""
        with app.app_context():
            c1 = Customer.query.get(seed['c1'])
            c1.device_count = 1  # 模拟已同步快照（SW-A）
            db.session.commit()
        xlsx = self._make_xlsx([
            ['设备API客户A', 'SW-D1', '交换机', '10.0.0.4', '是'],
            ['设备API客户A', 'SW-D2', '交换机', '10.0.0.5', '否'],
        ])
        r = op_client.post('/api/v2/devices/import', data={
            'import_file': (xlsx, 'devices.xlsx')},
            content_type='multipart/form-data')
        assert r.status_code == 200
        assert r.get_json()['data']['created'] == 2
        with app.app_context():
            c1 = Customer.query.get(seed['c1'])
            assert c1.device_count == 3  # SW-A + SW-D1 + SW-D2（全量口径，含不在用）


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
    def test_dicts_shape(self, admin_client, seed):
        r = admin_client.get('/api/dicts/devices')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert '华为' in data['brands']
        assert any(t['name'] == '交换机' for t in data['device_types'])
        assert len(data['customers']) >= 2

    def test_tree_three_levels(self, op_client, seed, app):
        """设备树：市 → 客户 → 设备 三级；未关联客户设备独立成组

        注：测试环境 SQLite SingletonThreadPool 同线程连接快照问题，
        不修改已有对象（新建客户/设备后请求），避免读到旧值。
        """
        from models import Region
        with app.app_context():
            city = Region(name='杭州市')
            db.session.add(city)
            db.session.flush()
            c3 = Customer(name='设备API客户C', region_id=city.id, city='杭州市')
            db.session.add(c3)
            db.session.flush()
            db.session.add(Device(customer_id=c3.id, device_name='SW-NEW',
                                  device_type='交换机', brand='H3C', is_in_use=True))
            db.session.add(Device(customer_id=None, device_name='无主设备'))
            db.session.commit()
        r = op_client.get('/api/devices/tree')
        assert r.status_code == 200
        data = r.get_json()['data']
        assert data['total'] == 4  # SW-A + FW-B + SW-NEW + 无主设备
        city_group = next(g for g in data['tree'] if g['name'] == '杭州市')
        assert city_group['device_count'] == 1
        cust_child = city_group['children'][0]
        assert cust_child['name'] == '设备API客户C'
        assert cust_child['children'][0]['device_name'] == 'SW-NEW'
        unassigned = next(g for g in data['tree'] if g['name'] == '未关联客户')
        assert unassigned['device_count'] == 1
        assert unassigned['children'][0]['device_name'] == '无主设备'
        assert data['tree'][-1]['name'] == '未关联客户'  # 最后

    def test_tree_filter(self, op_client, seed):
        r = op_client.get('/api/devices/tree', query_string={'device_type': '防火墙'})
        data = r.get_json()['data']
        assert data['total'] == 1
        # 客户 B 无地区 → 未分配地区组
        unassigned = next(g for g in data['tree'] if g['name'] == '未分配地区')
        assert unassigned['children'][0]['name'] == '设备API客户B'
        assert unassigned['children'][0]['children'][0]['device_name'] == 'FW-B'
