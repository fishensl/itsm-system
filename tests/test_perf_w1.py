# -*- coding: utf-8 -*-
"""W1 性能修复回归：页面可渲染 + 数据正确性（N+1 修复不改变输出）"""
from datetime import date, timedelta

import pytest

from models import (db, Customer, Device, DeviceFirmware, Rack, RackInstall,
                    Inspection, Ticket, InspectionTask, Inspector, User)


@pytest.fixture()
def seed(app):
    with app.app_context():
        c = Customer(name='性能客户')
        db.session.add(c)
        db.session.flush()
        d = Device(customer_id=c.id, device_name='SW-01', brand='华为', model='S5735',
                   password_encrypted='x')
        db.session.add(d)
        db.session.add(DeviceFirmware(brand='华为', model='S5735', firmware_type='系统固件',
                                      version='V2R20', is_latest=True))
        rack = Rack(customer_id=c.id, name='A01', total_u=42)
        db.session.add(rack)
        db.session.flush()
        db.session.add(RackInstall(rack_id=rack.id, device_id=d.id, start_u=10, occupy_u=2))
        insp = Inspection(title='Q2巡检', customer_id=c.id,
                          inspection_date=date.today(), overall_status='正常')
        db.session.add(insp)
        old_insp = Inspection(title='三年前巡检', customer_id=c.id,
                              inspection_date=date.today() - timedelta(days=1100),
                              overall_status='正常')
        db.session.add(old_insp)
        tk = Ticket(number='WO-20260719-001', title='断网', customer_id=c.id,
                    status='处理中', assigned_to='op')
        db.session.add(tk)
        db.session.commit()
        yield {'customer_id': c.id, 'device_id': d.id, 'rack_id': rack.id,
               'insp_id': insp.id, 'old_insp_id': old_insp.id, 'ticket_id': tk.id}


class TestIndexByRole:
    @pytest.mark.parametrize('role_client', ['admin_client', 'op_client',
                                             'sales_client', 'viewer_client'])
    def test_index_200(self, role_client, seed, request):
        client = request.getfixturevalue(role_client)
        assert client.get('/').status_code == 200

    def test_index_shows_assigned_ticket(self, op_client, seed):
        """operator 首页待办包含派给他的工单（assigned_to 匹配 realname/username）"""
        r = op_client.get('/')
        assert '断网'.encode() in r.data


class TestInspectorTaskSqlMatch:
    def test_comma_wrapped_match_no_false_positive(self, op_client, app, seed):
        """inspector_ids 逗号包裹匹配：id=2 不应命中 '12'"""
        with app.app_context():
            op = User.query.filter_by(username='op').first()
            insp_person = Inspector(user_id=op.id, is_active=True)
            db.session.add(insp_person)
            db.session.flush()
            iid = insp_person.id
            # 构造干扰任务：inspector_ids 含 '999,1001' 但不含独立 ',iid,'（iid 若为 10，1001 也不能误匹配）
            decoy = InspectionTask(title='干扰任务', customer_id=seed['customer_id'],
                                   status='待执行', task_type='计划',
                                   inspector_ids='999,1001')
            hit = InspectionTask(title='我的任务', customer_id=seed['customer_id'],
                                 status='待执行', task_type='计划',
                                 inspector_ids=f'5,{iid},9')
            db.session.add_all([decoy, hit])
            db.session.commit()
        r = op_client.get('/')
        body = r.data.decode('utf-8')
        assert '我的任务' in body
        assert '干扰任务' not in body


class TestFirmwareList:
    def test_devices_grouped_single_pass(self, op_client, seed):
        r = op_client.get('/device-firmwares')
        assert r.status_code == 200
        assert 'SW-01'.encode() in r.data  # 同 brand+model 设备挂到固件组下


class TestRackApis:
    def test_cabinets_list(self, op_client, seed):
        r = op_client.get('/api/rack/cabinets')
        assert r.status_code == 200
        items = r.get_json()['items']
        assert len(items) == 1
        assert items[0]['used_u'] == 2
        assert items[0]['install_count'] == 1

    def test_cabinet_detail(self, op_client, seed):
        r = op_client.get(f'/api/rack/cabinets/{seed["rack_id"]}')
        assert r.status_code == 200
        body = r.get_json()
        assert body['installs'][0]['name'] == 'SW-01'
        assert body['installs'][0]['start_u'] == 10

    def test_devices_all_marks_installed(self, op_client, seed):
        r = op_client.get(f'/api/rack/devices/all?customer_id={seed["customer_id"]}')
        items = r.get_json()['items']
        assert items[0]['installed'] is True


class TestReportCenter:
    def test_default_window_excludes_old_records(self, op_client, seed):
        """无过滤条件默认近 12 个月：三年前的巡检不出现在报告中心"""
        r = op_client.get('/reports')
        assert r.status_code == 200
        body = r.data.decode('utf-8')
        assert 'Q2巡检' in body
        assert '三年前巡检' not in body
        assert '默认显示近 12 个月' in body  # 默认窗口提示

    def test_explicit_date_range_shows_old(self, op_client, seed):
        old = (date.today() - timedelta(days=1200)).isoformat()
        r = op_client.get(f'/reports?date_from={old}')
        body = r.data.decode('utf-8')
        assert '三年前巡检' in body

    def test_tab_filter(self, op_client, seed):
        r = op_client.get('/reports?tab=ticket')
        assert r.status_code == 200
