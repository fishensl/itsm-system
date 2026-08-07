# -*- coding: utf-8 -*-
"""P2 客户 Vue API：列表/筛选/详情/增删改/字典"""
import pytest

from models import db, Customer, Region, CustomerCategory, Device


@pytest.fixture()
def seed(app):
    with app.app_context():
        cat_a = CustomerCategory(name='水利局')
        cat_b = CustomerCategory(name='水文局')
        db.session.add_all([cat_a, cat_b])
        city = Region(name='杭州市')
        db.session.add(city)
        db.session.flush()
        dist = Region(name='西湖区', parent_id=city.id)
        db.session.add(dist)
        db.session.flush()
        c1 = Customer(name='API客户A', contact_person='张三', phone='13800000001',
                      level='核心', has_onsite=True, category_id=cat_a.id,
                      region_id=dist.id, city='杭州市', device_count=5,
                      extra_fields='[{"name": "客户经理", "value": "王五"}]')
        c2 = Customer(name='API客户B', contact_person='李四', phone='13800000002',
                      level='常规', category_id=cat_b.id, region_id=city.id)
        db.session.add_all([c1, c2])
        db.session.commit()
        yield {'c1': c1.id, 'c2': c2.id,
               'cat_a': cat_a.id, 'cat_b': cat_b.id,
               'city': city.id, 'dist': dist.id}


class TestCustomerList:
    def test_list_shape(self, op_client, seed):
        r = op_client.get('/api/customers')
        assert r.status_code == 200
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['total'] == 2
        assert data['page'] == 1
        item = data['items'][0]
        assert set(['id', 'name', 'contact_person', 'phone', 'email', 'level',
                    'city', 'address', 'has_onsite', 'device_count',
                    'category_name', 'region_name']).issubset(item.keys())

    def test_list_names_joined(self, op_client, seed):
        data = op_client.get('/api/customers').get_json()['data']
        by_id = {i['id']: i for i in data['items']}
        assert by_id[seed['c1']]['category_name'] == '水利局'
        assert by_id[seed['c1']]['region_name'] == '西湖区'
        assert by_id[seed['c1']]['has_onsite'] is True
        assert by_id[seed['c1']]['has_onsite_label'] == '有'
        assert by_id[seed['c2']]['region_name'] == '杭州市'

    def test_search_by_name(self, op_client, seed):
        data = op_client.get('/api/customers', query_string={'search': '客户A'}).get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['name'] == 'API客户A'

    def test_search_by_contact_and_phone(self, op_client, seed):
        data = op_client.get('/api/customers', query_string={'search': '李四'}).get_json()['data']
        assert data['total'] == 1
        data = op_client.get('/api/customers', query_string={'search': '13800000001'}).get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['name'] == 'API客户A'

    def test_filter_category(self, op_client, seed):
        data = op_client.get('/api/customers', query_string={'category_id': seed['cat_a']}).get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['name'] == 'API客户A'

    def test_filter_region(self, op_client, seed):
        data = op_client.get('/api/customers', query_string={'region_id': seed['city']}).get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['name'] == 'API客户B'

    def test_filter_level(self, op_client, seed):
        data = op_client.get('/api/customers', query_string={'level': '核心'}).get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['name'] == 'API客户A'

    def test_pagination(self, op_client, seed):
        data = op_client.get('/api/customers', query_string={'page': 1, 'page_size': 1}).get_json()['data']
        assert data['total'] == 2
        assert len(data['items']) == 1

    def test_requires_login(self, client, seed):
        assert client.get('/api/customers').status_code == 401

    def test_forbidden_without_perm(self, client, app, seed):
        """未登录会话打 /api/customers 需 401；viewer 有 customer:view 可访问"""
        r = app.test_client().get('/api/customers')
        assert r.status_code == 401


class TestCustomerDetail:
    def test_detail_shape(self, op_client, seed):
        r = op_client.get(f"/api/customers/{seed['c1']}")
        assert r.status_code == 200
        d = r.get_json()['data']
        assert d['name'] == 'API客户A'
        assert d['category_name'] == '水利局'
        assert d['region_name'] == '西湖区'
        assert d['city'] == '杭州市'
        # extra_fields 解析为 [{name, value}]
        assert d['extra_fields'] == [{'name': '客户经理', 'value': '王五'}]
        # 关联统计
        assert d['device_count'] == 5
        assert d['inspection_count'] == 0
        assert d['ticket_count'] == 0

    def test_detail_counts(self, op_client, seed, app):
        with app.app_context():
            from models import Ticket, Inspection
            db.session.add(Ticket(number='WO-TEST-001', title='测试工单', customer_id=seed['c1']))
            db.session.add(Inspection(title='测试巡检', customer_id=seed['c1']))
            db.session.commit()
        d = op_client.get(f"/api/customers/{seed['c1']}").get_json()['data']
        assert d['inspection_count'] == 1
        assert d['ticket_count'] == 1

    def test_detail_not_found(self, op_client, seed):
        assert op_client.get('/api/customers/99999').status_code == 404


