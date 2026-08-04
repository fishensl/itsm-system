# -*- coding: utf-8 -*-
"""Vue API：设备字典（类型/品牌/网络类型/自定义字段 CRUD）"""
from models import db, DeviceType, Brand, NetworkType, CustomField


def _seed(app):
    with app.app_context():
        db.session.add(DeviceType(name='交换机', sort_order=1))
        db.session.add(DeviceType(name='路由器', sort_order=2))
        db.session.add(Brand(name='华为', sort_order=1))
        db.session.add(NetworkType(name='内网', sort_order=1))
        db.session.add(CustomField(name='资产编号', field_type='text', sort_order=1))
        db.session.add(CustomField(name='上架日期', field_type='date', sort_order=2))
        db.session.commit()


class TestDeviceDictApi:
    def test_list(self, admin_client, app):
        _seed(app)
        r = admin_client.get('/api/device-dicts/types')
        assert r.get_json()['code'] == 0
        names = [i['name'] for i in r.get_json()['data']]
        assert names == ['交换机', '路由器']

        r = admin_client.get('/api/device-dicts/custom-fields')
        fields = r.get_json()['data']
        assert fields[0]['field_type'] == 'text'
        assert fields[1]['field_type'] == 'date'

    def test_crud_flow(self, admin_client, app):
        _seed(app)
        r = admin_client.post('/api/device-dicts/types', json={'name': '防火墙', 'sort_order': 3})
        assert r.get_json()['code'] == 0
        tid = r.get_json()['data']['id']
        r = admin_client.put(f'/api/device-dicts/types/{tid}', json={'name': '下一代防火墙', 'sort_order': 3})
        assert r.get_json()['code'] == 0
        with app.app_context():
            t = db.session.get(DeviceType, tid)
            assert t.name == '下一代防火墙'
        r = admin_client.delete(f'/api/device-dicts/types/{tid}')
        assert r.get_json()['code'] == 0
        with app.app_context():
            assert db.session.get(DeviceType, tid) is None

    def test_name_required_and_unique(self, admin_client, app):
        _seed(app)
        r = admin_client.post('/api/device-dicts/brands', json={'name': '  '})
        assert r.status_code == 400
        r = admin_client.post('/api/device-dicts/brands', json={'name': '华为'})
        assert r.status_code == 400  # 唯一约束

    def test_field_type_default(self, admin_client, app):
        _seed(app)
        r = admin_client.post('/api/device-dicts/custom-fields', json={'name': '负责人', 'sort_order': 3})
        assert r.get_json()['code'] == 0
        with app.app_context():
            f = CustomField.query.filter_by(name='负责人').first()
            assert f.field_type == 'text'

    def test_permissions(self, viewer_client, op_client):
        assert viewer_client.get('/api/device-dicts/types').status_code == 200
        assert viewer_client.post('/api/device-dicts/types', json={'name': 'x'}).status_code == 403
        assert op_client.delete('/api/device-dicts/types/1').status_code == 403

    def test_network_types_order_by_id(self, admin_client, app):
        _seed(app)
        with app.app_context():
            db.session.add(NetworkType(name='外网', sort_order=99))
            db.session.commit()
        r = admin_client.get('/api/device-dicts/network-types')
        assert [i['name'] for i in r.get_json()['data']] == ['内网', '外网']
