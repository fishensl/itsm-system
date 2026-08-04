# -*- coding: utf-8 -*-
"""Vue API：任务安排（看板/KPI/单任务/批量/导入导出）"""
from datetime import date, timedelta

from models import db, Customer, InspectionTask, Inspector, User


def _seed(app):
    with app.app_context():
        c = Customer(name='看板客户')
        db.session.add(c)
        db.session.flush()
        op = User.create_with_password(username='tsuser', password='x', role='operator', realname='张工')
        db.session.add(op)
        db.session.flush()
        db.session.add(Inspector(user_id=op.id, is_active=True))
        db.session.add(InspectionTask(title='2026年二季度巡检', customer_id=c.id, status='待执行',
                                      assigned_to_user_id=op.id,
                                      planned_start=date.today() - timedelta(days=10),
                                      planned_end=date.today() - timedelta(days=1)))
        db.session.add(InspectionTask(title='2026年三季度巡检', customer_id=c.id, status='执行中',
                                      assigned_to_user_id=op.id,
                                      planned_start=date.today(), planned_end=date.today() + timedelta(days=30)))
        db.session.commit()
        return c.id, op.id


class TestTaskScheduleApi:
    def test_board_default_quarter(self, admin_client, app):
        _, op_id = _seed(app)
        r = admin_client.get('/api/task-schedule')
        assert r.get_json()['code'] == 0
        d = r.get_json()['data']
        # 默认工程师视角
        assert d['view'] == 'engineer'
        assert d['kpi']['total'] == 2
        assert len(d['engineer_groups'][str(op_id)]) == 2
        assert d['kpi']['overdue'] == 1
        assert len(d['engineers']) == 1

    def test_status_view(self, admin_client, app):
        _seed(app)
        r = admin_client.get('/api/task-schedule?view=status')
        d = r.get_json()['data']
        assert d['view'] == 'status'
        assert d['status_groups']['待执行'] and d['status_groups']['执行中']

    def test_board_sort_order(self, admin_client, app):
        """看板排序：逾期最前 → 执行中 → 待执行 → 已完成（同级按截止时间升序）"""
        cid, op_id = _seed(app)
        with app.app_context():
            t_overdue_running = InspectionTask(
                title='逾期执行中', customer_id=cid, status='执行中',
                assigned_to_user_id=op_id,
                planned_start=date.today() - timedelta(days=8),
                planned_end=date.today() - timedelta(days=1))
            t_done = InspectionTask(
                title='已完成', customer_id=cid, status='已完成',
                assigned_to_user_id=op_id,
                planned_start=date.today(), planned_end=date.today() + timedelta(days=5))
            t_pending_future = InspectionTask(
                title='未来待执行', customer_id=cid, status='待执行',
                assigned_to_user_id=op_id,
                planned_start=date.today() + timedelta(days=3),
                planned_end=date.today() + timedelta(days=10))
            db.session.add_all([t_overdue_running, t_done, t_pending_future])
            db.session.commit()
        r = admin_client.get('/api/task-schedule')
        d = r.get_json()['data']
        titles = [t['title'] for t in d['tasks']]
        # 逾期执行中 → 逾期待执行（seed 任务1） → 执行中（seed 任务2） → 未来待执行 → 已完成
        assert titles == ['逾期执行中', '2026年二季度巡检', '2026年三季度巡检',
                          '未来待执行', '已完成']
        # 工程师视角组内顺序一致
        r = admin_client.get('/api/task-schedule?view=engineer')
        d = r.get_json()['data']
        assert [t['title'] for t in d['engineer_groups'][str(op_id)]] == titles

    def test_engineer_view(self, admin_client, app):
        _, op_id = _seed(app)
        r = admin_client.get('/api/task-schedule?view=engineer')
        d = r.get_json()['data']
        assert d['view'] == 'engineer'
        assert len(d['engineer_groups'][str(op_id)]) == 2

    def test_quick_add_update_delete(self, admin_client, app):
        cid, op_id = _seed(app)
        r = admin_client.post('/api/task-schedule', json={
            'title': '新增任务X', 'customer_id': cid, 'assignee_id': op_id,
            'planned_start': '2026-08-01', 'planned_end': '2026-08-31', 'priority': '高',
            'estimated_effort': 1.5, 'task_type': '计划',
        })
        assert r.get_json()['code'] == 0
        tid = r.get_json()['data']['id']
        r = admin_client.put(f'/api/task-schedule/{tid}', json={'status': '已完成', 'actual_effort': 1})
        assert r.get_json()['code'] == 0
        with app.app_context():
            t = db.session.get(InspectionTask, tid)
            assert t.status == '已完成'
            assert t.actual_effort == 1
            assert t.actual_end is not None
        r = admin_client.delete(f'/api/task-schedule/{tid}')
        assert r.get_json()['code'] == 0
        with app.app_context():
            assert db.session.get(InspectionTask, tid) is None

    def test_quick_add_requires_title_customer(self, admin_client, app):
        r = admin_client.post('/api/task-schedule', json={'title': '', 'customer_id': 1})
        assert r.status_code == 400
        r = admin_client.post('/api/task-schedule', json={'title': 'x'})
        assert r.status_code == 400

    def test_batch_actions(self, admin_client, app):
        cid, op_id = _seed(app)
        with app.app_context():
            t1 = InspectionTask(title='批量1', customer_id=cid, status='待执行')
            t2 = InspectionTask(title='批量2', customer_id=cid, status='待执行')
            db.session.add_all([t1, t2])
            db.session.commit()
            ids = [t1.id, t2.id]
        r = admin_client.post('/api/task-schedule/batch', json={'ids': ids, 'action': 'assign', 'value': op_id})
        assert r.get_json()['code'] == 0
        r = admin_client.post('/api/task-schedule/batch', json={'ids': ids, 'action': 'status', 'value': '执行中'})
        assert r.get_json()['code'] == 0
        with app.app_context():
            tasks = InspectionTask.query.filter(InspectionTask.id.in_(ids)).all()
            assert all(t.status == '执行中' and t.assigned_to_user_id == op_id for t in tasks)
        r = admin_client.post('/api/task-schedule/batch', json={'ids': ids, 'action': 'delete'})
        assert r.get_json()['code'] == 0
        with app.app_context():
            assert InspectionTask.query.filter(InspectionTask.id.in_(ids)).count() == 0

    def test_import_template_and_import(self, admin_client, app):
        cid, op_id = _seed(app)
        with app.app_context():
            op = db.session.get(User, op_id)
            op_realname = op.realname
        r = admin_client.get('/api/task-schedule/import-template')
        assert r.get_json()['code'] == 0
        assert r.get_json()['data']['filename'].endswith('.xlsx')
        # 构造导入 xlsx
        import io
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(['客户名称', '任务描述', '优先级', '开始日期', '完成日期', '完成状态', '负责人', '完成时间', '预估工作量', '实际工作量'])
        ws.append(['看板客户', '导入任务A', '中', '2026-08-01', '2026-08-31', '已完成', op_realname, '', '1', '0.5'])
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        r = admin_client.post('/api/task-schedule/import', data={
            'importFile': (bio, 'import.xlsx'),
        }, content_type='multipart/form-data')
        assert r.get_json()['code'] == 0
        assert '新增 1' in r.get_json()['data']['message']
        with app.app_context():
            assert InspectionTask.query.filter_by(title='导入任务A').count() == 1

    def test_import_missing_required_column(self, admin_client, app):
        import io
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(['任务描述'])
        ws.append(['x'])
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        r = admin_client.post('/api/task-schedule/import', data={
            'importFile': (bio, 'bad.xlsx'),
        }, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_permissions(self, viewer_client, op_client):
        assert viewer_client.get('/api/task-schedule').status_code == 403  # 无 task:schedule
        assert op_client.get('/api/task-schedule').status_code == 200
        assert viewer_client.post('/api/task-schedule', json={}).status_code == 403
