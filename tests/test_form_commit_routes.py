# -*- coding: utf-8 -*-
"""W3-R7 写操作路由回归（SSR form_commit 路由已剥离 → Vue API /api/* 等价契约）"""

from models import db, SparePart, SpareStock, Opportunity, Customer, InspectionTaskTemplate
from services import sales_service


class TestSalesRoutes:
    def test_opportunity_add_success(self, sales_client, app):
        with app.app_context():
            db.session.add(Customer(name='销售客户'))
            db.session.commit()
            cid = Customer.query.filter_by(name='销售客户').first().id
        r = sales_client.post('/api/opportunities', json={
            'title': '百万集采项目', 'customer_id': cid, 'stage': '初步接触'})
        assert r.status_code == 200
        assert r.get_json()['code'] == 0
        with app.app_context():
            assert Opportunity.query.filter_by(title='百万集采项目').first() is not None

    def test_opportunity_add_invalid_rejected(self, sales_client, app):
        """空标题 → ServiceError → 400，不入库"""
        r = sales_client.post('/api/opportunities', json={'title': '  '})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1
        with app.app_context():
            assert Opportunity.query.count() == 0

    def test_contract_edit_generates_tasks(self, sales_client, app):
        """合同已配置巡检频率+新任务模板时，编辑保存触发 after 钩子自动生成任务（幂等）。"""
        with app.app_context():
            from models import Contract, InspectionTaskTemplate
            db.session.add(Customer(name='合同客户'))
            tpl = InspectionTaskTemplate(name='季巡任务模板', category='季度', is_active=True)
            db.session.add(tpl)
            db.session.flush()
            from datetime import date as _date
            ct = Contract(title='年度维保合同', number='HT-001',
                          customer_id=Customer.query.filter_by(name='合同客户').first().id,
                          status='执行中', inspection_frequency='每季度',
                          task_template_id=tpl.id, auto_generate_tasks=True,
                          start_date=_date(2026, 1, 1), end_date=_date(2026, 12, 31))
            db.session.add(ct)
            db.session.commit()
            ctid = ct.id
        r = sales_client.put(f'/api/contracts/{ctid}',
                             json={'title': '年度维保合同V2', 'auto_generate_tasks': True})
        assert r.status_code == 200
        assert r.get_json()['data']['generated'] >= 1
        with app.app_context():
            from models import InspectionTask, InspectionTaskTemplate
            tid = InspectionTaskTemplate.query.filter_by(name='季巡任务模板').first().id
            tasks = InspectionTask.query.filter_by(source='合同自动生成').all()
            assert len(tasks) >= 1
            # 新链路：生成的任务挂 task_template_id
            assert all(t.task_template_id == tid for t in tasks)


    def test_contract_add_with_inspection_config_generates_tasks(self, sales_client, app):
        """端到端：合同新增时配置巡检频率+新任务模板 → 字段持久化 + after 钩子自动生成任务"""
        with app.app_context():
            from models import InspectionTaskTemplate
            db.session.add(Customer(name='配置客户'))
            tpl = InspectionTaskTemplate(name='月巡任务模板', category='日常', is_active=True)
            db.session.add(tpl)
            db.session.commit()
            cid = Customer.query.filter_by(name='配置客户').first().id
            tid = tpl.id
        r = sales_client.post('/api/contracts', json={
            'title': '含巡检合同', 'customer_id': cid, 'status': '执行中',
            'start_date': '2026-01-01', 'end_date': '2026-12-31',
            'inspection_frequency': '每月', 'task_template_id': str(tid),
            'auto_generate_tasks': True,
        })
        assert r.status_code == 200
        assert r.get_json()['data']['generated'] >= 1
        with app.app_context():
            from models import Contract, InspectionTask
            ct = Contract.query.filter_by(title='含巡检合同').first()
            assert ct.inspection_frequency == '每月'
            assert ct.task_template_id == tid
            assert ct.auto_generate_tasks is True
            tasks = InspectionTask.query.filter_by(contract_id=ct.id, source='合同自动生成').all()
            assert len(tasks) >= 1

    def test_contract_create_update_persist_inspection_fields(self, app):
        """service 层：create/update 均持久化巡检配置三字段"""
        with app.app_context():
            # 建真实模板：PG 强制外键（SQLite 不强制可容忍悬空 task_template_id=3）
            tpl = InspectionTaskTemplate(name='巡检模板', is_active=True)
            db.session.add(tpl)
            db.session.flush()
            tpl_id = tpl.id
            c = sales_service.create_contract({
                'title': 'X', 'inspection_frequency': '每季度',
                'task_template_id': str(tpl_id), 'auto_generate_tasks': 'on'}, 'admin')
            assert c.inspection_frequency == '每季度'
            assert c.task_template_id == tpl_id
            assert c.auto_generate_tasks is True
            # 局部更新（无 inspection_config_present 标记）：checkbox 状态保持不变
            sales_service.update_contract(c.id, {'inspection_frequency': ''})
            assert c.inspection_frequency == ''
            assert c.auto_generate_tasks is True
            # 表单提交（带标记）：未勾选的 checkbox 正确重置为 False
            sales_service.update_contract(c.id, {'inspection_config_present': '1'})
            assert c.auto_generate_tasks is False


class TestSpareRoutes:
    def test_stock_add_negative_rejected(self, op_client, app):
        with app.app_context():
            p = SparePart(name='硬盘', code='HD-01')
            db.session.add(p)
            db.session.commit()
            pid = p.id
        r = op_client.post('/api/spare-stocks', json={
            'spare_part_id': pid, 'quantity': -5, 'location': 'A'})
        assert r.status_code == 400
        with app.app_context():
            assert SpareStock.query.count() == 0

    def test_stock_add_ok(self, op_client, app):
        with app.app_context():
            p = SparePart(name='内存条', code='RAM-01')
            db.session.add(p)
            db.session.commit()
            pid = p.id
        r = op_client.post('/api/spare-stocks', json={
            'spare_part_id': pid, 'quantity': 8, 'location': 'A', 'unit_price': 200})
        assert r.status_code == 200
        with app.app_context():
            assert SpareStock.query.filter_by(spare_part_id=pid).first().quantity == 8

    def test_spare_part_add_with_duplicate_name_fails(self, op_client, app):
        with app.app_context():
            db.session.add(SparePart(name='电源', code='PS-01'))
            db.session.commit()
        r = op_client.post('/api/spare-parts', json={'name': '电源', 'code': 'PS-02'})
        assert r.status_code == 400
        with app.app_context():
            assert SparePart.query.filter_by(name='电源').count() == 1
