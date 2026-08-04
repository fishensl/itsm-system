# -*- coding: utf-8 -*-
"""Vue API：固件版本库（分组列表/CRUD/is_latest 互斥）"""

from models import db, DeviceFirmware, Device, Customer


def _seed(app):
    with app.app_context():
        db.session.add(DeviceFirmware(brand='华为', model='S5735', firmware_type='系统固件',
                                      version='V2R20', is_latest=True))
        db.session.add(DeviceFirmware(brand='华为', model='S5735', firmware_type='系统固件',
                                      version='V2R19', is_latest=False))
        db.session.add(DeviceFirmware(brand='华为', model='S5735', firmware_type='规则库',
                                      version='R1', is_latest=True))
        db.session.commit()


class TestFirmwareApi:
    def test_grouped_list(self, admin_client, app):
        _seed(app)
        r = admin_client.get('/api/firmwares')
        assert r.get_json()['code'] == 0
        d = r.get_json()['data']
        assert len(d['groups']) == 1
        g = d['groups'][0]
        assert g['brand'] == '华为' and g['model'] == 'S5735'
        sys_items = next(t for t in g['types'] if t['firmware_type'] == '系统固件')['items']
        # is_latest 在前
        assert sys_items[0]['version'] == 'V2R20'
        assert sys_items[0]['is_latest'] is True
        assert d['all_brands'] == ['华为']

    def test_latest_mutual_exclusion(self, admin_client, app):
        _seed(app)
        with app.app_context():
            new_id = DeviceFirmware.query.filter_by(version='V3R00').first()
            assert new_id is None
        r = admin_client.post('/api/firmwares', json={
            'brand': '华为', 'model': 'S5735', 'firmware_type': '系统固件',
            'version': 'V3R00', 'is_latest': True,
        })
        assert r.get_json()['code'] == 0
        with app.app_context():
            latest = DeviceFirmware.query.filter_by(
                brand='华为', model='S5735', firmware_type='系统固件', is_latest=True).all()
            assert len(latest) == 1
            assert latest[0].version == 'V3R00'

    def test_required_fields(self, admin_client):
        r = admin_client.post('/api/firmwares', json={'brand': '', 'model': '', 'version': ''})
        assert r.status_code == 400
        r = admin_client.post('/api/firmwares', json={'brand': 'H', 'model': 'M', 'version': 'V1'})
        assert r.get_json()['code'] == 0

    def test_crud_and_filter(self, admin_client, app):
        _seed(app)
        r = admin_client.get('/api/firmwares?brand=华为&firmware_type=规则库')
        d = r.get_json()['data']
        assert len(d['groups']) == 1
        assert d['groups'][0]['types'][0]['firmware_type'] == '规则库'
        with app.app_context():
            fw = DeviceFirmware.query.filter_by(version='R1').first()
            fid = fw.id
        r = admin_client.put(f'/api/firmwares/{fid}', json={
            'brand': '华为', 'model': 'S5735', 'firmware_type': '规则库', 'version': 'R2',
            'is_latest': True,
        })
        assert r.get_json()['code'] == 0
        r = admin_client.delete(f'/api/firmwares/{fid}')
        assert r.get_json()['code'] == 0
        with app.app_context():
            assert db.session.get(DeviceFirmware, fid) is None

    def test_group_devices(self, admin_client, app):
        _seed(app)
        with app.app_context():
            c = Customer(name='固件客户')
            db.session.add(c)
            db.session.flush()
            db.session.add(Device(customer_id=c.id, device_name='SW-01', brand='华为',
                                  model='S5735', os_version='V2R19'))
            db.session.commit()
        r = admin_client.get('/api/firmwares')
        g = r.get_json()['data']['groups'][0]
        assert len(g['devices']) == 1
        assert g['devices'][0]['name'] == 'SW-01'

    def test_permissions(self, viewer_client, op_client):
        assert viewer_client.get('/api/firmwares').status_code == 200
        assert viewer_client.post('/api/firmwares', json={'brand': 'a', 'model': 'b', 'version': 'v'}).status_code == 403
        assert op_client.delete('/api/firmwares/1').status_code == 403
