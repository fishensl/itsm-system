# -*- coding: utf-8 -*-
"""P2 工单 Vue API：列表/详情/创建(自接单)/状态机动作/版本化提交审核/删除"""
import io

import pytest

from models import db, Customer, Ticket, TicketLog, SubmissionVersion


@pytest.fixture()
def seed(app):
    with app.app_context():
        c = Customer(name='工单API客户')
        db.session.add(c)
        db.session.flush()
        t = Ticket(number='WO-TEST-001', title='测试工单', customer_id=c.id,
                   priority='高', status='待派单', created_by='admin')
        db.session.add(t)
        db.session.commit()
        yield {'c': c.id, 't': t.id}


class TestTicketList:
    def test_list_shape(self, op_client, seed):
        r = op_client.get('/api/tickets')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['total'] == 1
        assert data['items'][0]['customer_name'] == '工单API客户'
        assert data['items'][0]['status'] == '待派单'

    def test_filter_status(self, op_client, seed):
        r = op_client.get('/api/tickets', query_string={'status': '处理中'})
        assert r.get_json()['data']['total'] == 0
        r = op_client.get('/api/tickets', query_string={'status': '待派单'})
        assert r.get_json()['data']['total'] == 1

    def test_search(self, op_client, seed):
        r = op_client.get('/api/tickets', query_string={'search': 'WO-TEST'})
        assert r.get_json()['data']['total'] == 1


class TestTicketDetailAndLogs:
    def test_detail_includes_logs(self, op_client, seed):
        r = op_client.get(f"/api/tickets/{seed['t']}")
        body = r.get_json()
        assert body['code'] == 0
        assert body['data']['title'] == '测试工单'
        assert isinstance(body['data']['logs'], list)


class TestTicketStateMachine:
    def test_full_flow(self, op_client, seed, app):
        """派单→接单→提交→审核通过→验收通过→关闭"""
        steps = [
            ('assign', {'action': 'assign', 'assignee': 'op'}),
            ('accept', {'action': 'accept'}),
            ('submit', {'action': 'submit', 'diagnosis': '光模块故障', 'solution': '更换'}),
            ('audit', {'action': 'audit', 'approved': True}),
            ('accept_check', {'action': 'accept_check', 'approved': True}),
        ]
        for _, payload in steps:
            r = op_client.post(f"/api/tickets/{seed['t']}/action", json=payload)
            assert r.status_code == 200, f'{payload} -> {r.get_json()}'
        with app.app_context():
            assert Ticket.query.get(seed['t']).status == '已关闭'
            # 5 次状态流转日志（fixture 直插无"创建"日志）
            assert TicketLog.query.filter_by(ticket_id=seed['t']).count() >= 5

    def test_illegal_transition_rejected(self, op_client, seed):
        """待派单直接提交审核 → 400"""
        r = op_client.post(f"/api/tickets/{seed['t']}/action", json={'action': 'submit'})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1

    def test_unknown_action_rejected(self, op_client, seed):
        r = op_client.post(f"/api/tickets/{seed['t']}/action", json={'action': 'boom'})
        assert r.status_code == 400

    def test_audit_reject_returns_processing(self, op_client, seed, app):
        for payload in ({'action': 'assign', 'assignee': 'op'}, {'action': 'accept'},
                        {'action': 'submit'}, {'action': 'audit', 'approved': False}):
            assert op_client.post(f"/api/tickets/{seed['t']}/action", json=payload).status_code == 200
        with app.app_context():
            assert Ticket.query.get(seed['t']).status == '处理中'


class TestTicketCreate:
    def test_create_default_pending(self, op_client, seed, app):
        r = op_client.post('/api/tickets', json={
            'title': '新工单', 'customer_id': seed['c'], 'priority': '中'})
        assert r.status_code == 200
        with app.app_context():
            t = Ticket.query.filter_by(title='新工单').first()
            assert t.status == '待派单'

    def test_create_self_accept(self, op_client, seed, app):
        r = op_client.post('/api/tickets', json={
            'title': '自接工单', 'customer_id': seed['c'],
            'dispatch_mode': 'self_accept'})
        assert r.status_code == 200
        with app.app_context():
            t = Ticket.query.filter_by(title='自接工单').first()
            assert t.status == '处理中'
            assert t.assigned_to == 'op'

    def test_create_empty_title(self, op_client, seed):
        r = op_client.post('/api/tickets', json={'title': '  '})
        assert r.status_code == 400


class TestTicketDelete:
    def test_delete_by_admin(self, admin_client, seed, app):
        r = admin_client.delete(f"/api/tickets/{seed['t']}")
        assert r.status_code == 200
        with app.app_context():
            assert Ticket.query.get(seed['t']) is None
            assert TicketLog.query.filter_by(ticket_id=seed['t']).count() == 0

    def test_operator_forbidden(self, op_client, seed):
        assert op_client.delete(f"/api/tickets/{seed['t']}").status_code == 403


