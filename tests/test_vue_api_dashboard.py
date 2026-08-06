# -*- coding: utf-8 -*-
"""V23 工作台待办：巡检任务按角色自动匹配（与任务看板同规则，已并入我的待办）"""
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


def _mk_customer(app, name='待办客户'):
    with app.app_context():
        c = Customer(name=name)
        db.session.add(c)
        db.session.commit()
        return c.id


class TestDashboardTaskScope:
    def test_admin_sees_all_pending(self, admin_client, app):
        """admin（有派发权）：待办含全部待执行任务（含未指派/他人），不含已完成"""
        cid = _mk_customer(app)
        with app.app_context():
            op = User.query.filter_by(username='op').first()
        _mk_task(app, '未指派任务', cid, status='待执行')
        _mk_task(app, '已完成任务', cid, status='已完成')
        _mk_task(app, '他人任务', cid, status='执行中', assigned_to_user_id=op.id)
        r = admin_client.get('/api/dashboard/overview')
        titles = [t['title'] for t in r.get_json()['data']['my_tasks']]
        assert '未指派任务' in titles
        assert '他人任务' in titles
        assert '已完成任务' not in titles

    def test_engineer_sees_only_own(self, app):
        cid = _mk_customer(app)
        c, uid = _mk_engineer(app)
        with app.app_context():
            op_id = User.query.filter_by(username='op').first().id
        _mk_task(app, '自己的任务', cid, status='待执行', assigned_to_user_id=uid)
        _mk_task(app, '别人的任务', cid, status='待执行', assigned_to_user_id=op_id)
        _mk_task(app, '未指派任务', cid, status='待执行')
        r = c.get('/api/dashboard/overview')
        titles = [t['title'] for t in r.get_json()['data']['my_tasks']]
        assert '自己的任务' in titles
        assert '别人的任务' not in titles
        assert '未指派任务' not in titles

    def test_supervisor_sees_dept(self, app):
        """部门主管（无派发权）：本部门任务 + 未指派可见，外部门不可见"""
        with app.app_context():
            dept = Department(name='运维一部')
            db.session.add(dept)
            db.session.flush()
            sup = User.create_with_password(
                username='sup', password='test123456', realname='主管',
                role='operator', department_id=dept.id)
            member = User.create_with_password(
                username='mem', password='test123456', realname='组员',
                role='operator', department_id=dept.id)
            db.session.add_all([sup, member])
            db.session.flush()
            dept.head_id = sup.id
            db.session.add(UserPermission(user_id=sup.id, permission_code='task:dispatch',
                                          grant_type='deny'))
            db.session.commit()
            member_id = member.id
            op_id = User.query.filter_by(username='op').first().id
        cid = _mk_customer(app)
        _mk_task(app, '部门任务', cid, status='待执行', assigned_to_user_id=member_id)
        _mk_task(app, '未指派', cid, status='待执行')
        _mk_task(app, '外部门任务', cid, status='待执行', assigned_to_user_id=op_id)
        c = app.test_client()
        c.post('/login', data={'username': 'sup', 'password': 'test123456'})
        titles = [t['title'] for t in
                  c.get('/api/dashboard/overview').get_json()['data']['my_tasks']]
        assert '部门任务' in titles
        assert '未指派' in titles
        assert '外部门任务' not in titles

    def test_merged_with_ticket_and_fault(self, admin_client, app):
        """合并列表：工单/故障与巡检任务同列表展示"""
        cid = _mk_customer(app)
        with app.app_context():
            from models import Ticket, Fault
            db.session.add(Ticket(number='WO-TEST-001', title='待办工单', customer_id=cid,
                                  assigned_to='admin', status='待处理', priority='中'))
            db.session.add(Fault(title='待办故障', customer_id=cid, result='处理中'))
            db.session.commit()
        _mk_task(app, '巡检任务', cid, status='待执行')
        r = admin_client.get('/api/dashboard/overview')
        tasks = r.get_json()['data']['my_tasks']
        types = {t['type_label'] for t in tasks}
        assert {'工单', '故障', '巡检'} <= types
        titles = {t['title'] for t in tasks}
        assert {'待办工单', '待办故障', '巡检任务'} <= titles
