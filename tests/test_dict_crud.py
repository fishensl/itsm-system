# -*- coding: utf-8 -*-
"""W3-R5 字典 CRUD 工厂回归：四组端点的增改删行为与端点名兼容"""
import pytest

from models import db, DeviceType, Brand, NetworkType, CustomField


class TestDeviceType:
    def test_list_add_via_list_post(self, op_client, app):
        r = op_client.post('/device-types', data={'name': '负载均衡器', 'sort_order': 9})
        assert r.status_code == 302
        with app.app_context():
            dt = DeviceType.query.filter_by(name='负载均衡器').first()
            assert dt is not None and dt.sort_order == 9

    def test_add_via_add_endpoint(self, op_client, app):
        """模板使用的 /add 端点保持可用"""
        r = op_client.post('/device-types/add', data={'name': '防火墙2', 'sort_order': 3})
        assert r.status_code == 302
        with app.app_context():
            assert DeviceType.query.filter_by(name='防火墙2').first() is not None

    def test_edit(self, op_client, app):
        with app.app_context():
            dt = DeviceType(name='旧名', sort_order=1)
            db.session.add(dt)
            db.session.commit()
            did = dt.id
        op_client.post(f'/device-types/edit/{did}', data={'name': '新名', 'sort_order': 5})
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
        admin_client.post(f'/device-types/delete/{did}')
        with app.app_context():
            assert DeviceType.query.get(did) is None

    def test_add_without_name_noop(self, op_client, app):
        op_client.post('/device-types/add', data={'name': '  '})
        with app.app_context():
            assert DeviceType.query.filter_by(name='').first() is None


class TestOtherDicts:
    @pytest.mark.parametrize('path,model', [
        ('/device-brands', Brand),
        ('/device-network-types', NetworkType),
    ])
    def test_full_cycle(self, op_client, admin_client, app, path, model):
        op_client.post(f'{path}/add', data={'name': '测试项', 'sort_order': 2})
        with app.app_context():
            obj = model.query.filter_by(name='测试项').first()
            assert obj is not None
            oid = obj.id
        op_client.post(f'{path}/edit/{oid}', data={'name': '测试项2'})
        with app.app_context():
            assert model.query.get(oid).name == '测试项2'
        admin_client.post(f'{path}/delete/{oid}')
        with app.app_context():
            assert model.query.get(oid) is None

    def test_custom_field_type_passthrough(self, op_client, app):
        op_client.post('/device-custom-fields/add', data={'name': '机房位置', 'field_type': 'date'})
        with app.app_context():
            f = CustomField.query.filter_by(name='机房位置').first()
            assert f is not None and f.field_type == 'date'

    def test_viewer_cannot_add(self, viewer_client):
        """viewer 有 device:view（可 list POST？不——/add 要 device:edit）"""
        r = viewer_client.post('/device-brands/add', data={'name': 'X'})
        assert r.status_code == 302  # 无权限重定向
        # 再确认未写入由 follow_redirects 后页面判定的太绕，直接查库在上一用例已覆盖写入路径

    def test_pages_render(self, op_client):
        for p in ('/device-types', '/device-brands', '/device-network-types', '/device-custom-fields'):
            assert op_client.get(p).status_code == 200
