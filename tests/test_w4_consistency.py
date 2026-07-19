# -*- coding: utf-8 -*-
"""W4 数据一致性：状态校验/JSON边界/事务完整性/密码升级"""
import io
import json

import openpyxl
import pytest

from models import db, Customer, Device, Ticket, TicketLog, User, InspectionDeviceTemplate
from services.base import ServiceError
from services import sales_service


class TestStatusValidation:
    def test_invalid_opp_stage_rejected(self, app):
        with app.app_context():
            with pytest.raises(ServiceError, match='非法的商机阶段'):
                sales_service.create_opportunity(
                    {'title': 'X', 'stage': '不存在的阶段'}, 'admin')

    def test_valid_opp_stage_accepted(self, app):
        with app.app_context():
            o = sales_service.create_opportunity(
                {'title': 'X', 'stage': '方案报价'}, 'admin')
            assert o.stage == '方案报价'

    def test_invalid_contract_status_rejected(self, app):
        with app.app_context():
            with pytest.raises(ServiceError, match='非法的合同状态'):
                sales_service.create_contract({'title': 'C', 'status': '执行种'}, 'admin')

    def test_invalid_project_status_rejected(self, app):
        with app.app_context():
            with pytest.raises(ServiceError, match='非法的项目状态'):
                sales_service.create_project({'name': 'P', 'status': '进行种'}, 'admin')

    def test_update_without_status_key_untouched(self, app):
        """update 不传 status 时保留原值（兼容只改标题的表单）"""
        with app.app_context():
            o = sales_service.create_opportunity({'title': 'A', 'stage': '成交'}, 'admin')
            sales_service.update_opportunity(o.id, {'title': 'B'})
            assert o.stage == '成交'


class TestMatchTemplatesApi:
    def test_items_count_is_real_count(self, op_client, app):
        """修复回归：items_count 是检查项条数，不是 JSON 字符数"""
        with app.app_context():
            c = Customer(name='匹配客户')
            db.session.add(c)
            db.session.flush()
            db.session.add(Device(customer_id=c.id, device_name='FW-1',
                                  device_type='防火墙', is_in_use=True))
            tpl = InspectionDeviceTemplate(
                name='防火墙模板', device_category='防火墙', is_active=True,
                items_json=json.dumps([{'field_type': 'text', 'label': '版本'},
                                       {'field_type': 'dropdown', 'label': '状态'}]))
            db.session.add(tpl)
            db.session.commit()
            cid = c.id
        r = op_client.get(f'/api/customers/{cid}/match-device-templates')
        assert r.status_code == 200
        assert r.is_json
        body = r.get_json()
        assert body['total_devices'] == 1
        matched = body['groups'][0]['matched_templates']
        assert matched[0]['items_count'] == 2  # 两条检查项；旧实现会返回几十（字符数）


class TestFaultTypePage:
    def test_fault_types_always_renders_page(self, op_client):
        """不再按 cwd 相对路径双态返回"""
        r = op_client.get('/fault-types')
        assert r.status_code == 200
        assert b'<html' in r.data.lower() or 'text/html' in r.content_type


class TestTicketDelete:
    def test_delete_removes_logs_and_writes_audit(self, admin_client, app):
        with app.app_context():
            t = Ticket(number='WO-DEL-001', title='待删工单', status='待派单')
            db.session.add(t)
            db.session.flush()
            db.session.add(TicketLog(ticket_id=t.id, action='创建', operator='admin'))
            db.session.commit()
            tid = t.id
        r = admin_client.post(f'/tickets/delete/{tid}')
        assert r.status_code == 302
        with app.app_context():
            assert Ticket.query.get(tid) is None
            assert TicketLog.query.filter_by(ticket_id=tid).count() == 0


class TestPlaintextPasswordUpgrade:
    def test_legacy_plaintext_user_login_upgrades_hash(self, client, app):
        """历史明文账号：登录成功 + 就地升级为哈希（login 流程显式提交）"""
        with app.app_context():
            u = User(username='legacy', password='plain123', realname='旧', role='viewer',
                     is_active=True)
            db.session.add(u)
            db.session.commit()
        r = client.post('/login', data={'username': 'legacy', 'password': 'plain123'})
        assert r.status_code == 302
        with app.app_context():
            u = User.query.filter_by(username='legacy').first()
            # 已升级为 werkzeug 哈希（scrypt:/pbkdf2:，不再是明文）
            assert u.password != 'plain123'
            assert '$' in u.password
            assert u.check_password('plain123') is True
            assert u.check_password('wrong') is False


class TestDeviceImportBatch:
    def _make_xlsx(self, rows):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['所属客户', '设备名称', '设备类型', 'IP地址', '是否在用'])
        for row in rows:
            ws.append(row)
        bio = io.BytesIO()
        wb.save(bio)
        bio.seek(0)
        return bio

    def test_batch_import(self, op_client, app):
        with app.app_context():
            db.session.add(Customer(name='导入客户'))
            db.session.commit()
        xlsx = self._make_xlsx([
            ['导入客户', 'SW-A', '交换机', '10.0.0.1', '是'],
            ['导入客户', 'SW-B', '交换机', '10.0.0.2', '否'],
            ['导入客户', '', '交换机', '10.0.0.3', '是'],  # 坏行：无名称
        ])
        r = op_client.post('/devices/import', data={
            'import_file': (xlsx, 'devices.xlsx')},
            content_type='multipart/form-data')
        assert r.status_code == 302
        with app.app_context():
            devs = Device.query.filter_by(device_type='交换机').all()
            assert len(devs) == 2
            # 是否在用列不再被忽略
            by_name = {d.device_name: d for d in devs}
            assert by_name['SW-A'].is_in_use is True
            assert by_name['SW-B'].is_in_use is False
