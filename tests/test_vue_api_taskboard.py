# -*- coding: utf-8 -*-
"""P2 任务看板 Vue API：分组看板 / 状态流转 / 权限 / 角色自动匹配"""
import pytest
from datetime import date, timedelta

from models import db, Customer, Department, InspectionTask, User, UserPermission


def _mk_engineer(app, username='eng'):
    """operator 角色 + 用户级拒绝 task:dispatch → 无派发权的普通工程师"""
    with app.app_context():
        u = User.create_with_password(
            username=username, password='test123456', realname=username, role='operator')
        db.session.add(u)
        db.session.flush()
        db.session.add(UserPermission(user_id=u.id, permission_code='task:dispatch',
                                      grant_type='deny'))
        db.session.commit()
        uid = u.id
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'test123456'})
    return c, uid


def _mk_task(app, title, customer_id, **kw):
    with app.app_context():
        t = InspectionTask(title=title, task_type='计划', customer_id=customer_id, **kw)
        db.session.add(t)
        db.session.commit()
        return t.id


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


class TestTaskBoardRoleScope:
    """V22 角色自动匹配：无派发权工程师只见自己 / 主管见部门 / 派发权见全部"""

    def test_engineer_sees_only_own(self, app, seed):
        with app.app_context():
            op = User.query.filter_by(username='op').first()
            op_id = op.id
        c, uid = _mk_engineer(app)
        _mk_task(app, '工程师任务', seed['c'], status='待执行', assigned_to_user_id=uid)
        _mk_task(app, '别人任务', seed['c'], status='执行中', assigned_to_user_id=op_id)
        r = c.get('/api/task-board')
        data = r.get_json()['data']
        assert data['scope'] == 'mine'
        titles = [t['title'] for t in data['groups']['待执行']]
        assert titles == ['工程师任务']

    def test_engineer_ignores_assignee_filter(self, app, seed):
        """无派发权工程师无法通过 assignee 筛选看别人的任务"""
        c, uid = _mk_engineer(app)
        _mk_task(app, '工程师任务', seed['c'], status='待执行', assigned_to_user_id=uid)
        with app.app_context():
            op = User.query.filter_by(username='op').first()
        r = c.get('/api/task-board', query_string={'assignee_id': op.id})
        assert r.get_json()['data']['total'] == 0

    def test_supervisor_sees_dept(self, app, seed):
        """部门主管（无派发权）：本部门任务 + 未指派 + 自己派发，看不到外部门"""
        with app.app_context():
            dept = Department(name='一区运维')
            db.session.add(dept)
            db.session.flush()
            sup = User.create_with_password(
                username='sup', password='test123456', realname='主管',
                role='operator', department_id=dept.id)
            member = User.create_with_password(
                username='member', password='test123456', realname='组员',
                role='operator', department_id=dept.id)
            db.session.add_all([sup, member])
            db.session.flush()
            dept.head_id = sup.id
            db.session.add(UserPermission(user_id=sup.id, permission_code='task:dispatch',
                                          grant_type='deny'))
            db.session.commit()
            member_id, sup_id = member.id, sup.id
            op_id = User.query.filter_by(username='op').first().id
        _mk_task(app, '部门任务', seed['c'], status='待执行', assigned_to_user_id=member_id)
        _mk_task(app, '未指派任务', seed['c'], status='待执行')
        _mk_task(app, '自己派发任务', seed['c'], status='待执行', dispatched_by=sup_id)
        _mk_task(app, '外部门任务', seed['c'], status='待执行', assigned_to_user_id=op_id)
        c = app.test_client()
        c.post('/login', data={'username': 'sup', 'password': 'test123456'})
        r = c.get('/api/task-board')
        data = r.get_json()['data']
        assert data['scope'] == 'dept'
        titles = {t['title'] for st in data['groups'].values() for t in st}
        assert {'部门任务', '未指派任务', '自己派发任务'} <= titles
        assert '外部门任务' not in titles
        assert '应急巡检B' not in titles

    def test_dicts_scoped_to_direct_customers(self, app, seed):
        """无派发权工程师的客户下拉 = 直接关联客户（非全量）"""
        with app.app_context():
            c2 = Customer(name='外区客户')
            db.session.add(c2)
            db.session.commit()
            c2_id = c2.id
        c, uid = _mk_engineer(app)
        with app.app_context():
            u = User.query.get(uid)
            u.customers = Customer.query.filter(Customer.id == seed['c']).all()
            db.session.commit()
        r = c.get('/api/dicts/task-board')
        customers = r.get_json()['data']['customers']
        assert [x['id'] for x in customers] == [seed['c']]
        assert c2_id not in [x['id'] for x in customers]


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
