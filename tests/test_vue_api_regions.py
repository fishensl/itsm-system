# -*- coding: utf-8 -*-
"""Vue API：地区管理 + 单位类别"""
from models import db, Region, CustomerCategory, Customer


class TestRegionApi:
    def test_tree_and_crud(self, admin_client, app):
        with app.app_context():
            c1 = Region(name='成都市')
            c2 = Region(name='绵阳市')
            db.session.add_all([c1, c2])
            db.session.flush()
            db.session.add(Region(name='高新区', parent_id=c1.id, sort_order=1))
            db.session.add(Region(name='武侯区', parent_id=c1.id, sort_order=2))
            db.session.commit()
            cid = c1.id
        r = admin_client.get('/api/regions')
        assert r.get_json()['code'] == 0
        cities = r.get_json()['data']
        assert len(cities) == 2
        chengdu = next(c for c in cities if c['id'] == cid)
        assert [d['name'] for d in chengdu['children']] == ['高新区', '武侯区']

        # 新增区县
        r = admin_client.post('/api/regions', json={'name': '金牛区', 'parent_id': cid})
        assert r.get_json()['code'] == 0
        with app.app_context():
            jn = Region.query.filter_by(name='金牛区').first()
            assert jn.parent_id == cid
            jn_id = jn.id
        # 编辑
        r = admin_client.put(f'/api/regions/{jn_id}', json={'name': '金牛北区', 'parent_id': cid, 'sort_order': 9})
        assert r.get_json()['code'] == 0
        # 删除有子地区的地市被拒
        r = admin_client.delete(f'/api/regions/{cid}')
        assert r.status_code == 400
        # 删除子地区成功
        r = admin_client.delete(f'/api/regions/{jn_id}')
        assert r.get_json()['code'] == 0

    def test_name_required(self, admin_client):
        r = admin_client.post('/api/regions', json={'name': '  '})
        assert r.status_code == 400
        r = admin_client.post('/api/regions', json={})
        assert r.status_code == 400

    def test_duplicate_same_level(self, admin_client, app):
        with app.app_context():
            db.session.add(Region(name='成都市'))
            db.session.commit()
        r = admin_client.post('/api/regions', json={'name': '成都市'})
        assert r.status_code == 400

    def test_permissions(self, viewer_client):
        assert viewer_client.get('/api/regions').status_code == 200
        assert viewer_client.post('/api/regions', json={'name': 'x'}).status_code == 403
        assert viewer_client.delete('/api/regions/1').status_code == 403


class TestCategoryApi:
    def test_crud(self, admin_client, app):
        with app.app_context():
            db.session.add(CustomerCategory(name='水利局', sort_order=1))
            db.session.commit()
        r = admin_client.get('/api/customer-categories')
        assert [c['name'] for c in r.get_json()['data']] == ['水利局']
        r = admin_client.post('/api/customer-categories', json={'name': '水文局', 'sort_order': 2})
        assert r.get_json()['code'] == 0
        r = admin_client.post('/api/customer-categories', json={'name': '水利局'})
        assert r.status_code == 400  # 唯一

    def test_delete_blocked_when_in_use(self, admin_client, app):
        with app.app_context():
            cat = CustomerCategory(name='电力公司', sort_order=1)
            db.session.add(cat)
            db.session.flush()
            db.session.add(Customer(name='XX 供电局', category_id=cat.id))
            db.session.commit()
            cid = cat.id
        r = admin_client.delete(f'/api/customer-categories/{cid}')
        assert r.status_code == 400

    def test_permissions(self, viewer_client, op_client):
        assert viewer_client.get('/api/customer-categories').status_code == 200
        assert viewer_client.post('/api/customer-categories', json={'name': 'x'}).status_code == 403
        assert op_client.delete('/api/customer-categories/1').status_code == 403
