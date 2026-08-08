# -*- coding: utf-8 -*-
"""S6 数据隔离：apply_scope_filter 接入工单/巡检列表后，非 admin 用户数据范围收窄"""
from models import db, User, Customer, Ticket, Inspection, Department


def _make_dept_user(app, username, realname, scope='department'):
    with app.app_context():
        dept = Department(name=f'{username}部门')
        db.session.add(dept)
        db.session.flush()
        u = User.create_with_password(username=username, password='x',
                                      role='operator', realname=realname,
                                      department_id=dept.id)
        u.scope = scope
        db.session.add(u)
        db.session.commit()
        return u.id, dept.id


def _login_user(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'x'})
    return c


class TestScopeFilter:
    def test_ticket_scope_department(self, app):
        """部门用户只见本部门创建/处理的工单"""
        uid, dept_id = _make_dept_user(app, 'scope_op1', '范围工程师')
        with app.app_context():
            from services.ticket_service import create_ticket
            c1 = Customer(name='范围客户')
            db.session.add(c1)
            db.session.flush()
            # 本部门创建（created_by=范围工程师）
            t_dept = create_ticket({'title': '本部门工单', 'customer_id': c1.id}, '范围工程师')
            # 他人创建
            t_other = create_ticket({'title': '他人工单', 'customer_id': c1.id}, '别人')
            db.session.commit()
        client = _login_user(app, 'scope_op1')
        r = client.get('/api/tickets')
        d = r.get_json()['data']
        titles = [i['title'] for i in d['items']]
        assert '本部门工单' in titles
        assert '他人工单' not in titles  # 隔离生效

    def test_admin_sees_all(self, app, admin_client):
        """admin 短路：可见全部"""
        with app.app_context():
            from services.ticket_service import create_ticket
            c1 = Customer(name='范围客户2')
            db.session.add(c1)
            db.session.flush()
            create_ticket({'title': '管理员可见', 'customer_id': c1.id}, '任何人')
            db.session.commit()
        r = admin_client.get('/api/tickets')
        titles = [i['title'] for i in r.get_json()['data']['items']]
        assert '管理员可见' in titles
