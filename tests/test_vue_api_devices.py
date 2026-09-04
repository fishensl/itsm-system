# -*- coding: utf-8 -*-
"""P2 设备 Vue API：列表/筛选/增删改/密码 reveal/字典"""
import io
from datetime import date

import pytest

from models import db, Customer, Device, User, Brand
from utils.crypto import decrypt_password, encrypt_password


@pytest.fixture()
def seed(app):
    with app.app_context():
        from models import DeviceType, NetworkType
        c1 = Customer(name='设备API客户A')
        c2 = Customer(name='设备API客户B')
        db.session.add_all([c1, c2])
        db.session.flush()
        d1 = Device(customer_id=c1.id, device_name='SW-A', device_type='交换机',
                    brand='华为', ip_address='10.0.0.1', is_in_use=True,
                    network_type='内网', cert_expiry_date=date(2026, 12, 31),
                    location='旧安装描述', power_supply='双电源',
                    password_encrypted=encrypt_password('Sec#1'))
        d2 = Device(customer_id=c2.id, device_name='FW-B', device_type='防火墙',
                    brand='深信服', ip_address='10.0.0.2', is_in_use=False)
        db.session.add_all([d1, d2])
        op = User.query.filter_by(username='op').first()
        op.customers = [c1, c2]
        # 字典种子（conftest 不种 DeviceType）
        if not DeviceType.query.first():
            db.session.add(DeviceType(name='交换机'))
            db.session.add(DeviceType(name='防火墙'))
        if not NetworkType.query.first():
            db.session.add(NetworkType(name='内网', sort_order=1))
            db.session.add(NetworkType(name='外网', sort_order=2))
        if not Brand.query.first():
            db.session.add(Brand(name='华为', sort_order=1))
            db.session.add(Brand(name='深信服', sort_order=2))
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
        assert {'rack_location', 'rack_name', 'rack_slot', 'rack_id', 'rack_install_id',
                'rack_start_u', 'rack_occupy_u'} <= first.keys()
        assert first['power_supply'] in ('', '双电源')
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

    def test_room_filter_uses_rack_for_installed_and_device_field_for_uninstalled(
            self, op_client, seed, app):
        from models import Rack, RackInstall
        with app.app_context():
            rack = Rack(customer_id=seed['c1'], name='A-01', location='生产机房')
            db.session.add(rack)
            db.session.flush()
            installed = Device.query.get(seed['d1'])
            installed.rack_location = '过期机房值'
            db.session.add(RackInstall(
                rack_id=rack.id, device_id=installed.id, start_u=1, occupy_u=1))
            db.session.commit()
        actual = op_client.get('/api/devices', query_string={'room_location': '生产机房'})
        assert [item['id'] for item in actual.get_json()['data']['items']] == [seed['d1']]
        stale = op_client.get('/api/devices', query_string={'room_location': '过期机房值'})
        assert stale.get_json()['data']['total'] == 0
        non_room = op_client.get('/api/devices', query_string={
            'room_location': '__non_room__'})
        assert [item['id'] for item in non_room.get_json()['data']['items']] == [seed['d2']]

    def test_location_scope_room_and_non_room(self, op_client, seed, app):
        with app.app_context():
            Device.query.get(seed['d1']).rack_location = '二楼机房'
            db.session.commit()
        rooms = op_client.get('/api/devices', query_string={'location_scope': 'room'})
        assert [item['id'] for item in rooms.get_json()['data']['items']] == [seed['d1']]
        other = op_client.get('/api/devices', query_string={'location_scope': 'non_room'})
        assert [item['id'] for item in other.get_json()['data']['items']] == [seed['d2']]

    def test_pagination(self, op_client, seed):
        r = op_client.get('/api/devices', query_string={'page': 1, 'page_size': 1})
        data = r.get_json()['data']
        assert data['total'] == 2
        assert len(data['items']) == 1


