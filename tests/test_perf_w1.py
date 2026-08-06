# -*- coding: utf-8 -*-
"""W1 性能修复回归：页面渲染（SSR 已剥离 → Vue API 等价断言）+ 数据正确性"""

from datetime import date, timedelta

import pytest

from models import (db, Customer, Device, DeviceFirmware, Rack, RackInstall,
                    Inspection, Ticket, InspectionTask, User)


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
    def test_index_302(self, role_client, request):
        """SSR 首页已剥离：无论界面版本，GET / 一律 302 → /app/"""
        client = request.getfixturevalue(role_client)
        r = client.get('/')
        assert r.status_code == 302
        assert r.headers.get('Location', '').endswith('/app/')

    def test_overview_shows_assigned_ticket(self, op_client, seed):
        """Vue 工作台 API 待办包含派给他的工单（assigned_to 匹配 realname/username）"""
        r = op_client.get('/api/dashboard/overview')
        assert r.status_code == 200
        tasks = r.get_json()['data']['my_tasks']
        assert any(t['type_label'] == '工单' and t['title'] == '断网' for t in tasks)


class TestInspectorTaskMatch:
    def test_assigned_to_user_id_match(self, op_client, app, seed):
        """巡检待办按 assigned_to_user_id 精确匹配：未指派的任务不出现在我的待办"""
        with app.app_context():
            op = User.query.filter_by(username='op').first()
            decoy = InspectionTask(title='干扰任务', customer_id=seed['customer_id'],
                                   status='待执行', task_type='计划',
                                   inspector_ids='999,1001')
            hit = InspectionTask(title='我的任务', customer_id=seed['customer_id'],
                                 status='待执行', task_type='计划',
                                 assigned_to_user_id=op.id)
            db.session.add_all([decoy, hit])
            db.session.commit()
        r = op_client.get('/api/dashboard/overview')
        tasks = r.get_json()['data']['my_tasks']
        titles = [t['title'] for t in tasks]
        assert '我的任务' in titles
        assert '干扰任务' not in titles


class TestFirmwareList:
    def test_firmware_page_gone(self, op_client):
        """SSR 固件列表页已剥离（Vue /app/device-firmwares 接管）"""
        assert op_client.get('/device-firmwares').status_code == 404


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
        """无过滤条件默认近 12 个月：三年前的巡检不出现在报告中心 API"""
        r = op_client.get('/api/reports')
        assert r.status_code == 200
        data = r.get_json()['data']
        titles = [i['title'] for b in data['data_order'] for i in b['items']['inspection']]
        assert 'Q2巡检' in titles
        assert '三年前巡检' not in titles

    def test_explicit_date_range_shows_old(self, op_client, seed):
        old = (date.today() - timedelta(days=1200)).isoformat()
        r = op_client.get(f'/api/reports?date_from={old}')
        data = r.get_json()['data']
        titles = [i['title'] for b in data['data_order'] for i in b['items']['inspection']]
        assert '三年前巡检' in titles

    def test_tab_filter(self, op_client, seed):
        r = op_client.get('/api/reports?tab=ticket')
        assert r.status_code == 200
        assert r.get_json()['code'] == 0
