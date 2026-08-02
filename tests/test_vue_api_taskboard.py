# -*- coding: utf-8 -*-
"""P2 任务看板 Vue API：分组看板 / 状态流转 / 权限"""
import pytest
from datetime import date, timedelta

from models import db, Customer, InspectionTask, User


@pytest.fixture()
def seed(app):
    with app.app_context():
        c = Customer(name='看板客户')
        db.session.add(c)
        db.session.flush()
        op = User.query.filter_by(username='op').first()
        t1 = InspectionTask(title='季度巡检A', customer_id=c.id, status='待执行',
                            planned_start=date.today() - timedelta(days=10),
                            planned_end=date.today() - timedelta(days=5),  # 逾期
                            task_type='计划', priority='中')
        t2 = InspectionTask(title='应急巡检B', customer_id=c.id, status='执行中',
                            planned_start=date.today(), planned_end=date.today() + timedelta(days=2),
                            task_type='突发', assigned_to_user_id=op.id)
        t3 = InspectionTask(title='月度巡检C', customer_id=c.id, status='已完成',
                            task_type='计划')
        t4 = InspectionTask(title='已取消任务', customer_id=c.id, status='已取消',
                            task_type='计划')
        db.session.add_all([t1, t2, t3, t4])
        db.session.commit()
        yield {'c': c.id, 't1': t1.id, 't2': t2.id}


class TestTaskBoard:
    def test_groups_shape(self, op_client, seed):
        r = op_client.get('/api/task-board')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['pending'] == 1
        assert data['running'] == 1
        assert data['done'] == 1
        assert data['total'] == 3  # 默认不含已取消
        # 逾期标记
        pending = data['groups']['待执行']
        assert pending[0]['overdue'] is True

    def test_show_cancelled(self, op_client, seed):
        r = op_client.get('/api/task-board', query_string={'show_cancelled': '1'})
        assert r.get_json()['data']['total'] == 4

    def test_filter_customer(self, op_client, seed):
        r = op_client.get('/api/task-board', query_string={'customer_id': seed['c']})
        assert r.get_json()['data']['total'] == 3

    def test_filter_assignee(self, op_client, seed, app):
        with app.app_context():
            op = User.query.filter_by(username='op').first()
        r = op_client.get('/api/task-board', query_string={'assignee_id': op.id})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['groups']['执行中'][0]['assigned_to_name'] == 'op'

    def test_requires_permission(self, viewer_client):
        """viewer 无 task:schedule"""
        assert viewer_client.get('/api/task-board').status_code == 403

    def test_dicts(self, op_client, seed):
        r = op_client.get('/api/dicts/task-board')
        body = r.get_json()
        assert body['code'] == 0
        assert len(body['data']['customers']) >= 1


class TestTaskStatusFlow:
    def test_advance_status(self, op_client, seed, app):
        r = op_client.post(f"/api/task-board/{seed['t1']}/status", json={'status': '执行中'})
        assert r.status_code == 200
        r = op_client.post(f"/api/task-board/{seed['t1']}/status", json={'status': '已完成'})
        assert r.status_code == 200
        with app.app_context():
            t = InspectionTask.query.get(seed['t1'])
            assert t.status == '已完成'
            assert t.actual_end is not None

    def test_illegal_status(self, op_client, seed):
        r = op_client.post(f"/api/task-board/{seed['t1']}/status", json={'status': '不存在'})
        assert r.status_code == 400

    def test_cancel(self, op_client, seed, app):
        r = op_client.post(f"/api/task-board/{seed['t1']}/status", json={'status': '已取消'})
        assert r.status_code == 200
        with app.app_context():
            assert InspectionTask.query.get(seed['t1']).status == '已取消'