class TestDeviceCrud:
    def test_name_is_unique_within_customer_but_reusable_across_customers(
            self, op_client, seed):
        payload = {
            'customer_id': seed['c2'], 'device_name': 'SW-A',
            'device_type': '交换机', 'is_in_use': True,
        }
        first = op_client.post('/api/devices', json=payload)
        assert first.status_code == 200
        duplicate = op_client.post('/api/devices', json=payload)
        assert duplicate.status_code == 400
        assert '当前客户' in duplicate.get_json()['message']

    def test_create_with_custom_rack_is_atomic(self, op_client, seed, app):
        from models import Rack, RackInstall

        r = op_client.post('/api/devices', json={
            'device_name': 'SW-CUSTOM-RACK', 'customer_id': seed['c1'],
            'rack_custom_name': '3', 'rack_location': '二楼机房',
            'rack_start_u': 12, 'rack_occupy_u': 2,
            'location': '正面', 'power_supply': '双电源', 'is_in_use': True,
        })
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            rack = Rack.query.filter_by(customer_id=seed['c1'], name='3').one()
            assert rack.location == '二楼机房'
            install = RackInstall.query.filter_by(
                device_id=r.get_json()['data']['id']).one()
            assert install.rack_id == rack.id
            assert (install.start_u, install.occupy_u) == (12, 2)

        failed = op_client.post('/api/devices', json={
            'device_name': 'SW-BAD-CUSTOM-RACK', 'customer_id': seed['c1'],
            'rack_custom_name': '临时孤儿柜', 'rack_location': '二楼机房',
            'rack_start_u': 42, 'rack_occupy_u': 2,
            'location': '正面', 'power_supply': '双电源', 'is_in_use': True,
        })
        assert failed.status_code == 400
        with app.app_context():
            assert Rack.query.filter_by(name='临时孤儿柜').count() == 0

    def test_create_with_rack_placement(self, op_client, seed, app):
        from models import Rack, RackInstall
        with app.app_context():
            rack = Rack(customer_id=seed['c1'], name='A-01', location='一楼机房', total_u=42)
            db.session.add(rack)
            db.session.commit()
            rack_id = rack.id

        r = op_client.post('/api/devices', json={
            'device_name': 'SW-RACKED', 'customer_id': seed['c1'],
            'rack_location': '不会写入设备自身', 'rack_id': rack_id,
            'rack_start_u': 8, 'rack_occupy_u': 2,
            'location': '正面', 'power_supply': '双电源', 'is_in_use': True,
        })
        assert r.status_code == 200, r.get_json()
        device_id = r.get_json()['data']['id']
        with app.app_context():
            device = Device.query.get(device_id)
            install = RackInstall.query.filter_by(device_id=device_id).one()
            assert device.rack_location == ''
            assert (install.rack_id, install.start_u, install.occupy_u) == (rack_id, 8, 2)

        payload = op_client.get(f'/api/devices/{device_id}').get_json()['data']
        assert payload['rack_location'] == '一楼机房'
        assert payload['rack_name'] == 'A-01'
        assert payload['rack_slot'] == '8U-9U'
        assert payload['rack_id'] == rack_id
        assert payload['rack_start_u'] == 8
        assert payload['rack_occupy_u'] == 2

    def test_create(self, op_client, seed, app):
        r = op_client.post('/api/devices', json={
            'device_name': 'SW-C', 'customer_id': seed['c1'], 'device_type': '交换机',
            'brand': 'H3C', 'ip_address': '10.0.0.3', 'is_in_use': True,
            'interface': ['G0/0/1', 'G0/0/2'], 'password': 'Pwd#123',
            'network_type': 'DMZ', 'cert_expiry_date': '2027-06-30',
            'location': '背面', 'power_supply': '单电源',
        })
        assert r.status_code == 200
        with app.app_context():
            d = Device.query.filter_by(device_name='SW-C').first()
            assert d is not None
            assert d.customer_id == seed['c1']
            assert 'G0/0/1' in d.interface
            assert d.password_encrypted
            assert d.network_type == 'DMZ'
            assert d.location == '背面'
            assert d.power_supply == '单电源'
            assert d.cert_expiry_date and d.cert_expiry_date.isoformat() == '2027-06-30'

    def test_create_duplicate_name(self, op_client, seed):
        r = op_client.post('/api/devices', json={'device_name': 'SW-A'})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1

    @pytest.mark.parametrize(('field', 'value'), [
        ('location', '左侧'),
        ('power_supply', '三电源'),
    ])
    def test_create_rejects_invalid_device_choice(self, op_client, seed, field, value):
        payload = {'device_name': f'INVALID-{field}', 'customer_id': seed['c1'], field: value}
        r = op_client.post('/api/devices', json=payload)
        assert r.status_code == 400
        assert '仅支持' in r.get_json()['message']

    def test_update_can_preserve_legacy_location_until_user_normalizes_it(
            self, op_client, seed, app):
        before = op_client.get(f"/api/devices/{seed['d1']}")
        assert before.get_json()['data']['location'] == '旧安装描述'
        r = op_client.put(f"/api/devices/{seed['d1']}", json={
            'device_name': 'SW-A', 'customer_id': seed['c1'],
            'location': '旧安装描述', 'is_in_use': True,
        })
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            assert Device.query.get(seed['d1']).location == '旧安装描述'

    def test_password_update_allows_preexisting_same_customer_duplicate(
            self, op_client, seed, app):
        """历史合法同名设备不得阻断当前设备的密码更新。"""
        with app.app_context():
            original = Device.query.get(seed['d1'])
            db.session.add(Device(
                customer_id=original.customer_id,
                device_name=original.device_name,
                device_type='交换机',
                is_in_use=True,
            ))
            db.session.commit()

        response = op_client.put(f"/api/devices/{seed['d1']}", json={
            'device_name': 'SW-A',
            'customer_id': seed['c1'],
            'password': 'Updated#Duplicate123',
            'is_in_use': True,
        })

        assert response.status_code == 200, response.get_json()
        with app.app_context():
            device = Device.query.get(seed['d1'])
            assert decrypt_password(device.password_encrypted) == 'Updated#Duplicate123'

    def test_update_still_rejects_new_same_customer_name_collision(
            self, op_client, seed):
        response = op_client.put(f"/api/devices/{seed['d2']}", json={
            'device_name': 'SW-A',
            'customer_id': seed['c1'],
            'is_in_use': True,
        })

        assert response.status_code == 400
        assert '当前客户' in response.get_json()['message']

    def test_update(self, op_client, seed, app):
        r = op_client.put(f"/api/devices/{seed['d1']}", json={
            'device_name': 'SW-A-EDITED', 'customer_id': seed['c2'],
            'device_type': '交换机', 'brand': '华为', 'is_in_use': True,
            'network_type': '外网', 'cert_expiry_date': '2028-01-01',
            'location': '正面', 'power_supply': '双电源',
        })
        assert r.status_code == 200
        with app.app_context():
            d = Device.query.get(seed['d1'])
            assert d.device_name == 'SW-A-EDITED'
            assert d.customer_id == seed['c2']
            assert d.network_type == '外网'
            assert d.location == '正面'
            assert d.power_supply == '双电源'
            assert d.cert_expiry_date and d.cert_expiry_date.isoformat() == '2028-01-01'
            # 客户 device_count 同步
            c = Customer.query.get(seed['c2'])
            assert c.device_count == 2  # FW-B + SW-A-EDITED

    def test_update_rack_placement_then_unrack(self, op_client, seed, app):
        from models import Rack, RackInstall
        with app.app_context():
            old_rack = Rack(customer_id=seed['c1'], name='OLD', location='旧机房', total_u=42)
            new_rack = Rack(customer_id=seed['c1'], name='NEW', location='新机房', total_u=24)
            db.session.add_all([old_rack, new_rack])
            db.session.flush()
            db.session.add(RackInstall(
                rack_id=old_rack.id, device_id=seed['d1'], start_u=2, occupy_u=1))
            db.session.commit()
            new_rack_id = new_rack.id

        r = op_client.put(f"/api/devices/{seed['d1']}", json={
            'device_name': 'SW-A', 'customer_id': seed['c1'],
            'rack_id': new_rack_id, 'rack_start_u': 10, 'rack_occupy_u': 2,
            'rack_location': '应由机柜派生', 'location': '背面',
            'power_supply': '双电源', 'is_in_use': True,
        })
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            installs = RackInstall.query.filter_by(device_id=seed['d1']).all()
            assert len(installs) == 1
            assert (installs[0].rack_id, installs[0].start_u, installs[0].occupy_u) == (
                new_rack_id, 10, 2)
            assert Device.query.get(seed['d1']).rack_location == ''

        r = op_client.put(f"/api/devices/{seed['d1']}", json={
            'device_name': 'SW-A', 'customer_id': seed['c1'],
            'rack_id': None, 'rack_location': '灾备机房',
            'location': '背面', 'power_supply': '双电源', 'is_in_use': True,
        })
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            assert RackInstall.query.filter_by(device_id=seed['d1']).count() == 0
            assert Device.query.get(seed['d1']).rack_location == '灾备机房'

    def test_update_rack_placement_rejects_conflict_atomically(
            self, op_client, seed, app):
        from models import Rack, RackInstall
        with app.app_context():
            rack = Rack(customer_id=seed['c1'], name='FULL', location='生产机房', total_u=12)
            other = Device(customer_id=seed['c1'], device_name='OCCUPIED', is_in_use=True)
            db.session.add_all([rack, other])
            db.session.flush()
            db.session.add(RackInstall(
                rack_id=rack.id, device_id=other.id, start_u=5, occupy_u=2))
            db.session.commit()
            rack_id = rack.id

        r = op_client.put(f"/api/devices/{seed['d1']}", json={
            'device_name': 'SHOULD-ROLLBACK', 'customer_id': seed['c1'],
            'rack_id': rack_id, 'rack_start_u': 6, 'rack_occupy_u': 1,
            'location': '正面', 'power_supply': '双电源', 'is_in_use': True,
        })
        assert r.status_code == 400
        assert '冲突' in r.get_json()['message']
        with app.app_context():
            assert Device.query.get(seed['d1']).device_name == 'SW-A'
            assert RackInstall.query.filter_by(device_id=seed['d1']).count() == 0

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
        """批量修改普通枚举字段（安装位置/电源配置）"""
        r = op_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1'], seed['d2']], 'field': 'location', 'value': '背面'})
        assert r.status_code == 200
        assert r.get_json()['data']['count'] == 2
        r = op_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1'], seed['d2']], 'field': 'power_supply', 'value': '双电源'})
        assert r.status_code == 200
        with app.app_context():
            for did in (seed['d1'], seed['d2']):
                device = Device.query.get(did)
                assert device.location == '背面'
                assert device.power_supply == '双电源'

    @pytest.mark.parametrize(('field', 'value'), [
        ('location', '机房A-1号柜'),
        ('power_supply', '三电源'),
    ])
    def test_batch_update_rejects_invalid_device_choice(self, op_client, seed, field, value):
        r = op_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1']], 'field': field, 'value': value})
        assert r.status_code == 400

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
        """批量改机房位置：已上架设备更新所在机柜 Rack.location；未上架设备写入自身 rack_location"""
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
        assert data['count'] == 2  # 全部生效，无跳过
        assert 'skipped' not in data
        with app.app_context():
            rack = Rack.query.get(rack_id)
            assert rack.location == '机房B'  # d1 已上架：改机柜位置
            d2 = Device.query.get(seed['d2'])
            assert d2.rack_location == '机房B'  # d2 未上架：写入设备自身

    def test_batch_update_rack_location_unracked_shows_in_list(self, admin_client, seed, app):
        """未上架设备批量写入机房位置后，列表口径显示设备自身值"""
        r = admin_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d2']], 'field': 'rack_location', 'value': '机房C'})
        assert r.status_code == 200
        assert r.get_json()['data']['count'] == 1
        # 列表口径
        r = admin_client.get('/api/devices', query_string={'search': 'FW-B'})
        assert r.status_code == 200
        items = r.get_json()['data']['items']
        assert len(items) == 1
        assert items[0]['rack_location'] == '机房C'
        # DB 层：未上架设备自身字段已写入
        with app.app_context():
            assert Device.query.get(seed['d2']).rack_location == '机房C'

    def test_batch_update_rack(self, admin_client, seed, app):
        """批量迁移机柜：自动连续排布 U 位、机房位置/机柜号随机柜、迁移走旧记录"""
        from models import Rack, RackInstall
        with app.app_context():
            same_customer_device = Device(
                customer_id=seed['c1'], device_name='SW-A-SECOND', is_in_use=True)
            db.session.add(same_customer_device)
            db.session.flush()
            second_device_id = same_customer_device.id
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
            'device_ids': [seed['d1'], second_device_id], 'rack_id': rack_id,
            'start_u': 3, 'occupy_u': 1})
        assert r.status_code == 200
        assert r.get_json()['data']['count'] == 2
        with app.app_context():
            # 两台设备自动连续排布：d1@U3、d2@U4；旧 A-01 记录已迁移删除（无幽灵占位）
            inst1 = RackInstall.query.filter_by(device_id=seed['d1']).first()
            inst2 = RackInstall.query.filter_by(device_id=second_device_id).first()
            assert inst1 is not None and inst1.rack_id == rack_id and inst1.start_u == 3
            assert inst2 is not None and inst2.rack_id == rack_id and inst2.start_u == 4
            assert RackInstall.query.filter_by(rack_id=old_rack_id).count() == 0

    def test_batch_update_rack_range_conflict_400(self, admin_client, seed, app):
        """批量迁移机柜：U 位超出机柜容量（连续排布超限）→ 400 且整体回滚"""
        from models import Rack, RackInstall
        with app.app_context():
            same_customer_device = Device(
                customer_id=seed['c1'], device_name='SW-A-RANGE', is_in_use=True)
            db.session.add(same_customer_device)
            db.session.flush()
            second_device_id = same_customer_device.id
            rack = Rack(customer_id=seed['c1'], name='B-03', location='机房B', total_u=4)
            db.session.add(rack)
            db.session.commit()
            rack_id = rack.id
        # 起始 U4 + 2 台占用 U1 → 第二台 U5 超出 total_u=4
        r = admin_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1'], second_device_id], 'rack_id': rack_id,
            'start_u': 4, 'occupy_u': 1})
        assert r.status_code == 400
        assert 'U 位超出范围' in r.get_json()['message']
        with app.app_context():
            assert RackInstall.query.filter_by(rack_id=rack_id).count() == 0

    def test_batch_update_rack_rejects_mixed_customers(self, admin_client, seed, app):
        from models import Rack, RackInstall
        with app.app_context():
            rack = Rack(customer_id=seed['c1'], name='B-05', location='机房B', total_u=42)
            db.session.add(rack)
            db.session.commit()
            rack_id = rack.id
        r = admin_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1'], seed['d2']], 'rack_id': rack_id,
            'start_u': 1, 'occupy_u': 1,
        })
        assert r.status_code == 400
        assert '同一客户' in r.get_json()['message']
        with app.app_context():
            assert RackInstall.query.filter_by(rack_id=rack_id).count() == 0

    def test_batch_update_custom_rack(self, admin_client, seed, app):
        from models import Rack, RackInstall
        r = admin_client.post('/api/v2/devices/batch-update', json={
            'device_ids': [seed['d1']], 'rack_custom_name': '4',
            'rack_location': '9楼机房', 'start_u': 27, 'occupy_u': 4,
        })
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            rack = Rack.query.filter_by(
                customer_id=seed['c1'], name='4', location='9楼机房').one()
            install = RackInstall.query.filter_by(
                rack_id=rack.id, device_id=seed['d1']).one()
            assert (install.start_u, install.occupy_u) == (27, 4)

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


