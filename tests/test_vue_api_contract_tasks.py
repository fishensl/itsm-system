# -*- coding: utf-8 -*-
"""Vue API：合同巡检配置（列表/生成/预览/已生成任务）"""
from datetime import date, timedelta

from models import db, Customer, Contract, InspectionTask, InspectionTaskTemplate


def _mk_contract(app):
    with app.app_context():
        c = Customer(name='合同客户A')
        db.session.add(c)
        db.session.flush()
        tt = InspectionTaskTemplate(name='季度巡检模板', is_active=True)
        db.session.add(tt)
        db.session.flush()
        ct = Contract(title='年度运维合同', customer_id=c.id, inspection_frequency='每季度',
                      auto_generate_tasks=True, status='执行中', task_template_id=tt.id,
                      start_date=date.today() - timedelta(days=120))
        db.session.add(ct)
        db.session.commit()
        return ct.id


class TestContractTasksApi:
    def test_list(self, admin_client, app):
        _mk_contract(app)
        r = admin_client.get('/api/contract-tasks')
        assert r.get_json()['code'] == 0
        d = r.get_json()['data']
        assert len(d['contracts']) == 1
        assert d['contracts'][0]['inspection_frequency'] == '每季度'
        assert len(d['all_contracts']) == 1

    def test_generate_and_generated_tasks(self, admin_client, app):
        cid = _mk_contract(app)
        r = admin_client.post('/api/contract-tasks/generate', json={'contract_id': cid})
        assert r.get_json()['code'] == 0
        assert r.get_json()['data']['count'] > 0
        with app.app_context():
            assert InspectionTask.query.filter_by(contract_id=cid).count() > 0
        r = admin_client.get(f'/api/contract-tasks/generated/{cid}')
        assert r.get_json()['code'] == 0
        assert len(r.get_json()['data']) > 0

    def test_preview_dry_run(self, admin_client, app):
        cid = _mk_contract(app)
        r = admin_client.get(f'/api/contract-tasks/preview/{cid}')
        assert r.get_json()['code'] == 0
        assert r.get_json()['data']['count'] >= 0
        with app.app_context():
            # dry_run 不入库
            assert InspectionTask.query.filter_by(contract_id=cid).count() == 0

    def test_permissions(self, viewer_client, op_client, admin_client):
        assert viewer_client.get('/api/contract-tasks').status_code == 403  # 无 contract_auto:manage
        assert op_client.get('/api/contract-tasks').status_code == 200
        assert admin_client.post('/api/contract-tasks/generate', json={'contract_id': 1}).status_code == 200
