# -*- coding: utf-8 -*-
"""Vue API：任务模板 + 设备检查模板"""
import json

from models import db, Customer, Device, InspectionTaskTemplate, InspectionDeviceTemplate


def _mk_device_template(app, name='网络设备模板', category='网络设备'):
    with app.app_context():
        t = InspectionDeviceTemplate(
            name=name, device_category=category, device_sub_type='核心',
            items_json=json.dumps([{'name': '电源检查', 'field_type': 'status_note'},
                                   {'name': '版本核对', 'field_type': 'version_check', 'min_version': 'V7'}],
                                  ensure_ascii=False),
            is_active=True)
        db.session.add(t)
        db.session.commit()
        return t.id


class TestTaskTemplateApi:
    def test_list_shape(self, admin_client, app):
        dtid = _mk_device_template(app)
        with app.app_context():
            t = InspectionTaskTemplate(
                name='季度任务模板', category='季度巡检', inspection_type='季度巡检',
                sections_json=json.dumps({'sections': [{'key': 'a', 'title': '主机', 'enabled': True}]}),
                is_active=True)
            db.session.add(t)
            db.session.flush()
            t.device_templates = [db.session.get(InspectionDeviceTemplate, dtid)]
            db.session.commit()
        r = admin_client.get('/api/task-templates')
        assert r.get_json()['code'] == 0
        d = r.get_json()['data']
        assert len(d['templates']) == 1
        tpl = d['templates'][0]
        assert tpl['sections'][0]['title'] == '主机'
        assert tpl['device_template_ids'] == [dtid]
        assert len(d['device_templates']) == 1

    def test_crud_with_device_order(self, admin_client, app):
        id1 = _mk_device_template(app, '模板一')
        id2 = _mk_device_template(app, '模板二')
        r = admin_client.post('/api/task-templates', json={
            'name': '新模板', 'category': '日常巡检', 'inspection_type': '月度巡检',
            'sections': [{'key': 's1', 'title': '第一章', 'enabled': True}],
            'device_template_ids': [id2, id1],
        })
        assert r.get_json()['code'] == 0
        tid = r.get_json()['data']['id']
        r = admin_client.get('/api/task-templates')
        tpl = r.get_json()['data']['templates'][0]
        assert tpl['device_template_ids'] == [id2, id1]  # 顺序保持
        r = admin_client.put(f'/api/task-templates/{tid}', json={
            'name': '新模板-改', 'category': '日常巡检', 'inspection_type': '月度巡检',
            'sections': [], 'device_template_ids': [id1],
        })
        assert r.get_json()['code'] == 0
        r = admin_client.delete(f'/api/task-templates/{tid}')
        assert r.get_json()['code'] == 0
        with app.app_context():
            assert db.session.get(InspectionTaskTemplate, tid) is None

    def test_name_required(self, admin_client):
        r = admin_client.post('/api/task-templates', json={'name': ''})
        assert r.status_code == 400

    def test_match_api(self, admin_client, app):
        dtid = _mk_device_template(app, '网络设备模板')
        with app.app_context():
            c = Customer(name='匹配客户')
            db.session.add(c)
            db.session.flush()
            db.session.add(Device(customer_id=c.id, device_name='SW', device_type='网络设备',
                                  brand='华为', model='S5735', is_in_use=True))
            db.session.commit()
            cid = c.id
        r = admin_client.get(f'/api/task-templates/match/{cid}')
        assert r.get_json()['code'] == 0
        d = r.get_json()['data']
        assert d['total_devices'] == 1
        assert d['groups'][0]['device_category'] == '网络设备'
        assert d['groups'][0]['matched_templates'][0]['id'] == dtid
        assert d['groups'][0]['matched_templates'][0]['match_score'] == 100


class TestDeviceCheckTemplateApi:
    def test_grouped_list(self, admin_client, app):
        _mk_device_template(app)
        r = admin_client.get('/api/device-check-templates')
        assert r.get_json()['code'] == 0
        d = r.get_json()['data']
        assert d['category_order'][0] == '服务器'
        assert len(d['groups']['网络设备']) == 1
        assert d['groups']['网络设备'][0]['total_sub_items'] == 2

    def test_crud(self, admin_client, app):
        tid = _mk_device_template(app)
        r = admin_client.post('/api/device-check-templates', json={
            'name': '服务器检查', 'device_category': '服务器',
            'items': [{'name': 'CPU 状态', 'field_type': 'status_note'}],
        })
        assert r.get_json()['code'] == 0
        nid = r.get_json()['data']['id']
        r = admin_client.put(f'/api/device-check-templates/{nid}', json={
            'name': '服务器检查-改', 'device_category': '服务器',
            'items': [{'name': 'CPU 状态', 'field_type': 'status_note'},
                      {'name': '内存', 'field_type': 'percentage'}],
        })
        assert r.get_json()['code'] == 0
        with app.app_context():
            t = db.session.get(InspectionDeviceTemplate, nid)
            assert len(json.loads(t.items_json)) == 2
        r = admin_client.delete(f'/api/device-check-templates/{tid}')
        assert r.get_json()['code'] == 0

    def test_invalid_items(self, admin_client):
        r = admin_client.post('/api/device-check-templates', json={'name': 'x', 'items': 'not-list'})
        assert r.status_code == 400
        r = admin_client.post('/api/device-check-templates', json={'name': '', 'items': []})
        assert r.status_code == 400

    def test_permissions(self, viewer_client, op_client):
        assert viewer_client.get('/api/device-check-templates').status_code == 200
        assert viewer_client.post('/api/device-check-templates', json={'name': 'x', 'items': []}).status_code == 403
        assert op_client.delete('/api/device-check-templates/1').status_code == 403