class TestTicketDicts:
    def test_dicts(self, op_client):
        r = op_client.get('/api/dicts/tickets')
        body = r.get_json()
        assert body['code'] == 0
        assert '待派单' in body['data']['statuses']
        assert '紧急' in body['data']['priorities']

    def test_customers_include_region_id(self, op_client, app):
        """客户字典携带 region_id，供驻场工程师按负责区域过滤/预选"""
        with app.app_context():
            from models import Region
            r = Region(name='字典市'); db.session.add(r); db.session.flush()
            c = Customer(name='区域客户', region_id=r.id)
            db.session.add(c); db.session.commit()
            rid = r.id
        data = op_client.get('/api/dicts/tickets').get_json()['data']
        row = next(x for x in data['customers'] if x['name'] == '区域客户')
        assert row['region_id'] == rid
        # faults / inspections 字典同构
        for url in ('/api/dicts/faults', '/api/dicts/inspections'):
            data = op_client.get(url).get_json()['data']
            row = next(x for x in data['customers'] if x['name'] == '区域客户')
            assert row['region_id'] == rid


class TestTicketVersionedSubmit:
    """V21 工单闭环：提交(带处理报告文件) → 建版本 → 审核意见挂版本 → 退回重提版本递增"""

    def _to_processing(self, client, tid):
        for payload in ({'action': 'assign', 'assignee': 'op'}, {'action': 'accept'}):
            r = client.post(f'/api/tickets/{tid}/action', json=payload)
            assert r.status_code == 200

    def test_submit_with_report_creates_version(self, op_client, seed, app):
        self._to_processing(op_client, seed['t'])
        r = op_client.post(f"/api/tickets/{seed['t']}/action", data={
            'action': 'submit', 'diagnosis': '光模块故障', 'solution': '更换光模块',
            'note': '客户要求工作时段外上门，已协调',
            'report_file': (io.BytesIO(b'fake report'), 'handle.docx'),
        }, content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            t = Ticket.query.get(seed['t'])
            assert t.status == '待审核'
            assert t.report_file.startswith('uploads/ticket_reports/')
            v = SubmissionVersion.query.filter_by(entity_type='ticket', entity_id=t.id).first()
            assert v is not None
            assert v.version_no == 1
            assert v.review_status == '待审核'
            assert '光模块故障' in (v.content_json or '')
            assert '工作时段外' in (v.content_json or '')  # 提交备注随版本留档

    def test_audit_comment_written_to_version_and_reject_resubmit(self, op_client, seed, app):
        """退回修改（意见+修改要求挂版本）→ 重新提交（版本递增），每轮意见留档"""
        self._to_processing(op_client, seed['t'])
        r = op_client.post(f"/api/tickets/{seed['t']}/action", json={
            'action': 'submit', 'diagnosis': 'd1', 'solution': 's1'})
        assert r.status_code == 200
        r = op_client.post(f"/api/tickets/{seed['t']}/action", json={
            'action': 'audit', 'approved': False, 'remark': '缺少变更记录',
            'requirements': '请补充变更窗口与回退方案后重新提交'})
        assert r.status_code == 200
        with app.app_context():
            t = Ticket.query.get(seed['t'])
            assert t.status == '处理中'
            assert t.audit_status == '拒绝'
            assert t.audit_comment == '缺少变更记录'
        # 重新提交 v2
        r = op_client.post(f"/api/tickets/{seed['t']}/action", data={
            'action': 'submit', 'diagnosis': 'd2', 'solution': 's2',
            'report_file': (io.BytesIO(b'v2'), 'v2.docx'),
        }, content_type='multipart/form-data')
        assert r.status_code == 200
        with app.app_context():
            t = Ticket.query.get(seed['t'])
            versions = SubmissionVersion.query.filter_by(entity_type='ticket', entity_id=t.id) \
                .order_by(SubmissionVersion.version_no.asc()).all()
            assert [v.version_no for v in versions] == [1, 2]
            assert versions[0].review_status == '已退回'
            assert versions[0].review_comment == '缺少变更记录'
            assert versions[0].revision_requirements == '请补充变更窗口与回退方案后重新提交'
            assert versions[1].review_status == '待审核'
        # 版本列表 API 含审核人/意见/修改要求
        r = op_client.get(f"/api/tickets/{seed['t']}/versions")
        body = r.get_json()['data']
        assert len(body) == 2
        assert body[0]['review_status'] == '已退回'
        assert body[0]['review_comment'] == '缺少变更记录'
        assert body[0]['revision_requirements'] == '请补充变更窗口与回退方案后重新提交'
        assert body[0]['submitted_by_name'] == 'op'
        assert body[1]['version_no'] == 2
        # 报告可读名：客户+工单标题+处理报告+序号；v1 未传报告文件（无扩展名），v2 有
        assert body[0]['report_name'] == '工单API客户测试工单处理报告01'
        assert body[1]['report_name'] == '工单API客户测试工单处理报告02.docx'

    def test_submit_requires_processing(self, op_client, seed):
        """待派单直接提交审核 → 400"""
        r = op_client.post(f"/api/tickets/{seed['t']}/action", json={'action': 'submit'})
        assert r.status_code == 400

    def test_payload_has_audit_fields(self, op_client, seed):
        """V21: payload 下发审核意见/报告/完整性字段（前端可见退回原因）"""
        self._to_processing(op_client, seed['t'])
        op_client.post(f"/api/tickets/{seed['t']}/action", json={
            'action': 'submit', 'diagnosis': 'd', 'solution': 's'})
        op_client.post(f"/api/tickets/{seed['t']}/action", json={
            'action': 'audit', 'approved': False, 'remark': '证据不足'})
        r = op_client.get(f"/api/tickets/{seed['t']}")
        data = r.get_json()['data']
        assert data['audit_status'] == '拒绝'
        assert data['audit_comment'] == '证据不足'
        assert data['audit_by'] == 'op'
        assert 'complete' in data
        assert data['complete'] is False
        assert '处理报告' in data['missing_fields']

    def test_versions_require_view_permission(self, viewer_client, seed):
        r = viewer_client.get(f"/api/tickets/{seed['t']}/versions")
        assert r.status_code == 200  # viewer 有 ticket:view

    def test_audit_requires_review_permission(self, op_client, viewer_client, seed, app):
        """ticket:review 权限：viewer 无 → 403（先由 op 把工单推到待审核）"""
        self._to_processing(op_client, seed['t'])
        assert op_client.post(f"/api/tickets/{seed['t']}/action", json={
            'action': 'submit', 'diagnosis': 'd', 'solution': 's'}).status_code == 200
        r = viewer_client.post(f"/api/tickets/{seed['t']}/action", json={'action': 'audit', 'approved': True})
        assert r.status_code == 403

    def test_report_download(self, op_client, seed, app):
        self._to_processing(op_client, seed['t'])
        r = op_client.post(f"/api/tickets/{seed['t']}/action", data={
            'action': 'submit', 'report_file': (io.BytesIO(b'real'), 'r.docx'),
        }, content_type='multipart/form-data')
        assert r.status_code == 200
        with app.app_context():
            v = SubmissionVersion.query.filter_by(entity_type='ticket').first()
            vid = v.id
        r = op_client.get(f'/api/tickets/report/{vid}')
        assert r.status_code == 200
        assert r.data == b'real'


class TestTicketExport:
    """V21: 工单按客户+时间段导出 Excel / 报告包 zip"""

    def test_export_excel_with_filters(self, admin_client, seed):
        r = admin_client.get('/tickets/export',
                             query_string={'customer_id': seed['c'],
                                           'date_from': '2026-01-01', 'date_to': '2026-12-31'})
        assert r.status_code == 200
        assert r.content_type.startswith('application/vnd.openxmlformats-officedocument.spreadsheetml')
        assert '.xlsx' in r.headers.get('Content-Disposition', '')

    def test_reports_zip_contains_excel_and_report(self, admin_client, seed, app):
        import os
        import zipfile
        with app.app_context():
            t = Ticket.query.get(seed['t'])
            t.status = '处理中'
            t.assigned_to = 'op'
            t.report_file = 'uploads/ticket_reports/1/r.docx'
            os.makedirs(os.path.join('static', 'uploads', 'ticket_reports', '1'), exist_ok=True)
            with open(os.path.join('static', 'uploads', 'ticket_reports', '1', 'r.docx'), 'wb') as fh:
                fh.write(b'zip-report')
            v = SubmissionVersion(entity_type='ticket', entity_id=t.id, version_no=1,
                                  report_file='uploads/ticket_reports/1/r.docx')
            db.session.add(v)
            db.session.commit()
        r = admin_client.get('/tickets/reports-zip', query_string={'customer_id': seed['c']})
        assert r.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(r.data))
        names = zf.namelist()
        assert any(n.endswith('记录明细.xlsx') for n in names)
        assert any('r.docx' in n for n in names)

    def test_reports_zip_empty_redirects(self, admin_client, seed):
        r = admin_client.get('/tickets/reports-zip', query_string={'date_to': '2020-01-01'})
        assert r.status_code == 302

    def test_date_filter_no_match(self, admin_client, seed):
        r = admin_client.get('/tickets/export', query_string={'date_to': '2020-01-01'})
        assert r.status_code == 200  # 空结果也导出（仅表头）
