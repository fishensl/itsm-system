# -*- coding: utf-8 -*-
"""P2 巡检 Vue API：列表/筛选/详情/创建/更新/审核流/上传报告版本化/导出/字典/权限"""
import io
import os

import pytest

from models import db, Customer, Inspection, InspectionTask, User, SubmissionVersion, Device


@pytest.fixture()
def seed(app):
    with app.app_context():
        c = Customer(name='巡检API客户')
        db.session.add(c)
        db.session.flush()
        op = User.query.filter_by(username='op').first()
        t1 = InspectionTask(title='核心机房月度巡检任务', customer_id=c.id,
                            status='执行中', assigned_to_user_id=op.id)
        t2 = InspectionTask(title='季度巡检任务', customer_id=c.id,
                            status='待审核', assigned_to_user_id=op.id)
        db.session.add_all([t1, t2])
        db.session.flush()
        i1 = Inspection(title='核心机房月度巡检', customer_id=c.id, task_id=t1.id,
                        overall_status='草稿', review_status='', inspector_name='op',
                        submitted_report='uploads/inspection_reports/1/x.docx')
        i2 = Inspection(title='季度巡检-待审核', customer_id=c.id, task_id=t2.id,
                        overall_status='待审核', review_status='待审核', inspector_name='op',
                        content_json='[{"name": "电源检查"}]',
                        field_values_json='{"机房A": {"电源": "正常"}}',
                        sections_json='{"sections": [{"title": "基础信息"}]}',
                        review_comment='')
        db.session.add_all([i1, i2])
        db.session.commit()
        yield {'c': c.id, 'i1': i1.id, 'i2': i2.id, 't1': t1.id, 't2': t2.id}


def _dummy_file(name='report.docx'):
    return io.BytesIO(b'fake docx content'), name


class TestInspectionList:
    def test_list_shape(self, op_client, seed):
        r = op_client.get('/api/inspections')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['total'] == 2
        item = {i['title']: i for i in data['items']}['核心机房月度巡检']
        assert item['customer_name'] == '巡检API客户'
        assert item['review_status'] == '草稿'
        assert item['task_id'] == seed['t1']
        assert item['task_title'] == '核心机房月度巡检任务'
        assert item['submitted_report'] is True
        assert item['complete'] is False  # 缺正式报告/审核通过
        assert 'missing_fields' in item
        assert 'content_json' not in item  # 列表不带详情 JSON

    def test_filter_search(self, op_client, seed):
        r = op_client.get('/api/inspections', query_string={'search': '季度'})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['title'] == '季度巡检-待审核'

    def test_filter_task(self, op_client, seed):
        r = op_client.get('/api/inspections', query_string={'task_id': seed['t1']})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['title'] == '核心机房月度巡检'

    def test_filter_date_range(self, op_client, seed, app):
        with app.app_context():
            i1 = Inspection.query.get(seed['i1'])
            i1.inspection_date = __import__('datetime').date(2026, 7, 15)
            i2 = Inspection.query.get(seed['i2'])
            i2.inspection_date = __import__('datetime').date(2026, 8, 20)
            db.session.commit()
        r = op_client.get('/api/inspections', query_string={'date_from': '2026-08-01'})
        assert r.get_json()['data']['total'] == 1
        r = op_client.get('/api/inspections', query_string={'date_from': '2026-07-01', 'date_to': '2026-07-31'})
        assert r.get_json()['data']['total'] == 1
        r = op_client.get('/api/inspections', query_string={'date_to': '2026-06-01'})
        assert r.get_json()['data']['total'] == 0

    def test_filter_incomplete_only(self, op_client, seed):
        # 两条都缺正式报告 → 都是不完整
        r = op_client.get('/api/inspections', query_string={'incomplete_only': 1})
        assert r.get_json()['data']['total'] == 2

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
    def test_create_requires_task(self, op_client, seed, app):
        """V21: 巡检记录必须关联任务（任务↔记录 1:1）"""
        r = op_client.post('/api/inspections', json={
            'title': '新巡检', 'customer_id': seed['c'], 'overall_status': '正常',
            'inspection_date': '2026-08-01', 'conclusion': '一切正常'})
        assert r.status_code == 400
        assert '任务' in r.get_json()['message']

    def test_create_with_task(self, op_client, seed, app):
        with app.app_context():
            # 新建一个无记录的任务
            t3 = InspectionTask(title='新任务', customer_id=seed['c'], status='执行中')
            db.session.add(t3)
            db.session.commit()
            tid = t3.id
        r = op_client.post('/api/inspections', json={
            'title': '新巡检', 'task_id': tid, 'overall_status': '正常',
            'inspection_date': '2026-08-01', 'conclusion': '一切正常'})
        assert r.status_code == 200
        with app.app_context():
            i = Inspection.query.filter_by(title='新巡检').first()
            assert i is not None
            assert i.customer_id == seed['c']  # 未传客户时从任务带出
            assert i.task_id == tid
            assert i.conclusion == '一切正常'
            # 未传巡检人员时冻结当前用户快照
            assert i.inspector_name == 'op'

    def test_create_duplicate_task_rejected(self, op_client, seed, app):
        """任务已有记录时拒绝再建（1:1）"""
        r = op_client.post('/api/inspections', json={
            'title': '重复巡检', 'task_id': seed['t1']})
        assert r.status_code == 400
        assert '1:1' in r.get_json()['message']

    def test_create_empty_title(self, op_client, seed):
        r = op_client.post('/api/inspections', json={'title': '  ', 'task_id': seed['t1']})
        assert r.status_code == 400

    def test_create_forbidden_without_permission(self, viewer_client, seed):
        r = viewer_client.post('/api/inspections', json={'title': 'x', 'task_id': seed['t1']})
        assert r.status_code == 403


