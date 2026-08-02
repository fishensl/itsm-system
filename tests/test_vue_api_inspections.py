# -*- coding: utf-8 -*-
"""P2 巡检 Vue API：列表/筛选/详情/创建/更新/审核流/删除/字典/权限"""
import pytest

from models import db, Customer, Inspection, User


@pytest.fixture()
def seed(app):
    with app.app_context():
        c = Customer(name='巡检API客户')
        db.session.add(c)
        db.session.flush()
        i1 = Inspection(title='核心机房月度巡检', customer_id=c.id,
                        overall_status='正常', review_status='', inspector_name='op')
        i2 = Inspection(title='季度巡检-待审核', customer_id=c.id,
                        overall_status='待审核', review_status='待审核', inspector_name='op',
                        content_json='[{"name": "电源检查"}]',
                        field_values_json='{"机房A": {"电源": "正常"}}',
                        sections_json='{"sections": [{"title": "基础信息"}]}',
                        review_comment='')
        db.session.add_all([i1, i2])
        db.session.commit()
        yield {'c': c.id, 'i1': i1.id, 'i2': i2.id}


class TestInspectionList:
    def test_list_shape(self, op_client, seed):
        r = op_client.get('/api/inspections')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['total'] == 2
        assert data['page'] == 1
        item = {i['title']: i for i in data['items']}['核心机房月度巡检']
        assert item['customer_name'] == '巡检API客户'
        assert item['review_status'] == '草稿'
        assert item['overall_status'] == '正常'
        assert item['inspector_name'] == 'op'
        assert item['report_file'] is False
        assert item['report_label'] == '无'
        assert 'content_json' not in item  # 列表不带详情 JSON

    def test_filter_search(self, op_client, seed):
        r = op_client.get('/api/inspections', query_string={'search': '季度'})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['title'] == '季度巡检-待审核'

    def test_filter_status(self, op_client, seed):
        r = op_client.get('/api/inspections', query_string={'status': '正常'})
        assert r.get_json()['data']['total'] == 1

    def test_filter_review_status(self, op_client, seed):
        r = op_client.get('/api/inspections', query_string={'review_status': '草稿'})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['title'] == '核心机房月度巡检'
        r = op_client.get('/api/inspections', query_string={'review_status': '待审核'})
        assert r.get_json()['data']['total'] == 1

    def test_filter_customer(self, op_client, seed):
        r = op_client.get('/api/inspections', query_string={'customer_id': seed['c']})
        assert r.get_json()['data']['total'] == 2

    def test_pagination(self, op_client, seed):
        r = op_client.get('/api/inspections', query_string={'page': 1, 'page_size': 1})
        data = r.get_json()['data']
        assert data['total'] == 2
        assert len(data['items']) == 1


class TestInspectionDetail:
    def test_detail_parses_json_fields(self, op_client, seed):
        r = op_client.get(f"/api/inspections/{seed['i2']}")
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['title'] == '季度巡检-待审核'
        assert data['review_status'] == '待审核'
        assert data['content_json'] == [{'name': '电源检查'}]
        assert data['field_values_json'] == {'机房A': {'电源': '正常'}}
        assert data['sections_json'] == {'sections': [{'title': '基础信息'}]}
        assert 'review_comment' in data
        assert 'created_at' in data


class TestInspectionCreate:
    def test_create(self, op_client, seed, app):
        r = op_client.post('/api/inspections', json={
            'title': '新巡检', 'customer_id': seed['c'], 'overall_status': '正常',
            'inspection_date': '2026-08-01', 'conclusion': '一切正常'})
        assert r.status_code == 200
        with app.app_context():
            i = Inspection.query.filter_by(title='新巡检').first()
            assert i is not None
            assert i.customer_id == seed['c']
            assert i.conclusion == '一切正常'
            # 未传巡检人员时冻结当前用户快照
            assert i.inspector_name == 'op'

    def test_create_with_inspector(self, op_client, seed, app):
        with app.app_context():
            op_uid = User.query.filter_by(username='op').first().id
        r = op_client.post('/api/inspections', json={
            'title': '指派巡检', 'customer_id': seed['c'], 'inspector_user_id': op_uid})
        assert r.status_code == 200
        with app.app_context():
            i = Inspection.query.filter_by(title='指派巡检').first()
            assert i.inspector_user_id == op_uid
            assert i.inspector_name == 'op'

    def test_create_missing_customer(self, op_client, seed):
        r = op_client.post('/api/inspections', json={'title': '无客户巡检'})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1

    def test_create_empty_title(self, op_client, seed):
        r = op_client.post('/api/inspections', json={'title': '  ', 'customer_id': seed['c']})
        assert r.status_code == 400

    def test_create_forbidden_without_permission(self, viewer_client, seed):
        r = viewer_client.post('/api/inspections', json={'title': 'x', 'customer_id': seed['c']})
        assert r.status_code == 403


