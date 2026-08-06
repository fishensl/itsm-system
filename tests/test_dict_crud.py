# -*- coding: utf-8 -*-
"""W3-R5 字典 CRUD 回归（SSR 路由已剥离 → Vue /api/device-dicts/* 等价契约）"""
import pytest

from models import db, DeviceType, Brand, NetworkType, CustomField


class TestDeviceType:
    def test_add(self, op_client, app):
        r = op_client.post('/api/device-dicts/types', json={'name': '负载均衡器', 'sort_order': 9})
        assert r.status_code == 200
        with app.app_context():
            dt = DeviceType.query.filter_by(name='负载均衡器').first()
            assert dt is not None and dt.sort_order == 9

    def test_update(self, op_client, app):
        with app.app_context():
            dt = DeviceType(name='旧名', sort_order=1)
            db.session.add(dt)
            db.session.commit()
            did = dt.id
        r = op_client.put(f'/api/device-dicts/types/{did}', json={'name': '新名', 'sort_order': 5})
        assert r.status_code == 200
        with app.app_context():
            dt = DeviceType.query.get(did)
            assert dt.name == '新名' and dt.sort_order == 5

    def test_delete(self, admin_client, app):
        """删除需 device:delete（operator 无此权限，admin 走全量短路）"""
        with app.app_context():
            dt = DeviceType(name='待删')
            db.session.add(dt)
            db.session.commit()
            did = dt.id
        r = admin_client.delete(f'/api/device-dicts/types/{did}')
        assert r.status_code == 200
        with app.app_context():
            assert DeviceType.query.get(did) is None

    def test_add_without_name_rejected(self, op_client, app):
        r = op_client.post('/api/device-dicts/types', json={'name': '  '})
        assert r.status_code == 400
        with app.app_context():
            assert DeviceType.query.filter_by(name='').first() is None


class TestOtherDicts:
    @pytest.mark.parametrize('resource,model', [
        ('brands', Brand),
        ('network-types', NetworkType),
    ])
    def test_full_cycle(self, op_client, admin_client, app, resource, model):
        r = op_client.post(f'/api/device-dicts/{resource}', json={'name': '测试项', 'sort_order': 2})
        assert r.status_code == 200
        with app.app_context():
            obj = model.query.filter_by(name='测试项').first()
            assert obj is not None
            oid = obj.id
        r = op_client.put(f'/api/device-dicts/{resource}/{oid}', json={'name': '测试项2'})
        assert r.status_code == 200
        with app.app_context():
            assert model.query.get(oid).name == '测试项2'
        r = admin_client.delete(f'/api/device-dicts/{resource}/{oid}')
        assert r.status_code == 200
        with app.app_context():
            assert model.query.get(oid) is None

    def test_custom_field_type_passthrough(self, op_client, app):
        r = op_client.post('/api/device-dicts/custom-fields',
                           json={'name': '机房位置', 'field_type': 'date'})
        assert r.status_code == 200
        with app.app_context():
            f = CustomField.query.filter_by(name='机房位置').first()
            assert f is not None and f.field_type == 'date'

    def test_viewer_cannot_add(self, viewer_client):
        """viewer 有 device:view（可 GET），无 device:edit → POST 403"""
        r = viewer_client.post('/api/device-dicts/brands', json={'name': 'X'})
        assert r.status_code == 403

    def test_list_returns_items(self, op_client):
        for p in ('/api/device-dicts/types', '/api/device-dicts/brands',
                  '/api/device-dicts/network-types', '/api/device-dicts/custom-fields'):
            r = op_client.get(p)
            assert r.status_code == 200
            assert r.get_json()['code'] == 0
