# -*- coding: utf-8 -*-
"""批量导入端点：备件档案/库存/巡检记录/故障记录（模板列见 views/system.download_template）"""
import io

from models import (db, Customer, SparePart, SpareStock, Inspection, Fault)


def _xlsx(headers, rows):
    """构造 xlsx bytes：headers 为列名列表，rows 为单元格列表列表"""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestSpareImport:
    def test_import_spare_parts(self, admin_client, app):
        data = _xlsx(
            ['编码', '名称', '分类', '规格', '单位', '最低库存', '备注'],
            [['SP-001', '光模块SFP', '光模块', '千兆', '个', '5', ''],
             ['SP-002', '电源模块', '电源', '48V', '个', '2', '备用'],
             ['SP-001', '光模块SFP-重复', '光模块', '', '', '', '']])  # 编码重复应跳过
        r = admin_client.post('/api/spare-parts/import',
                              data={'import_file': (io.BytesIO(data), 'spare.xlsx')},
                              content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        d = r.get_json()['data']
        assert d['success'] == 2
        assert d['skipped'] == 1
        with app.app_context():
            assert SparePart.query.filter_by(code='SP-001').count() == 1

    def test_import_spare_stocks(self, admin_client, app):
        with app.app_context():
            p = SparePart(name='硬盘1T', code='HDD-1T')
            db.session.add(p)
            db.session.commit()
            pid = p.id
        data = _xlsx(
            ['备件名称', '位置', '数量', '单价'],
            [['硬盘1T', 'A柜-01', '10', '450'],
             ['硬盘1T', 'A柜-01', '5', '450'],    # 同名库位累加
             ['不存在的备件', 'B柜', '1', '1']])   # 报错行
        r = admin_client.post('/api/spare-stocks/import',
                              data={'import_file': (io.BytesIO(data), 'stock.xlsx')},
                              content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        d = r.get_json()['data']
        assert d['success'] == 1
        assert len(d['errors']) == 1
        with app.app_context():
            s = SpareStock.query.filter_by(spare_part_id=pid).first()
            assert s.quantity == 15  # 10 + 5 累加


class TestInspectionFaultImport:
    def test_import_inspections(self, admin_client, app):
        with app.app_context():
            c = Customer(name='巡检导入客户')
            db.session.add(c)
            db.session.commit()
            cid = c.id
        data = _xlsx(
            ['客户名称', '标题', '巡检人员', '巡检日期', '巡检地点', '总体状态', '结论', '备注'],
            [['巡检导入客户', '季度巡检', '张工', '2026-08-01', '机房A', '正常', '无异常', ''],
             ['不存在的客户', '无效巡检', '', '', '', '', '', '']])
        r = admin_client.post('/api/inspections/import',
                              data={'import_file': (io.BytesIO(data), 'insp.xlsx')},
                              content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        d = r.get_json()['data']
        assert d['success'] == 1
        assert len(d['errors']) == 1
        with app.app_context():
            i = Inspection.query.filter_by(customer_id=cid).first()
            assert i.title == '季度巡检'
            assert i.overall_status == '正常'

    def test_import_faults(self, admin_client, app):
        with app.app_context():
            c = Customer(name='故障导入客户')
            db.session.add(c)
            db.session.commit()
            cid = c.id
        data = _xlsx(
            ['客户名称', '标题', '处理人', '故障时间', '故障类型', '故障描述', '故障原因', '解决方案', '处理结果'],
            [['故障导入客户', '交换机离线', '李工', '2026-08-02', '网络故障',
              '端口down', '光纤松动', '重新插拔', '已解决']])
        r = admin_client.post('/api/faults/import',
                              data={'import_file': (io.BytesIO(data), 'fault.xlsx')},
                              content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        d = r.get_json()['data']
        assert d['success'] == 1
        with app.app_context():
            f = Fault.query.filter_by(customer_id=cid).first()
            assert f.title == '交换机离线'
            assert f.result == '已解决'
