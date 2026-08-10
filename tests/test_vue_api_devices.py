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
                    network_type='内网', cert_expiry_date='2026-12-31',
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
        # 全量字段（与导出 vue_export.DEVICE_EXPORT_COLUMNS 对齐）下发：网络类型/证书到期/机柜/改密记录
        first = data['items'][0]
        assert 'network_type' in first and 'cert_expiry_date' in first
        assert {'rack_location', 'rack_name', 'rack_slot'} <= first.keys()
        assert {'pwd_changed_by', 'pwd_changed_at'} <= first.keys()
        assert first['rack_location'] == ''  # 未上架设备机柜列为空

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
            'network_type': 'DMZ', 'cert_expiry_date': '2027-06-30',
        })
        assert r.status_code == 200
        with app.app_context():
            d = Device.query.filter_by(device_name='SW-C').first()
            assert d is not None
            assert d.customer_id == seed['c1']
            assert 'G0/0/1' in d.interface
            assert d.password_encrypted
            assert d.network_type == 'DMZ'
            assert d.cert_expiry_date and d.cert_expiry_date.isoformat() == '2027-06-30'

    def test_create_duplicate_name(self, op_client, seed):
        r = op_client.post('/api/devices', json={'device_name': 'SW-A'})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1

    def test_update(self, op_client, seed, app):
        r = op_client.put(f"/api/devices/{seed['d1']}", json={
            'device_name': 'SW-A-EDITED', 'customer_id': seed['c2'],
            'device_type': '交换机', 'brand': '华为', 'is_in_use': True,
            'network_type': '外网', 'cert_expiry_date': '2028-01-01',
        })
        assert r.status_code == 200
        with app.app_context():
            d = Device.query.get(seed['d1'])
            assert d.device_name == 'SW-A-EDITED'
            assert d.customer_id == seed['c2']
            assert d.network_type == '外网'
            assert d.cert_expiry_date and d.cert_expiry_date.isoformat() == '2028-01-01'
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


class TestDeviceBatchUpdate:
    def test_batch_update_field(self, op_client, seed, app):
        """批量修改普通字段（安装位置）"""
        r = op_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1'], seed['d2']], 'field': 'location', 'value': '机房A-1号柜'})
        assert r.status_code == 200
        assert r.get_json()['data']['count'] == 2
        with app.app_context():
            for did in (seed['d1'], seed['d2']):
                assert Device.query.get(did).location == '机房A-1号柜'

    def test_batch_update_bool_and_date(self, op_client, seed, app):
        """批量修改布尔与日期字段"""
        r = op_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1']], 'field': 'is_in_use', 'value': False})
        assert r.status_code == 200
        r = op_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1']], 'field': 'license_expiry', 'value': '2027-12-31'})
        assert r.status_code == 200
        with app.app_context():
            d = Device.query.get(seed['d1'])
            assert d.is_in_use is False
            assert d.license_expiry and d.license_expiry.isoformat() == '2027-12-31'

    def test_batch_update_unknown_field_400(self, op_client, seed):
        r = op_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1']], 'field': 'password', 'value': 'x'})
        assert r.status_code == 400

    def test_batch_update_rack_location(self, admin_client, seed, app):
        """批量改机房位置：更新最近上架记录所在机柜的 Rack.location；未上架设备跳过"""
        from models import Rack, RackInstall
        with app.app_context():
            rack = Rack(customer_id=seed['c1'], name='A-01', location='机房A', total_u=42)
            db.session.add(rack)
            db.session.flush()
            db.session.add(RackInstall(rack_id=rack.id, device_id=seed['d1'], start_u=1, occupy_u=1))
            db.session.commit()
            rack_id = rack.id
        r = admin_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1'], seed['d2']], 'field': 'rack_location', 'value': '机房B'})
        assert r.status_code == 200
        data = r.get_json()['data']
        assert data['count'] == 1  # d1 已上架
        assert data['skipped'] == 1  # d2 未上架跳过
        with app.app_context():
            rack = Rack.query.get(rack_id)
            assert rack.location == '机房B'

    def test_batch_update_rack(self, admin_client, seed, app):
        """批量迁移机柜：自动连续排布 U 位、机房位置/机柜号随机柜、迁移走旧记录"""
        from models import Rack, RackInstall
        with app.app_context():
            rack = Rack(customer_id=seed['c1'], name='B-02', location='机房B', total_u=42)
            db.session.add(rack)
            db.session.flush()
            # 预置 d1 的旧上架记录
            old_rack = Rack(customer_id=seed['c1'], name='A-01', location='机房A', total_u=42)
            db.session.add(old_rack)
            db.session.flush()
            db.session.add(RackInstall(rack_id=old_rack.id, device_id=seed['d1'], start_u=1, occupy_u=1))
            db.session.commit()
            rack_id, old_rack_id = rack.id, old_rack.id
        r = admin_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1'], seed['d2']], 'rack_id': rack_id, 'start_u': 3, 'occupy_u': 1})
        assert r.status_code == 200
        assert r.get_json()['data']['count'] == 2
        with app.app_context():
            # 两台设备自动连续排布：d1@U3、d2@U4；旧 A-01 记录已迁移删除（无幽灵占位）
            inst1 = RackInstall.query.filter_by(device_id=seed['d1']).first()
            inst2 = RackInstall.query.filter_by(device_id=seed['d2']).first()
            assert inst1 is not None and inst1.rack_id == rack_id and inst1.start_u == 3
            assert inst2 is not None and inst2.rack_id == rack_id and inst2.start_u == 4
            assert RackInstall.query.filter_by(rack_id=old_rack_id).count() == 0

    def test_batch_update_rack_range_conflict_400(self, admin_client, seed, app):
        """批量迁移机柜：U 位超出机柜容量（连续排布超限）→ 400 且整体回滚"""
        from models import Rack, RackInstall
        with app.app_context():
            rack = Rack(customer_id=seed['c1'], name='B-03', location='机房B', total_u=4)
            db.session.add(rack)
            db.session.commit()
            rack_id = rack.id
        # 起始 U4 + 2 台占用 U1 → 第二台 U5 超出 total_u=4
        r = admin_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1'], seed['d2']], 'rack_id': rack_id, 'start_u': 4, 'occupy_u': 1})
        assert r.status_code == 400
        assert 'U 位超出范围' in r.get_json()['message']
        with app.app_context():
            assert RackInstall.query.filter_by(rack_id=rack_id).count() == 0

    def test_batch_update_rack_existing_occupation_conflict_400(self, admin_client, seed, app):
        """批量迁移机柜：与机柜既有占用冲突 → 400（基线校验仍生效）"""
        from models import Rack, RackInstall
        with app.app_context():
            rack = Rack(customer_id=seed['c1'], name='B-04', location='机房B', total_u=42)
            db.session.add(rack)
            db.session.flush()
            # 其他设备已占 U5（非本次迁移设备）
            other = Device(customer_id=seed['c1'], device_name='Other-D', is_in_use=True)
            db.session.add(other)
            db.session.flush()
            db.session.add(RackInstall(rack_id=rack.id, device_id=other.id, start_u=5, occupy_u=1))
            db.session.commit()
            rack_id = rack.id
        r = admin_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1']], 'rack_id': rack_id, 'start_u': 5, 'occupy_u': 1})
        assert r.status_code == 400
        assert '冲突' in r.get_json()['message']
        with app.app_context():
            assert RackInstall.query.filter_by(rack_id=rack_id).count() == 1  # 仅原占用，未新增


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
