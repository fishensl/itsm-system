# -*- coding: utf-8 -*-
"""W3-R7 form_commit 封装路由回归：成功/失败路径的消息与重定向"""
import pytest

from models import db, SparePart, SpareStock, Opportunity, Customer


class TestSalesRoutes:
    def test_opportunity_add_success(self, sales_client, app):
        with app.app_context():
            db.session.add(Customer(name='销售客户'))
            db.session.commit()
            cid = Customer.query.filter_by(name='销售客户').first().id
        r = sales_client.post('/opportunities/add', data={
            'title': '百万集采项目', 'customer_id': cid, 'stage': '初步接触'})
        assert r.status_code == 302
        with app.app_context():
            assert Opportunity.query.filter_by(title='百万集采项目').first() is not None

    def test_opportunity_add_invalid_shows_error(self, sales_client, app):
        """空标题 → ServiceError → rollback + flash danger，不入库"""
        r = sales_client.post('/opportunities/add', data={'title': '  '},
                              follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            assert Opportunity.query.count() == 0

    def test_contract_edit_generates_tasks(self, sales_client, app):
        """合同已配置巡检频率+模板时，编辑保存触发 after 钩子自动生成任务（幂等）。

        注：合同表单本身不含巡检配置字段（create/update_contract 均不持久化它们），
        配置经 DB 直接写入——与原行为一致，这里验证 after 钩子接线正确。
        """
        with app.app_context():
            from models import Contract, InspectionTemplate
            db.session.add(Customer(name='合同客户'))
            tpl = InspectionTemplate(name='季巡模板', is_active=True)
            db.session.add(tpl)
            db.session.flush()
            from datetime import date as _date
            ct = Contract(title='年度维保合同', number='HT-001',
                          customer_id=Customer.query.filter_by(name='合同客户').first().id,
                          status='执行中', inspection_frequency='每季度',
                          inspection_template_id=tpl.id, auto_generate_tasks=True,
                          start_date=_date(2026, 1, 1), end_date=_date(2026, 12, 31))
            db.session.add(ct)
            db.session.commit()
            ctid = ct.id
        r = sales_client.post(f'/contracts/edit/{ctid}', data={'title': '年度维保合同V2'})
        assert r.status_code == 302
        with app.app_context():
            from models import InspectionTask
            tasks = InspectionTask.query.filter_by(source='合同自动生成').all()
            assert len(tasks) >= 1


class TestSpareRoutes:
    def test_stock_add_negative_rejected(self, op_client, app):
        with app.app_context():
            p = SparePart(name='硬盘', code='HD-01')
            db.session.add(p)
            db.session.commit()
            pid = p.id
        op_client.post('/spare-stocks/add', data={
            'spare_part_id': pid, 'quantity': -5, 'location': 'A'})
        with app.app_context():
            assert SpareStock.query.count() == 0

    def test_stock_add_ok(self, op_client, app):
        with app.app_context():
            p = SparePart(name='内存条', code='RAM-01')
            db.session.add(p)
            db.session.commit()
            pid = p.id
        op_client.post('/spare-stocks/add', data={
            'spare_part_id': pid, 'quantity': 8, 'location': 'A', 'unit_price': 200})
        with app.app_context():
            assert SpareStock.query.filter_by(spare_part_id=pid).first().quantity == 8

    def test_spare_part_add_with_duplicate_name_fails(self, op_client, app):
        with app.app_context():
            db.session.add(SparePart(name='电源', code='PS-01'))
            db.session.commit()
        r = op_client.post('/spare-parts/add', data={'name': '电源', 'code': 'PS-02'},
                           follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            assert SparePart.query.filter_by(name='电源').count() == 1
