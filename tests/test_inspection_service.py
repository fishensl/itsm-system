# -*- coding: utf-8 -*-
"""巡检审核流：提交→审核通过（触发报告生成）/退回"""
from datetime import date

import pytest

from models import db, Customer, Inspection
from services import inspection_service


@pytest.fixture()
def ctx(app):
    with app.app_context():
        yield


@pytest.fixture()
def inspection(ctx):
    c = Customer(name='巡检客户')
    db.session.add(c)
    db.session.flush()
    i = Inspection(title='Q2 机房巡检', customer_id=c.id,
                   inspection_date=date.today(), overall_status='', review_status='')
    db.session.add(i)
    db.session.commit()
    return i.id


class TestReviewFlow:
    def test_submit_for_review(self, ctx, inspection):
        inspection_service.submit_for_review(inspection, 'op')
        i = Inspection.query.get(inspection)
        assert i.review_status == '待审核'

    def test_approve_triggers_report_generation(self, ctx, inspection, monkeypatch):
        calls = []

        def _fake_report(insp):
            calls.append(insp.id)
            insp.report_file = '巡检报告_fake.docx'

        monkeypatch.setattr(inspection_service, '_generate_report_for_inspection', _fake_report)
        inspection_service.submit_for_review(inspection, 'op')
        inspection_service.review_inspection(inspection, True, 'admin', remark='同意')
        i = Inspection.query.get(inspection)
        assert i.review_status == '已通过'
        assert calls == [inspection]

    def test_reject_does_not_generate_report(self, ctx, inspection, monkeypatch):
        calls = []
        monkeypatch.setattr(inspection_service, '_generate_report_for_inspection',
                            lambda insp: calls.append(insp.id))
        inspection_service.submit_for_review(inspection, 'op')
        inspection_service.review_inspection(inspection, False, 'admin', remark='数据不全')
        i = Inspection.query.get(inspection)
        assert i.review_status == '已退回'
        assert calls == []

    def test_report_failure_does_not_block_approval(self, ctx, inspection, monkeypatch):
        """报告生成异常不阻塞审核通过（服务内 try/except 兜底）"""
        def _boom(insp):
            raise RuntimeError('docx 生成失败')

        monkeypatch.setattr(inspection_service, '_generate_report_for_inspection', _boom)
        inspection_service.submit_for_review(inspection, 'op')
        inspection_service.review_inspection(inspection, True, 'admin')
        assert Inspection.query.get(inspection).review_status == '已通过'