class TestDeviceBatchDelete:
    def test_preview_and_delete_preserve_rack_snapshot_and_audit(
            self, admin_client, seed, app):
        from models import AuditLog, Rack, RackInstall
        with app.app_context():
            rack = Rack(customer_id=seed['c1'], name='删除预览柜', location='机房')
            db.session.add(rack)
            db.session.flush()
            install = RackInstall(
                rack_id=rack.id, device_id=seed['d1'], start_u=5, occupy_u=2)
            db.session.add(install)
            db.session.commit()
            install_id = install.id
        preview = admin_client.post('/api/v2/devices/batch-delete/preview', json={
            'device_ids': [seed['d1'], seed['d2']],
        })
        assert preview.status_code == 200
        assert preview.get_json()['data']['rack_installs'] == 1
        deleted = admin_client.post('/api/v2/devices/batch-delete', json={
            'device_ids': [seed['d1'], seed['d2']],
        })
        assert deleted.status_code == 200
        assert deleted.get_json()['data']['count'] == 2
        with app.app_context():
            assert Device.query.filter(Device.id.in_([seed['d1'], seed['d2']])).count() == 0
            snapshot = RackInstall.query.get(install_id)
            assert snapshot.device_id is None
            assert snapshot.manual_name == 'SW-A'
            assert AuditLog.query.filter_by(action='device:batch_delete').count() == 1

    def test_invalid_member_rolls_back_whole_batch(self, admin_client, seed, app):
        response = admin_client.post('/api/v2/devices/batch-delete', json={
            'device_ids': [seed['d1'], 999999],
        })
        assert response.status_code == 400
        with app.app_context():
            assert Device.query.get(seed['d1']) is not None


