# -*- coding: utf-8 -*-
"""功能3：新建巡检按任务模板快速创建——devices-with-templates 端点 + 表单模板选择器"""
import json

import pytest

from models import (db, Customer, Device, InspectionDeviceTemplate,
                    InspectionTaskTemplate, task_device_template_link)


@pytest.fixture()
def seed(app):
    with app.app_context():
        c = Customer(name='巡检模板客户')
        db.session.add(c)
        db.session.flush()
        d1 = Device(customer_id=c.id, device_name='SW-01', device_type='交换机',
                    ip_address='10.0.0.1', is_in_use=True)
        d2 = Device(customer_id=c.id, device_name='FW-01', device_type='防火墙',
                    is_in_use=True)
        d3 = Device(customer_id=c.id, device_name='SVR-01', device_type='服务器',
                    is_in_use=True)
        db.session.add_all([d1, d2, d3])
        sw_tpl = InspectionDeviceTemplate(
            name='交换机检查模板', device_category='交换机', is_active=True,
            items_json=json.dumps([
                {'name': '端口状态', 'sub_items': [
                    {'label': '状态', 'field_type': 'status_note'}]},
                {'name': 'VLAN配置', 'sub_items': [
                    {'label': '结果', 'field_type': 'dropdown', 'options': '正常,异常'}]},
            ], ensure_ascii=False))
        fw_tpl = InspectionDeviceTemplate(
            name='防火墙检查模板', device_category='防火墙', is_active=True,
            items_json=json.dumps([
                {'name': '会话数', 'sub_items': [{'label': '数值', 'field_type': 'number'}]},
            ], ensure_ascii=False))
        db.session.add_all([sw_tpl, fw_tpl])
        db.session.flush()
        tt = InspectionTaskTemplate(name='安全设备季巡', category='季度', is_active=True)
        db.session.add(tt)
        db.session.flush()
        db.session.execute(task_device_template_link.insert().values(
            task_template_id=tt.id, device_template_id=fw_tpl.id, sort_order=1))
        db.session.commit()
        yield {'customer_id': c.id, 'task_template_id': tt.id}


class TestDevicesWithTemplatesApi:
    def test_auto_match_by_device_type(self, op_client, seed):
        r = op_client.get(f'/api/customers/{seed["customer_id"]}/devices-with-templates')
        assert r.status_code == 200
        body = r.get_json()
        assert body['task_template'] is None
        by_name = {d['device_name']: d for d in body['devices']}
        assert by_name['SW-01']['match_type'] == 'device_type'
        assert by_name['SW-01']['matched_template_name'] == '交换机检查模板'
        assert len(by_name['SW-01']['items']) == 2  # 标准化检查项直接下发
        assert by_name['SW-01']['items'][0]['sub_items'][0]['label'] == '状态'
        assert by_name['FW-01']['items'][0]['name'] == '会话数'
        # 服务器无同类别模板 → none
        assert by_name['SVR-01']['match_type'] == 'none'
        assert by_name['SVR-01']['items'] == []

    def test_task_template_drives_items(self, op_client, seed):
        """选任务模板：关联设备模板驱动检查项（match_type=task_template）"""
        r = op_client.get(f'/api/customers/{seed["customer_id"]}/devices-with-templates'
                          f'?task_template_id={seed["task_template_id"]}')
        body = r.get_json()
        assert body['task_template']['name'] == '安全设备季巡'
        by_name = {d['device_name']: d for d in body['devices']}
        assert by_name['FW-01']['match_type'] == 'task_template'
        assert by_name['FW-01']['items'][0]['name'] == '会话数'
        # 任务模板只关联了防火墙模板 → 交换机/服务器不匹配
        assert by_name['SW-01']['items'] == []

    def test_unknown_customer_404(self, op_client):
        assert op_client.get('/api/customers/9999/devices-with-templates').status_code == 404

    def test_permission_required(self, client, seed):
        assert client.get(f'/api/customers/{seed["customer_id"]}/devices-with-templates').status_code == 401


class TestInspectionFormTemplateSelector:
    def test_add_form_renders_customers_and_selector(self, op_client, seed):
        """回归：新建巡检页必须渲染客户下拉（曾缺 customers 变量）+ 模板选择器"""
        r = op_client.get('/inspections/add')
        assert r.status_code == 200
        body = r.data.decode('utf-8')
        assert '巡检模板客户' in body  # customers 已传入
        assert 'taskTemplateSelect' in body
        assert '安全设备季巡' in body

    def test_edit_form_renders_customers(self, op_client, seed, app):
        with app.app_context():
            from models import Inspection
            from datetime import date
            i = Inspection(title='X', customer_id=seed['customer_id'],
                           inspection_date=date.today())
            db.session.add(i)
            db.session.commit()
            iid = i.id
        r = op_client.get(f'/inspections/edit/{iid}')
        assert r.status_code == 200
        assert '巡检模板客户' in r.data.decode('utf-8')
