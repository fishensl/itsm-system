# -*- coding: utf-8 -*-
"""W0-S3/S6 读 API 权限补齐 + API JSON 错误响应验证"""


class TestRackApiPermissions:
    def test_anonymous_401_json(self, client):
        r = client.get('/api/rack/cabinets')
        assert r.status_code == 401
        assert r.is_json

    def test_viewer_allowed(self, viewer_client):
        """viewer 有 device:view → 可读机柜 API"""
        assert viewer_client.get('/api/rack/cabinets').status_code == 200

    def test_sales_forbidden_403_json(self, sales_client):
        """sales 无 device:view → 403 JSON"""
        r = sales_client.get('/api/rack/cabinets')
        assert r.status_code == 403
        assert r.is_json
        assert r.get_json()['required'] == 'device:view'

    def test_devices_all_permission(self, sales_client, viewer_client):
        assert sales_client.get('/api/rack/devices/all').status_code == 403
        assert viewer_client.get('/api/rack/devices/all').status_code == 200


class TestOtherReadApis:
    def test_dept_tree_viewer_allowed(self, viewer_client):
        assert viewer_client.get('/departments/api/tree').status_code == 200

    def test_contract_tasks_api(self, viewer_client, sales_client):
        """viewer 无 contract_auto:manage → 403；sales 有 → 200"""
        assert viewer_client.get('/contract-tasks/api/contracts/1/generated-tasks').status_code == 403
        assert sales_client.get('/contract-tasks/api/contracts/1/generated-tasks').status_code == 200

    def test_customer_apis_require_permission(self, client):
        assert client.get('/api/customers/parent-candidates').status_code == 401
        assert client.get('/api/regions/children/1').status_code == 401


class TestKnowledgeViewCount:
    def test_view_count_atomic_and_dedup(self, app, op_client, viewer_client):
        """原子自增 + 同 session 去重：op 连看两次只 +1，换个用户再 +1"""
        with app.app_context():
            from models import db, KnowledgeBase
            kb = KnowledgeBase(title='交换机故障处理', category='故障案例',
                               content='...', is_published=True, view_count=0)
            db.session.add(kb)
            db.session.commit()
            kb_id = kb.id

        assert op_client.get(f'/knowledge-base/{kb_id}').status_code == 200
        assert op_client.get(f'/knowledge-base/{kb_id}').status_code == 200
        with app.app_context():
            from models import KnowledgeBase
            assert KnowledgeBase.query.get(kb_id).view_count == 1

        assert viewer_client.get(f'/knowledge-base/{kb_id}').status_code == 200
        with app.app_context():
            from models import KnowledgeBase
            assert KnowledgeBase.query.get(kb_id).view_count == 2