class TestInspectionUploadReportFlow:
    """V21 核心闭环：任务执行中 → 上传报告建版本 → 任务待审核 → 审核通过任务完成"""

    def test_upload_report_creates_record_and_reviewing(self, op_client, app, seed):
        with app.app_context():
            t3 = InspectionTask(title='上传闭环任务', customer_id=seed['c'], status='执行中',
                                assigned_to_user_id=User.query.filter_by(username='op').first().id)
            db.session.add(t3)
            db.session.commit()
            tid = t3.id
        r = op_client.post(f'/api/inspections/task/{tid}/report',
                           data={'report_file': _dummy_file(),
                                 'conclusion': '现场巡检完成，设备运行正常',
                                 'remark': '客户口头反馈下季度扩容计划'},
                           content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        body = r.get_json()['data']
        assert body['task_status'] == '待审核'
        with app.app_context():
            t = db.session.get(InspectionTask, tid)
            assert t.status == '待审核'
            i = Inspection.query.filter_by(task_id=tid).first()
            assert i is not None
            assert i.review_status == '待审核'
            assert i.submitted_report.startswith('uploads/inspection_reports/')
            v = SubmissionVersion.query.filter_by(entity_type='inspection', entity_id=i.id).first()
            assert v is not None
            assert v.version_no == 1
            assert v.review_status == '待审核'
            assert v.report_file == i.submitted_report
            assert '现场巡检完成' in (v.content_json or '')
            assert '扩容计划' in (v.content_json or '')  # 提交备注随版本留档

    def test_upload_requires_running_task(self, op_client, app, seed):
        with app.app_context():
            t3 = InspectionTask(title='待执行任务', customer_id=seed['c'], status='待执行')
            t4 = InspectionTask(title='已完成任务', customer_id=seed['c'], status='已完成')
            db.session.add_all([t3, t4])
            db.session.commit()
            tid_pending = t3.id
            tid_done = t4.id
        # 待执行任务允许上传（自动开始）
        r = op_client.post(f'/api/inspections/task/{tid_pending}/report',
                           data={'report_file': _dummy_file()},
                           content_type='multipart/form-data')
        assert r.status_code == 200
        # 已完成任务允许补传（生成巡检记录，任务状态保持已完成）
        r = op_client.post(f'/api/inspections/task/{tid_done}/report',
                           data={'report_file': _dummy_file(), 'conclusion': '补传报告'},
                           content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        body = r.get_json()['data']
        assert body['task_status'] == '已完成'  # 补传不改变任务状态
        with app.app_context():
            t4 = db.session.get(InspectionTask, tid_done)
            assert t4.status == '已完成'
            i = Inspection.query.filter_by(task_id=tid_done).first()
            assert i is not None  # 巡检记录已生成
            assert i.review_status == '待审核'
            assert i.submitted_report.startswith('uploads/inspection_reports/')
            v = SubmissionVersion.query.filter_by(entity_type='inspection', entity_id=i.id).first()
            assert v is not None and v.review_status == '待审核'

    def test_upload_redo_after_done_keeps_task_done(self, op_client, app, seed):
        """已完成任务已有已通过记录 → 补传新版本走审核，任务仍保持已完成"""
        from datetime import date as _date
        with app.app_context():
            t5 = InspectionTask(title='已完成补传任务', customer_id=seed['c'], status='已完成')
            db.session.add(t5)
            db.session.flush()
            i = Inspection(title='已完成补传任务', customer_id=seed['c'], task_id=t5.id,
                           inspection_date=_date(2026, 8, 1), inspector_name='测试',
                           overall_status='正常', review_status='已通过',
                           submitted_report='uploads/inspection_reports/old.pdf')
            db.session.add(i)
            db.session.commit()
            tid = t5.id
            iid = i.id
        r = op_client.post(f'/api/inspections/task/{tid}/report',
                           data={'report_file': _dummy_file(), 'conclusion': '补充资料'},
                           content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['data']['task_status'] == '已完成'
        with app.app_context():
            assert db.session.get(InspectionTask, tid).status == '已完成'
            i = Inspection.query.get(iid)
            assert i.review_status == '待审核'  # 新版本重新提交审核
            assert i.submitted_report.startswith('uploads/inspection_reports/')
            # 新版本
            vs = SubmissionVersion.query.filter_by(entity_type='inspection', entity_id=iid)\
                .order_by(SubmissionVersion.version_no.desc()).all()
            assert vs and vs[0].version_no == 1
            assert vs[0].review_status == '待审核'

    def test_upload_rejects_other_engineer(self, op_client, admin_client, app, seed):
        with app.app_context():
            other = User.create_with_password(username='other_eng', password='x',
                                              role='operator', realname='李工')
            db.session.add(other)
            db.session.flush()
            t3 = InspectionTask(title='他人任务', customer_id=seed['c'], status='执行中',
                                assigned_to_user_id=other.id)
            db.session.add(t3)
            db.session.commit()
            tid = t3.id
        # 非指派者上传被拒（op 无 review 权限则 force=False）
        r = op_client.post(f'/api/inspections/task/{tid}/report',
                           data={'report_file': _dummy_file()},
                           content_type='multipart/form-data')
        assert r.status_code == 400
        # 管理员（有 inspection:review）可代传
        r = admin_client.post(f'/api/inspections/task/{tid}/report',
                              data={'report_file': _dummy_file()},
                              content_type='multipart/form-data')
        assert r.status_code == 200

    def test_upload_rejects_bad_file(self, op_client, seed):
        r = op_client.post(f"/api/inspections/task/{seed['t1']}/report",
                           data={'report_file': (io.BytesIO(b'evil'), 'evil.exe')},
                           content_type='multipart/form-data')
        assert r.status_code == 400

    def test_review_approve_completes_task(self, op_client, seed, app):
        """上传 → 待审核 → 审核通过 → 任务已完成 + actual_end"""
        r = op_client.post(f"/api/inspections/task/{seed['t1']}/report",
                           data={'report_file': _dummy_file()},
                           content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            assert db.session.get(InspectionTask, seed['t1']).status == '待审核'
        r = op_client.post(f"/api/inspections/{seed['i1']}/review", json={
            'approved': True, 'remark': '审核通过'})
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            i = Inspection.query.get(seed['i1'])
            assert i.review_status == '已通过'
            assert i.overall_status == '正常'
            t = db.session.get(InspectionTask, seed['t1'])
            assert t.status == '已完成'
            assert t.actual_end is not None

    def test_review_reject_reverts_task(self, op_client, seed, app):
        r = op_client.post(f"/api/inspections/task/{seed['t1']}/report",
                           data={'report_file': _dummy_file()},
                           content_type='multipart/form-data')
        assert r.status_code == 200
        with app.app_context():
            assert db.session.get(InspectionTask, seed['t1']).status == '待审核'
        r = op_client.post(f"/api/inspections/{seed['i1']}/review", json={
            'approved': False, 'remark': '报告缺少照片，退回'})
        assert r.status_code == 200
        with app.app_context():
            i = Inspection.query.get(seed['i1'])
            assert i.review_status == '已退回'
            assert i.overall_status == '异常'
            assert i.review_comment == '报告缺少照片，退回'
            t = db.session.get(InspectionTask, seed['t1'])
            assert t.status == '执行中'

    def test_review_pending_double_submit_rejected(self, op_client, seed, app):
        """任务已有待审核记录时不可重复上传"""
        r = op_client.post(f"/api/inspections/task/{seed['t1']}/report",
                           data={'report_file': _dummy_file()},
                           content_type='multipart/form-data')
        assert r.status_code == 200
        r = op_client.post(f"/api/inspections/task/{seed['t1']}/report",
                           data={'report_file': _dummy_file('again.docx')},
                           content_type='multipart/form-data')
        assert r.status_code == 400
        assert '待审核' in r.get_json()['message']

    def test_versions_after_multi_round(self, op_client, seed, app):
        """退回修改（带修改要求）→ 再上传 → 版本递增，每轮审核意见/修改要求/文件留档"""
        # v1 上传
        r = op_client.post(f"/api/inspections/task/{seed['t1']}/report",
                           data={'report_file': _dummy_file()},
                           content_type='multipart/form-data')
        assert r.status_code == 200
        # 退回修改 v1：原因 + 修改要求
        r = op_client.post(f"/api/inspections/{seed['i1']}/review", json={
            'approved': False, 'remark': '报告缺照片', 'requirements': '请补充每台设备的现场照片并重新上传'})
        assert r.status_code == 200
        # v2 重传
        r = op_client.post(f"/api/inspections/task/{seed['t1']}/report",
                           data={'report_file': _dummy_file('second.docx'), 'conclusion': '补充后重传'},
                           content_type='multipart/form-data')
        assert r.status_code == 200
        with app.app_context():
            i = Inspection.query.get(seed['i1'])
            assert i.review_status == '待审核'
            versions = SubmissionVersion.query.filter_by(entity_type='inspection', entity_id=i.id) \
                .order_by(SubmissionVersion.version_no.asc()).all()
            assert [v.version_no for v in versions] == [1, 2]
            assert versions[0].review_status == '已退回'
            assert versions[0].review_comment == '报告缺照片'
            assert versions[0].revision_requirements == '请补充每台设备的现场照片并重新上传'
            assert versions[1].review_status == '待审核'
        # 版本列表 API 含修改要求
        r = op_client.get(f"/api/inspections/{seed['i1']}/versions")
        body = r.get_json()['data']
        assert len(body) == 2
        assert body[0]['version_no'] == 1
        assert body[0]['review_status'] == '已退回'
        assert body[0]['review_comment'] == '报告缺照片'
        assert body[0]['revision_requirements'] == '请补充每台设备的现场照片并重新上传'
        assert body[1]['version_no'] == 2
        assert body[1]['reviewed_by_name'] == ''  # 未审核

    def test_report_download_and_traversal_guard(self, op_client, app, seed):
        with app.app_context():
            # 造一个真实文件 + 一个不存在的版本
            static_dir = os.path.join('static', 'uploads', 'inspection_reports', 'test')
            os.makedirs(static_dir, exist_ok=True)
            real = os.path.join(static_dir, 'ok.docx')
            with open(real, 'wb') as fh:
                fh.write(b'content')
            i = Inspection.query.get(seed['i1'])
            v = SubmissionVersion(entity_type='inspection', entity_id=i.id, version_no=1,
                                  report_file='uploads/inspection_reports/test/ok.docx')
            db.session.add(v)
            db.session.commit()
            vid = v.id
        r = op_client.get(f'/api/inspections/report/{vid}')
        assert r.status_code == 200
        assert r.data == b'content'
        # 下载文件名为可读拼接名（客户+任务+报告01），UTF-8 filename*（URL 编码，解码断言）
        from urllib.parse import unquote
        cd = r.headers.get('Content-Disposition', '')
        assert "filename*=UTF-8''" in cd
        assert '巡检API客户核心机房月度巡检任务报告01.docx' in unquote(cd)
        # 路径穿越：report_file 含 ../ 的版本 → 404
        with app.app_context():
            bad = SubmissionVersion(entity_type='inspection', entity_id=seed['i1'], version_no=99,
                                    report_file='uploads/../../config.py')
            db.session.add(bad)
            db.session.commit()
            bad_id = bad.id
        r = op_client.get(f'/api/inspections/report/{bad_id}')
        assert r.status_code == 404 or r.get_json()['code'] == 1

    def test_report_display_name_rules(self, op_client, seed, app):
        """报告可读名：任务标题+报告+两位序号；客户前缀去重；审核通过定稿去序号"""
        # 任务标题不含客户名 → 拼客户前缀；v1 带序号 01
        r = op_client.post(f"/api/inspections/task/{seed['t1']}/report",
                           data={'report_file': _dummy_file()},
                           content_type='multipart/form-data')
        assert r.status_code == 200
        r = op_client.get(f"/api/inspections/{seed['i1']}/versions")
        body = r.get_json()['data']
        assert body[0]['report_name'] == '巡检API客户核心机房月度巡检任务报告01.docx'
        # inspection payload submitted_report_name 同步（最新版本名）
        r = op_client.get(f"/api/inspections/{seed['i1']}")
        detail = r.get_json()['data']
        assert detail['submitted_report_name'] == '巡检API客户核心机房月度巡检任务报告01.docx'
        # 审核通过（定稿）→ 去序号
        r = op_client.post(f"/api/inspections/{seed['i1']}/review", json={
            'approved': True, 'remark': '通过'})
        assert r.status_code == 200
        r = op_client.get(f"/api/inspections/{seed['i1']}/versions")
        body = r.get_json()['data']
        assert body[0]['review_status'] == '已通过'
        assert body[0]['report_name'] == '巡检API客户核心机房月度巡检任务报告.docx'
        # 定稿后补传第 2 轮 → 02（仍带序号，未定稿）
        r = op_client.post(f"/api/inspections/task/{seed['t1']}/report",
                           data={'report_file': _dummy_file('second.docx')},
                           content_type='multipart/form-data')
        assert r.status_code == 200
        r = op_client.get(f"/api/inspections/{seed['i1']}/versions")
        body = r.get_json()['data']
        assert [v['version_no'] for v in body] == [1, 2]
        assert body[1]['report_name'] == '巡检API客户核心机房月度巡检任务报告02.docx'

    def test_report_display_name_dedup_customer_prefix(self, op_client, app):
        """任务标题已含客户名 → 不重复拼接客户前缀"""
        from models import Customer as _C
        with app.app_context():
            c = _C(name='定稿客户')
            db.session.add(c)
            db.session.flush()
            t = InspectionTask(title='定稿客户2026年第3季度巡检', customer_id=c.id,
                               status='执行中', assigned_to_user_id=User.query.filter_by(username='op').first().id)
            db.session.add(t)
            db.session.commit()
            tid = t.id
        r = op_client.post(f'/api/inspections/task/{tid}/report',
                           data={'report_file': _dummy_file()},
                           content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            i = Inspection.query.filter_by(task_id=tid).first()
            iid = i.id
        r = op_client.get(f'/api/inspections/{iid}/versions')
        body = r.get_json()['data']
        assert body[0]['report_name'] == '定稿客户2026年第3季度巡检报告01.docx'

    def test_upload_requires_login(self, client, seed):
        r = client.post(f"/api/inspections/task/{seed['t1']}/report",
                        data={'report_file': _dummy_file()},
                        content_type='multipart/form-data')
        assert r.status_code == 401


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
            assert db.session.get(InspectionTask, seed['t1']).status == '待审核'

    def test_submit_requires_report(self, op_client, seed, app):
        """无现场报告且无检查项内容的记录不可提交审核"""
        with app.app_context():
            t3 = InspectionTask(title='空记录任务', customer_id=seed['c'], status='执行中')
            db.session.add(t3)
            db.session.flush()
            i3 = Inspection(title='空记录', customer_id=seed['c'], task_id=t3.id,
                            review_status='', overall_status='草稿')
            db.session.add(i3)
            db.session.commit()
            iid = i3.id
        r = op_client.post(f'/api/inspections/{iid}/submit')
        assert r.status_code == 400
        assert '报告' in r.get_json()['message']

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
            assert SubmissionVersion.query.filter_by(entity_type='inspection',
                                                     entity_id=seed['i1']).count() == 0

    def test_operator_forbidden(self, op_client, seed):
        assert op_client.delete(f"/api/inspections/{seed['i1']}").status_code == 403

    def test_requires_login(self, client, seed):
        assert client.delete(f"/api/inspections/{seed['i1']}").status_code == 401


class TestInspectionSSR:
    """V21: SSR 任务详情上传报告端点（双轨）"""

    def test_ssr_upload_report(self, op_client, app, seed):
        with app.app_context():
            t3 = InspectionTask(title='SSR上传任务', customer_id=seed['c'], status='执行中',
                                assigned_to_user_id=User.query.filter_by(username='op').first().id)
            db.session.add(t3)
            db.session.commit()
            tid = t3.id
        r = op_client.post(f'/task-schedule/{tid}/upload-report',
                           data={'report_file': _dummy_file(), 'conclusion': 'SSR端上传'},
                           content_type='multipart/form-data')
        assert r.status_code == 302  # 成功重定向回详情页
        with app.app_context():
            t = db.session.get(InspectionTask, tid)
            assert t.status == '待审核'
            i = Inspection.query.filter_by(task_id=tid).first()
            assert i is not None
            assert i.review_status == '待审核'
            assert i.submitted_report.startswith('uploads/inspection_reports/')

    def test_ssr_upload_requires_file(self, op_client, seed):
        r = op_client.post(f"/task-schedule/{seed['t1']}/upload-report", data={},
                           content_type='multipart/form-data')
        assert r.status_code == 302  # 无文件 → flash 重定向

    def test_ssr_upload_bad_file(self, op_client, seed):
        r = op_client.post(f"/task-schedule/{seed['t1']}/upload-report",
                           data={'report_file': (io.BytesIO(b'evil'), 'evil.exe')},
                           content_type='multipart/form-data')
        assert r.status_code == 302


class TestInspectionDicts:
    def test_dicts(self, op_client, app):
        with app.app_context():
            from models import Inspector
            op_uid = User.query.filter_by(username='op').first().id
            if not Inspector.query.filter_by(user_id=op_uid).first():
                db.session.add(Inspector(user_id=op_uid, is_active=True))
            c = Customer(name='字典客户')
            db.session.add(c)
            db.session.flush()
            t = InspectionTask(title='字典任务', customer_id=c.id)
            db.session.add(t)
            db.session.commit()
            tid = t.id
        r = op_client.get('/api/dicts/inspections')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert any(c['name'] == '字典客户' for c in data['customers'])
        assert any(p['user_id'] == op_uid and p['name'] == 'op' for p in data['inspectors'])
        assert any(t['id'] == tid for t in data['tasks'])
        assert data['overall_statuses'] == ['正常', '警告', '异常']
        assert '草稿' in data['review_statuses']
        assert '待审核' in data['review_statuses']

    def test_list_requires_login(self, client):
        assert client.get('/api/inspections').status_code == 401


def _xlsx_bytes(rows):
    """构造 xlsx 内存字节（rows: 首行为表头）"""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


class TestTaskSubmissionAssets:
    """V22: 任务提交全套资料（配置备份/拓扑图/资产清单）→ 同步设备管理"""

    def _task(self, app, seed, tpl=None):
        with app.app_context():
            op = User.query.filter_by(username='op').first()
            t = InspectionTask(title='全套资料任务', customer_id=seed['c'], status='执行中',
                               assigned_to_user_id=op.id, task_template_id=tpl.id if tpl else None)
            db.session.add(t)
            db.session.flush()
            d = Device(customer_id=seed['c'], device_name='核心交换机A', device_type='核心交换机',
                       ip_address='10.0.0.1')
            db.session.add(d)
            db.session.commit()
            return t.id, d.id

    def test_full_submission_syncs_all(self, op_client, app, seed):
        """报告+配置zip+文本配置+拓扑+资产清单 → 版本 assets + DeviceConfigBackup + Topology + 设备导入"""
        from models import InspectionTaskTemplate, Device, DeviceConfigBackup, Topology, SubmissionAsset
        with app.app_context():
            tpl = InspectionTaskTemplate(name='全套模板', required_assets_json='{}')
            db.session.add(tpl)
            db.session.commit()
            tid, did = self._task(app, seed, tpl)
        r = op_client.post(f'/api/inspections/task/{tid}/report',
                           data={
                               'report_file': _dummy_file(),
                               'config_zip': (io.BytesIO(b'zip'), 'full.zip'),
                               'config_zip_device_id': str(did),
                               'config_text_file_0': (io.BytesIO(b'hostname core-a\n'), 'core-a.cfg'),
                               'config_text_device_id_0': str(did),
                               'topology_file': (io.BytesIO(b'png'), 'topo.png'),
                               'asset_list': (_xlsx_bytes([
                                   ['设备名称', '设备类型', 'IP地址'],
                                   ['核心交换机A', '核心交换机', '10.0.0.1'],
                                   ['新服务器B', '服务器', '10.0.0.2'],
                               ]), 'assets.xlsx'),
                           },
                           content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        body = r.get_json()['data']
        assert body['config_backups'] == 2  # zip + 文本配置
        assert body['topologies'] == 1
        assert body['asset_import']['created'] == 1  # 新服务器B
        assert body['asset_import']['updated'] == 1  # 核心交换机A
        with app.app_context():
            i = Inspection.query.filter_by(task_id=tid).first()
            v = SubmissionVersion.query.filter_by(entity_type='inspection', entity_id=i.id).first()
            assets = SubmissionAsset.query.filter_by(version_id=v.id).all()
            types = sorted(a.asset_type for a in assets)
            assert types == ['asset_list', 'config_text', 'config_zip', 'report', 'topology']
            # 同步目标
            assert DeviceConfigBackup.query.filter_by(device_id=did).count() == 2
            cb = DeviceConfigBackup.query.filter_by(device_id=did, backup_type='全部配置').first()
            assert cb is not None and cb.file_path.endswith('full.zip')
            ct = DeviceConfigBackup.query.filter_by(device_id=did, backup_type='运行配置').first()
            assert ct is not None and 'hostname core-a' in ct.config_content
            assert Topology.query.filter_by(customer_id=seed['c']).count() == 1
            # 资产导入
            assert Device.query.filter_by(customer_id=seed['c']).count() == 2
            assert Device.query.filter_by(device_name='新服务器B').first() is not None
        # 版本列表 API 含资料明细
        r = op_client.get(f"/api/inspections/{i.id}/versions")
        vers = r.get_json()['data']
        assert len(vers[0]['assets']) == 5

    def test_required_assets_enforced(self, op_client, app, seed):
        """模板配置 config_zip 必传：缺传拒绝 / 填豁免原因放行"""
        import json
        from models import InspectionTaskTemplate
        with app.app_context():
            tpl = InspectionTaskTemplate(
                name='必传模板',
                required_assets_json=json.dumps(
                    {'report': True, 'config_zip': True, 'config_text': False,
                     'topology': False, 'asset_list': False}, ensure_ascii=False))
            db.session.add(tpl)
            db.session.commit()
            tid, did = self._task(app, seed, tpl)
        # 缺 config_zip → 拒绝
        r = op_client.post(f'/api/inspections/task/{tid}/report',
                           data={'report_file': _dummy_file()},
                           content_type='multipart/form-data')
        assert r.status_code == 400
        assert '完整配置备份包' in r.get_json()['message']
        # 填豁免原因 → 放行
        r = op_client.post(f'/api/inspections/task/{tid}/report',
                           data={'report_file': _dummy_file(),
                                 'config_zip_skip_reason': '客户机房未开放，无法导出完整配置'},
                           content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            i = Inspection.query.filter_by(task_id=tid).first()
            v = SubmissionVersion.query.filter_by(entity_type='inspection', entity_id=i.id).first()
            from models import SubmissionAsset
            skip = SubmissionAsset.query.filter_by(version_id=v.id, asset_type='config_zip').first()
            assert skip.skip_reason == '客户机房未开放，无法导出完整配置'
        # 版本列表 API 可见豁免
        r = op_client.get(f"/api/inspections/{i.id}/versions")
        assets = r.get_json()['data'][0]['assets']
        assert any(a['asset_type'] == 'config_zip' and a['skip_reason'] for a in assets)

    def test_report_skip_reason(self, op_client, app, seed):
        """报告豁免：不传文件但填原因 → 放行"""
        tid, _ = self._task(app, seed)
        r = op_client.post(f'/api/inspections/task/{tid}/report',
                           data={'report_skip_reason': '报告后续线下补交'},
                           content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()

    def test_required_assets_default_when_no_template(self, op_client, app, seed):
        """无模板任务默认仅报告必传：只传报告放行"""
        tid, _ = self._task(app, seed)
        r = op_client.post(f'/api/inspections/task/{tid}/report',
                           data={'report_file': _dummy_file()},
                           content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()

    def test_required_assets_meta_endpoint(self, op_client, app, seed):
        """GET /api/task-schedule/<id>/required-assets 返回配置+客户设备"""
        tid, did = self._task(app, seed)
        r = op_client.get(f'/api/task-schedule/{tid}/required-assets')
        body = r.get_json()['data']
        assert body['required_assets']['report'] is True
        assert any(d['id'] == did for d in body['devices'])


class TestDeviceConfigBackupApi:
    """V22: Vue 设备配置备份（列表/内容/下载）"""

    def test_list_content_download(self, op_client, app, seed):
        from models import Device, DeviceConfigBackup
        with app.app_context():
            d = Device(customer_id=seed['c'], device_name='核心交换机A', device_type='核心交换机')
            db.session.add(d)
            db.session.flush()
            b = DeviceConfigBackup(device_id=d.id, backup_type='运行配置', backup_method='巡检上传',
                                   config_content='hostname core-a', created_by='op / 版本1')
            db.session.add(b)
            db.session.commit()
            did, bid = d.id, b.id
        r = op_client.get(f'/api/devices/{did}/config-backups')
        assert r.status_code == 200
        rows = r.get_json()['data']
        assert len(rows) == 1
        assert rows[0]['backup_method'] == '巡检上传'
        assert rows[0]['has_content'] is True
        r = op_client.get(f'/api/devices/config-backup/{bid}/content')
        assert r.get_json()['data']['content'] == 'hostname core-a'
        # 无附件文件 → 下载 404
        r = op_client.get(f'/api/devices/config-backup/{bid}/download')
        assert r.status_code == 404

    def test_requires_login(self, client, seed):
        assert client.get(f'/api/devices/{seed["c"]}/config-backups').status_code == 401


class TestTaskTemplateRequiredAssets:
    """V22: 任务模板必传配置 API"""

    def test_set_and_read(self, op_client, app):
        r = op_client.post('/api/task-templates', json={
            'name': '必传模板X',
            'required_assets': {'report': True, 'config_zip': True, 'config_text': True,
                                'topology': True, 'asset_list': True},
        })
        assert r.status_code == 200
        tid = r.get_json()['data']['id']
        r = op_client.get('/api/task-templates')
        tpl = next(t for t in r.get_json()['data']['templates'] if t['id'] == tid)
        assert tpl['required_assets']['config_zip'] is True
        # 更新
        r = op_client.put(f'/api/task-templates/{tid}', json={
            'required_assets': {'report': True, 'config_zip': False, 'config_text': False,
                                'topology': False, 'asset_list': False},
        })
        assert r.status_code == 200
        r = op_client.get('/api/task-templates')
        tpl = next(t for t in r.get_json()['data']['templates'] if t['id'] == tid)
        assert tpl['required_assets']['config_zip'] is False


class TestReviewChecklist:
    """V23: 审核检查项清单——勾选留痕 / 退回自动拼装 / 配置 API"""

    def test_default_checklist(self, op_client):
        r = op_client.get('/api/system/inspection-review-checklist')
        assert r.status_code == 200
        items = r.get_json()['data']['items']
        names = [it['name'] for it in items]
        assert '核心设备配置备份' in names
        assert '拓扑图' in names and '机房环境' in names
        assert len(items) == 9

    def test_update_checklist_requires_admin_perm(self, admin_client, op_client, viewer_client):
        # viewer 无 permission:edit → 403
        r = viewer_client.put('/api/system/inspection-review-checklist', json={'items': [{'name': 'x', 'enabled': True}]})
        assert r.status_code == 403
        # 保存后读回
        r = admin_client.put('/api/system/inspection-review-checklist', json={'items': [
            {'name': '链路状态', 'enabled': True}, {'name': '设备除尘', 'enabled': False},
        ]})
        assert r.status_code == 200
        r = op_client.get('/api/system/inspection-review-checklist')
        items = r.get_json()['data']['items']
        assert [it['name'] for it in items] == ['链路状态', '设备除尘']
        assert items[1]['enabled'] is False

    def test_checklist_written_to_version(self, op_client, seed, app):
        """审核提交 checklist → 版本落库 + 版本列表 API 输出 + 退回自动拼装"""
        r = op_client.post(f"/api/inspections/task/{seed['t1']}/report",
                           data={'report_file': _dummy_file()},
                           content_type='multipart/form-data')
        assert r.status_code == 200
        checklist = {'核心设备配置备份': '合格', '拓扑图': '需修改', '资产信息': '合格',
                     '链路状态及信息': '合格', '路由信息': '不适用', '现场图片': '需修改',
                     '设备除尘': '合格', '机房环境': '合格', '会议测试': '合格'}
        # 退回且不填 requirements → 由需修改项自动拼装
        r = op_client.post(f"/api/inspections/{seed['i1']}/review", json={
            'approved': False, 'remark': '两项不合格', 'checklist': checklist})
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            v = SubmissionVersion.query.filter_by(entity_type='inspection',
                                                  entity_id=seed['i1']).first()
            assert '拓扑图' in (v.review_checklist_json or '')
            assert '需修改' in (v.review_checklist_json or '')
        r = op_client.get(f"/api/inspections/{seed['i1']}/versions")
        data = r.get_json()['data']
        assert data[-1]['checklist']['拓扑图'] == '需修改'
        assert '请完善：拓扑图、现场图片' in data[-1]['revision_requirements']

    def test_preview_content_types(self, admin_client, app, seed):
        """预览数据流：受控下载端点 Content-Type 按扩展名"""
        import os
        from models import SubmissionAsset, SubmissionVersion as _SV
        with app.app_context():
            i = Inspection.query.get(seed['i1'])
            v = _SV(entity_type='inspection', entity_id=i.id, version_no=99,
                    report_file='uploads/inspection_reports/1/r.pdf')
            db.session.add(v)
            db.session.flush()
            os.makedirs(os.path.join('static', 'uploads', 'inspection_reports', '1'), exist_ok=True)
            with open(os.path.join('static', 'uploads', 'inspection_reports', '1', 'r.pdf'), 'wb') as fh:
                fh.write(b'%PDF-1.4 fake')
            a = SubmissionAsset(version_id=v.id, asset_type='report',
                                file_path='uploads/inspection_reports/1/r.pdf',
                                file_name='r.pdf')
            db.session.add(a)
            db.session.commit()
            aid = a.id
        r = admin_client.get(f'/api/inspections/assets/{aid}/download')
        assert r.status_code == 200
        assert 'pdf' in r.content_type.lower()
        assert r.data == b'%PDF-1.4 fake'


class TestInspectionExport:
    """V21: 按客户+时间段导出 Excel / 报告包 zip"""

    def test_export_excel_with_filters(self, admin_client, seed):
        r = admin_client.get('/inspections/export',
                             query_string={'customer_id': seed['c'],
                                           'date_from': '2026-01-01', 'date_to': '2026-12-31'})
        assert r.status_code == 200
        assert r.content_type.startswith('application/vnd.openxmlformats-officedocument.spreadsheetml')
        assert '.xlsx' in r.headers.get('Content-Disposition', '')

    def test_export_excel_no_match(self, admin_client, seed):
        r = admin_client.get('/inspections/export', query_string={'date_to': '2020-01-01'})
        assert r.status_code == 200  # 空结果也导出（仅表头）

    def test_reports_zip(self, admin_client, seed, app):
        """报告包 zip 含记录明细 Excel + 版本报告文件"""
        import zipfile
        with app.app_context():
            from models import SubmissionVersion as _SV
            os.makedirs(os.path.join('static', 'uploads', 'inspection_reports', 'zipcase'), exist_ok=True)
            with open(os.path.join('static', 'uploads', 'inspection_reports', 'zipcase', 'a.docx'), 'wb') as fh:
                fh.write(b'zip-report')
            i = Inspection.query.get(seed['i1'])
            v = _SV(entity_type='inspection', entity_id=i.id, version_no=1,
                    report_file='uploads/inspection_reports/zipcase/a.docx')
            db.session.add(v)
            db.session.commit()
        r = admin_client.get('/inspections/reports-zip', query_string={'customer_id': seed['c']})
        assert r.status_code == 200
        assert r.content_type == 'application/zip' or 'zip' in r.content_type
        zf = zipfile.ZipFile(io.BytesIO(r.data))
        names = zf.namelist()
        assert any(n.endswith('记录明细.xlsx') for n in names)
        assert any('a.docx' in n for n in names)

    def test_reports_zip_empty(self, admin_client, seed):
        r = admin_client.get('/inspections/reports-zip', query_string={'date_to': '2020-01-01'})
        assert r.status_code == 302  # 空结果重定向回列表

    def test_export_requires_login(self, client):
        assert client.get('/inspections/export').status_code == 302  # SSR 未登录重定向登录页