class TestInspectionUpdate:
    def test_update(self, op_client, seed, app):
        r = op_client.put(f"/api/inspections/{seed['i1']}", json={
            'title': '改名巡检', 'customer_id': seed['c'], 'conclusion': '更新结论'})
        assert r.status_code == 200
        with app.app_context():
            i = Inspection.query.get(seed['i1'])
            assert i.title == '改名巡检'
            assert i.conclusion == '更新结论'

    def test_update_forbidden(self, viewer_client, seed):
        r = viewer_client.put(f"/api/inspections/{seed['i1']}", json={'title': 'x'})
        assert r.status_code == 403


class TestInspectionReviewFlow:
    def test_submit_to_review(self, op_client, seed, app):
        r = op_client.post(f"/api/inspections/{seed['i1']}/submit")
        assert r.status_code == 200
        with app.app_context():
            i = Inspection.query.get(seed['i1'])
            assert i.review_status == '待审核'

    def test_review_approve(self, op_client, seed, app):
        r = op_client.post(f"/api/inspections/{seed['i2']}/review", json={
            'approved': True, 'remark': '审核通过'})
        assert r.status_code == 200
        with app.app_context():
            i = Inspection.query.get(seed['i2'])
            assert i.review_status == '已通过'
            assert i.overall_status == '正常'
            assert i.review_comment == '审核通过'

    def test_review_reject(self, op_client, seed, app):
        r = op_client.post(f"/api/inspections/{seed['i2']}/review", json={
            'approved': False, 'remark': '资料不全，退回'})
        assert r.status_code == 200
        with app.app_context():
            i = Inspection.query.get(seed['i2'])
            assert i.review_status == '已退回'
            assert i.overall_status == '异常'
            assert i.review_comment == '资料不全，退回'

    def test_review_forbidden_without_permission(self, viewer_client, seed):
        r = viewer_client.post(f"/api/inspections/{seed['i2']}/review", json={'approved': True})
        assert r.status_code == 403


class TestInspectionDelete:
    def test_delete_by_admin(self, admin_client, seed, app):
        r = admin_client.delete(f"/api/inspections/{seed['i1']}")
        assert r.status_code == 200
        with app.app_context():
            assert Inspection.query.get(seed['i1']) is None

    def test_operator_forbidden(self, op_client, seed):
        assert op_client.delete(f"/api/inspections/{seed['i1']}").status_code == 403

    def test_requires_login(self, client, seed):
        assert client.delete(f"/api/inspections/{seed['i1']}").status_code == 401


class TestInspectionDicts:
    def test_dicts(self, op_client, app):
        with app.app_context():
            from models import Inspector
            op_uid = User.query.filter_by(username='op').first().id
            if not Inspector.query.filter_by(user_id=op_uid).first():
                db.session.add(Inspector(user_id=op_uid, is_active=True))
            c = Customer(name='字典客户')
            db.session.add(c)
            db.session.commit()
        r = op_client.get('/api/dicts/inspections')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert any(c['name'] == '字典客户' for c in data['customers'])
        assert any(p['user_id'] == op_uid and p['name'] == 'op' for p in data['inspectors'])
        assert data['overall_statuses'] == ['正常', '警告', '异常']
        assert '草稿' in data['review_statuses']
        assert '待审核' in data['review_statuses']

    def test_list_requires_login(self, client):
        assert client.get('/api/inspections').status_code == 401
