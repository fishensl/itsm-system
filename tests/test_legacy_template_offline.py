# -*- coding: utf-8 -*-
"""旧 InspectionTemplate 下线：写路径 404 + 读路径保留 + 生成器回退兼容"""
import pytest

from models import db, Customer, Contract, InspectionTask, InspectionTemplate
from datetime import date


class TestLegacyTemplateWritePathsGone:
    @pytest.mark.parametrize('url', [
        '/inspection-templates/add',
        '/inspection-templates/edit/1',
        '/inspection-templates/delete/1',
    ])
    def test_write_routes_removed(self, admin_client, url):
        r = admin_client.post(url, data={'name': 'X'})
        assert r.status_code == 404

    def test_read_paths_kept(self, op_client, app):
        """列表页 + API 只读保留（历史任务/巡检表单仍引用）"""
        with app.app_context():
            db.session.add(InspectionTemplate(name='遗留模板', is_active=True))
            db.session.commit()
        assert op_client.get('/inspection-templates').status_code == 200
        r = op_client.get('/api/inspection-templates')
        assert r.status_code == 200
        assert r.get_json()[0]['name'] == '遗留模板'


class TestGeneratorLegacyFallback:
    def test_legacy_contract_still_generates(self, app):
        """未迁移的旧合同（只有 inspection_template_id）仍能生成任务，挂旧 template_id"""
        with app.app_context():
            from utils.auto_task_generator import generate_contract_tasks
            c = Customer(name='回退客户')
            db.session.add(c)
            db.session.flush()
            tpl = InspectionTemplate(name='旧月巡模板', is_active=True)
            db.session.add(tpl)
            db.session.flush()
            ct = Contract(title='旧合同', number='HT-OLD', customer_id=c.id,
                          status='执行中', inspection_frequency='每月',
                          inspection_template_id=tpl.id, auto_generate_tasks=True,
                          start_date=date(2026, 5, 1), end_date=date(2026, 12, 31))
            db.session.add(ct)
            db.session.commit()
            ctid = ct.id
            tplid = tpl.id
            generated = generate_contract_tasks(contract_id=ctid)
            assert len(generated) >= 1
            tasks = InspectionTask.query.filter_by(contract_id=ctid).all()
            assert all(t.template_id == tplid for t in tasks)
            assert all(t.task_template_id is None for t in tasks)

    def test_new_template_preferred_over_legacy(self, app):
        """双字段都有值时优先新任务模板"""
        from models import InspectionTaskTemplate
        from utils.auto_task_generator import generate_contract_tasks
        with app.app_context():
            c = Customer(name='双模板客户')
            db.session.add(c)
            db.session.flush()
            old = InspectionTemplate(name='旧模板', is_active=True)
            db.session.add(old)
            new = InspectionTaskTemplate(name='新任务模板', category='日常', is_active=True)
            db.session.add(new)
            db.session.flush()
            ct = Contract(title='双模板合同', number='HT-BOTH', customer_id=c.id,
                          status='执行中', inspection_frequency='每月',
                          inspection_template_id=old.id, task_template_id=new.id,
                          auto_generate_tasks=True,
                          start_date=date(2026, 5, 1), end_date=date(2026, 12, 31))
            db.session.add(ct)
            db.session.commit()
            ctid, newid = ct.id, new.id
            generate_contract_tasks(contract_id=ctid)
            tasks = InspectionTask.query.filter_by(contract_id=ctid).all()
            assert all(t.task_template_id == newid for t in tasks)
            assert all('新任务模板' in t.title for t in tasks)