class TestCustomerCrud:
    def test_create(self, sales_client, seed, app):
        r = sales_client.post('/api/customers', json={
            'name': 'API客户C', 'contact_person': '赵六', 'phone': '13800000003',
            'email': 'c@example.com', 'category_id': seed['cat_a'],
            'region_id': seed['dist'], 'level': 'auto',
            'address': '文一西路100号', 'has_onsite': True,
            'onsite_contact': '赵六', 'onsite_phone': '13800000004', 'onsite_office': 'A101',
            'has_drill': False, 'remark': '测试',
            'extra_fields': [{'name': '客户经理', 'value': '王五'}],
        })
        assert r.status_code == 200
        with app.app_context():
            c = Customer.query.filter_by(name='API客户C').first()
            assert c is not None
            assert c.region_id == seed['dist']
            assert c.city == '杭州市'          # 区县 → 父地市
            assert c.has_onsite is True
            assert '客户经理' in c.extra_fields
            # 区县客户选 auto → 默认常规
            assert c.level == '常规'

    def test_create_auto_level_by_onsite(self, sales_client, seed, app):
        """市级客户 + 驻场 + auto → 自动定级为 重点"""
        r = sales_client.post('/api/customers', json={
            'name': 'API客户D', 'region_id': seed['city'],
            'level': 'auto', 'has_onsite': True,
        })
        assert r.status_code == 200
        with app.app_context():
            c = Customer.query.filter_by(name='API客户D').first()
            assert c.level == '重点'

    def test_create_explicit_level(self, sales_client, seed, app):
        r = sales_client.post('/api/customers', json={'name': 'API客户E', 'level': '核心'})
        assert r.status_code == 200
        with app.app_context():
            assert Customer.query.filter_by(name='API客户E').first().level == '核心'

    def test_create_duplicate_name(self, sales_client, seed):
        r = sales_client.post('/api/customers', json={'name': 'API客户A'})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1

    def test_create_empty_name(self, sales_client, seed):
        r = sales_client.post('/api/customers', json={'name': '  '})
        assert r.status_code == 400

    def test_create_forbidden_for_operator(self, op_client, seed):
        """operator 只有 customer:view，无 customer:add"""
        r = op_client.post('/api/customers', json={'name': '无权限客户'})
        assert r.status_code == 403

    def test_update(self, sales_client, seed, app):
        r = sales_client.put(f"/api/customers/{seed['c2']}", json={
            'name': 'API客户B-改名', 'contact_person': '更新联系人',
            'category_id': seed['cat_a'], 'region_id': seed['city'],
            'level': '重点', 'has_onsite': False, 'has_drill': True, 'remark': '改',
        })
        assert r.status_code == 200
        with app.app_context():
            c = Customer.query.get(seed['c2'])
            assert c.name == 'API客户B-改名'
            assert c.contact_person == '更新联系人'
            assert c.category_id == seed['cat_a']
            assert c.level == '重点'
            assert c.has_drill is True

    def test_update_duplicate_name(self, sales_client, seed):
        r = sales_client.put(f"/api/customers/{seed['c2']}", json={'name': 'API客户A'})
        assert r.status_code == 400

    def test_delete(self, admin_client, seed, app):
        r = admin_client.delete(f"/api/customers/{seed['c2']}")
        assert r.status_code == 200
        with app.app_context():
            assert Customer.query.get(seed['c2']) is None

    def test_delete_forbidden_for_sales(self, sales_client, seed):
        """sales 有 customer:add/edit 但无 delete"""
        r = sales_client.delete(f"/api/customers/{seed['c2']}")
        assert r.status_code == 403

    def test_delete_blocked_with_devices(self, admin_client, seed, app):
        with app.app_context():
            db.session.add(Device(customer_id=seed['c1'], device_name='SW-X'))
            db.session.commit()
        r = admin_client.delete(f"/api/customers/{seed['c1']}")
        assert r.status_code == 400
        with app.app_context():
            assert Customer.query.get(seed['c1']) is not None

    def test_delete_after_ghost_device_unlinked(self, admin_client, seed, app):
        """「设备数快照残留/幽灵设备」场景：解除残留引用后客户可删除"""
        from services.device_service import sync_customer_device_count
        with app.app_context():
            db.session.add(Device(customer_id=seed['c1'], device_name='幽灵设备'))
            db.session.commit()
            c = Customer.query.get(seed['c1'])
            c.device_count = 0  # 快照与 devices 表不一致（幽灵设备不可见）
            db.session.commit()
        r = admin_client.delete(f"/api/customers/{seed['c1']}")
        assert r.status_code == 400  # 真实 devices 表仍有残留 → 拦截
        # 修复：置空幽灵设备引用 + 重算快照（与 check_customer_refs --unlink 同路径）
        with app.app_context():
            for d in Device.query.filter_by(customer_id=seed['c1']).all():
                d.customer_id = None
            db.session.commit()
            sync_customer_device_count(seed['c1'])
        r = admin_client.delete(f"/api/customers/{seed['c1']}")
        assert r.status_code == 200
        with app.app_context():
            assert Customer.query.get(seed['c1']) is None


class TestCustomerDicts:
    def test_dicts_shape(self, op_client, seed):
        r = op_client.get('/api/dicts/customers')
        assert r.status_code == 200
        data = r.get_json()['data']
        assert any(c['name'] == '水利局' for c in data['customer_categories'])
        city = next(x for x in data['regions'] if x['name'] == '杭州市')
        assert city['parent_id'] is None
        dist = next(x for x in data['regions'] if x['name'] == '西湖区')
        assert dist['parent_id'] == city['id']
        assert data['levels'] == ['auto', '核心', '重点', '常规']