class TestDeviceImportSync:
    def _make_xlsx(self, rows, headers=None):
        import io
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(headers or [
            '所属客户', '设备名称', '设备类型', 'IP地址', '是否在用',
            '安装位置', '电源配置', '额定功率',
        ])
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

    def test_import_persists_installation_and_power_choices(self, op_client, seed, app):
        xlsx = self._make_xlsx([
            ['设备API客户A', 'SW-POWER', '交换机', '10.0.0.6', '是', '背面', '四电源', 480],
        ])
        r = op_client.post('/api/v2/devices/import', data={
            'import_file': (xlsx, 'devices.xlsx')},
            content_type='multipart/form-data')
        assert r.status_code == 200
        assert r.get_json()['data']['created'] == 1
        with app.app_context():
            device = Device.query.filter_by(device_name='SW-POWER').one()
            assert device.location == '背面'
            assert device.power_supply == '四电源'
            assert device.rated_power_w == 480

    def test_import_batch_id_is_idempotent(self, op_client, seed, app):
        raw = self._make_xlsx([
            ['设备API客户A', 'SW-IDEMPOTENT', '交换机', '10.0.0.7', '是'],
        ]).getvalue()
        form = {
            'import_file': (io.BytesIO(raw), 'devices.xlsx'),
            'batch_id': 'batch-idempotency-001',
        }
        first = op_client.post('/api/v2/devices/import', data=form,
                               content_type='multipart/form-data')
        assert first.status_code == 200
        assert first.get_json()['data']['created'] == 1
        second = op_client.post('/api/v2/devices/import', data={
            'import_file': (io.BytesIO(raw), 'devices.xlsx'),
            'batch_id': 'batch-idempotency-001',
        }, content_type='multipart/form-data')
        assert second.status_code == 200
        assert second.get_json()['data']['duplicate_submission'] is True
        with app.app_context():
            assert Device.query.filter_by(device_name='SW-IDEMPOTENT').count() == 1

    def test_import_creates_distinct_same_name_rows(self, op_client, seed, app):
        """Excel 一行代表一台设备；同客户同名但 IP 不同不能被误合并。"""
        xlsx = self._make_xlsx([
            ['设备API客户A', 'SW-DUP-ROW', '交换机', '10.0.0.8', '是'],
            ['设备API客户A', 'SW-DUP-ROW', '交换机', '10.0.0.9', '是'],
        ])
        response = op_client.post('/api/v2/devices/import', data={
            'import_file': (xlsx, 'duplicates.xlsx'),
            'mode': 'upsert',
        }, content_type='multipart/form-data')
        assert response.status_code == 200
        data = response.get_json()['data']
        assert data['failed'] == 0
        assert data['created'] == 2
        with app.app_context():
            devices = Device.query.filter_by(device_name='SW-DUP-ROW').all()
            assert {item.ip_address for item in devices} == {'10.0.0.8', '10.0.0.9'}

    def test_import_reclaims_deleted_device_rack_snapshot(
            self, admin_client, seed, app):
        """删除后保留的机柜快照应回接新设备，不能误报 U 位冲突。"""
        from models import Rack, RackInstall
        with app.app_context():
            rack = Rack(customer_id=seed['c1'], name='12', location='中心机房')
            db.session.add(rack)
            db.session.flush()
            device = Device.query.get(seed['d1'])
            device.location = '背面'
            device.model = 'S5720'
            db.session.add(RackInstall(
                rack_id=rack.id, device_id=device.id, start_u=19, occupy_u=2,
                install_side='背面'))
            db.session.commit()
            rack_id = rack.id
            install_id = RackInstall.query.filter_by(device_id=device.id).one().id

        deleted = admin_client.post('/api/v2/devices/batch-delete', json={
            'device_ids': [seed['d1']],
        })
        assert deleted.status_code == 200

        headers = [
            '所属客户', '设备名称', '品牌', '型号', 'IP地址', '安装位置',
            '机房位置', '机柜号', '起始U位', '占用U数', '是否在用',
        ]
        raw = self._make_xlsx([[
            '设备API客户A', 'SW-A', '华为', 'S5720', '10.0.0.1', '背面',
            '中心机房', '12', 19, 2, '是',
        ]], headers).getvalue()
        preview = admin_client.post('/api/v2/devices/import', data={
            'import_file': (io.BytesIO(raw), 'reclaim.xlsx'),
            'dry_run': '1',
        }, content_type='multipart/form-data')
        preview_data = preview.get_json()['data']
        assert preview.status_code == 200
        assert preview_data['failed'] == 0
        assert preview_data['create'] == 1

        execute = admin_client.post('/api/v2/devices/import', data={
            'import_file': (io.BytesIO(raw), 'reclaim.xlsx'),
            'batch_id': preview_data['batch_id'],
        }, content_type='multipart/form-data')
        assert execute.status_code == 200, execute.get_json()
        with app.app_context():
            new_device = Device.query.filter_by(
                customer_id=seed['c1'], device_name='SW-A').one()
            install = RackInstall.query.get(install_id)
            assert install.rack_id == rack_id
            assert install.device_id == new_device.id
            assert install.install_side == '背面'
            assert RackInstall.query.filter_by(rack_id=rack_id).count() == 1

    def test_import_allows_same_u_on_opposite_sides(self, admin_client, seed, app):
        """同 U 的旧快照可按工作簿正反面分别回接。"""
        from models import Rack, RackInstall
        with app.app_context():
            rack = Rack(customer_id=seed['c1'], name='13', location='中心机房')
            db.session.add(rack)
            db.session.flush()
            db.session.add_all([
                RackInstall(rack_id=rack.id, manual_name='正面设备',
                            manual_ip='10.0.1.1', start_u=23, occupy_u=1),
                RackInstall(rack_id=rack.id, manual_name='背面设备',
                            manual_ip='10.0.1.2', start_u=23, occupy_u=1),
            ])
            db.session.commit()
            rack_id = rack.id
        headers = [
            '所属客户', '设备名称', 'IP地址', '安装位置', '机房位置', '机柜号',
            '起始U位', '占用U数', '是否在用',
        ]
        xlsx = self._make_xlsx([
            ['设备API客户A', '正面设备', '10.0.1.1', '正面', '中心机房', '13', 23, 1, '是'],
            ['设备API客户A', '背面设备', '10.0.1.2', '背面', '中心机房', '13', 23, 1, '是'],
        ], headers)
        response = admin_client.post('/api/v2/devices/import', data={
            'import_file': (xlsx, 'opposite-sides.xlsx'),
        }, content_type='multipart/form-data')
        assert response.status_code == 200, response.get_json()
        result = response.get_json()['data']
        assert result['failed'] == 0
        assert result['created'] == 2
        with app.app_context():
            installs = RackInstall.query.filter_by(rack_id=rack_id, start_u=23).all()
            assert len(installs) == 2
            assert all(item.device_id for item in installs)
            assert {item.install_side for item in installs} == {'正面', '背面'}

    def test_update_mode_does_not_reject_unmatched_same_name_rows(self, op_client, seed):
        """仅更新时，不存在的同名行都应跳过，不能在匹配前误判为同一设备。"""
        xlsx = self._make_xlsx([
            ['设备API客户A', '尚未入库服务器', '服务器', '', '是'],
            ['设备API客户A', '尚未入库服务器', '服务器', '', '是'],
        ])
        response = op_client.post('/api/v2/devices/import', data={
            'import_file': (xlsx, 'update-unmatched.xlsx'),
            'mode': 'update',
            'dry_run': '1',
        }, content_type='multipart/form-data')
        data = response.get_json()['data']
        assert response.status_code == 200
        assert data['failed'] == 0
        assert data['skipped'] == 2
        assert len(data['skip_details']) == 2
        assert data['skip_details'][0]['row'] == 2
        assert '系统中不存在可更新的正式设备' in data['skip_details'][0]['reason']
        assert '仅新增' in data['skip_details'][0]['reason']

    def test_update_legacy_duplicate_names_by_rack_position(self, op_client, seed, app):
        """旧模板无设备ID时，用机柜号+起始U位精确更新真实同名设备。"""
        from models import Rack, RackInstall
        with app.app_context():
            rack = Rack(customer_id=seed['c1'], name='12', location='中心机房')
            db.session.add(rack)
            db.session.flush()
            first = Device(customer_id=seed['c1'], device_name='防汛二期服务器',
                           device_type='服务器', model='旧型号-1')
            second = Device(customer_id=seed['c1'], device_name='防汛二期服务器',
                            device_type='服务器', model='旧型号-2')
            db.session.add_all([first, second])
            db.session.flush()
            first_id, second_id = first.id, second.id
            db.session.add_all([
                RackInstall(rack_id=rack.id, device_id=first.id, start_u=19, occupy_u=2),
                RackInstall(rack_id=rack.id, device_id=second.id, start_u=16, occupy_u=2),
            ])
            db.session.commit()
        headers = [
            '所属客户', '设备名称', '设备类型', '型号', '机房位置', '机柜号',
            '起始U位', '占用U数', '是否在用',
        ]
        raw = self._make_xlsx([
            ['设备API客户A', '防汛二期服务器', '服务器', '新型号-19U',
             '中心机房', '12', 19, 2, '是'],
            ['设备API客户A', '防汛二期服务器', '服务器', '新型号-16U',
             '中心机房', '12', 16, 2, '是'],
        ], headers).getvalue()
        preview = op_client.post('/api/v2/devices/import', data={
            'import_file': (io.BytesIO(raw), 'legacy-update.xlsx'),
            'mode': 'update',
            'dry_run': '1',
        }, content_type='multipart/form-data')
        preview_data = preview.get_json()['data']
        assert preview.status_code == 200
        assert preview_data['failed'] == 0
        assert preview_data['update'] == 2
        execute = op_client.post('/api/v2/devices/import', data={
            'import_file': (io.BytesIO(raw), 'legacy-update.xlsx'),
            'mode': 'update',
            'batch_id': preview_data['batch_id'],
        }, content_type='multipart/form-data')
        assert execute.status_code == 200
        with app.app_context():
            assert db.session.get(Device, first_id).model == '新型号-19U'
            assert db.session.get(Device, second_id).model == '新型号-16U'


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
        assert data['network_types'] == ['内网', '外网']
        assert len(data['customers']) >= 2
        assert data['installation_positions'] == ['正面', '背面']
        assert data['power_supplies'] == ['单电源', '双电源', '四电源']
        assert data['login_methods'] == ['SSH', 'Telnet', 'Web', 'SNMP', '本地串口']

    def test_tree_three_levels(self, admin_client, seed, app):
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
        r = admin_client.get('/api/devices/tree')
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
