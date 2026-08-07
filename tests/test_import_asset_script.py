# -*- coding: utf-8 -*-
"""导入脚本（scripts/import_asset_devices.py）解析与落库测试"""
import io
import tempfile

import openpyxl

from models import db, Customer, Device


HEADERS = ['序号', '位置', '设备名称', 'IP地址', '用户名密码', '品牌', '型号',
           '接口类型及数量', '电源', '建设时间', '硬件维修情况', '是否在用',
           '序列号', '授权到期时间', '系统版本', '规则库版本']


def _make_xlsx(rows):
    """构造与资产登记表同构的 xlsx：首行为文档标题，次行为列标题，含机柜组头行"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '网络设备'
    ws.append(['鄱阳湖水文网络设备资产登记表'])
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


def _sample_rows():
    return [
        ['机房机柜1', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
        [1, '42U', '启明星辰防火墙2', '10.36.34.218', '', '天清汉马', 'SAG-6000-1600',
         '24个千兆电口，4个千兆光口', '单', '2023-03-01', '无维修', '在用',
         'NT00299844', '', '', ''],
        [2, '39U', '大队防火墙', '10.36.34.219', '', '天清汉马', 'SAG-6000-1600',
         '', '单', '', '无维修', '在用', 'NT00299841', '', '', ''],
        [3, '37U', '交换机（大队视频监控）', '', '', 'H3C', 'S5130',
         '', '单', '', '无维修', '在用', '219801A2S9922BQ003G4', '', '', ''],
        [4, '32-34U', 'IP RAN接入设备', '', '', '华为', 'ATN 980C',
         '', '双', '', '无维修', '在用', '', '', '', ''],
        [5, '29U', '防火墙外网', '10.36.34.249', '', '绿盟', 'NFNX3-HDB1780',
         '', '单', '', '无维修', '在用', '210235A45NB21C000159', '', '', ''],
        ['机房机柜1背面', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
        [1, '32U', '光猫To省水文', '', '', '运营商设备', '',
         '', '单', '', '无维修', '在用', '', '', '', ''],
        ['机房机柜2', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
        [1, '37U', '防火墙-服务器', '10.36.130.250', '', '迪普', 'FW1000-GM-A',
         '', '单', '', '无维修', '在用', '02050389D174000186', '', '', ''],
        [2, '35U', 'ISP2(入侵防御系统)', '10.36.34.242', '', '绿盟', 'NIPSNX3-CH1350',
         '', '单', '', '无维修', '在用', '19-49-J-0490', '', '', ''],
        [9, '3-6U', '服务器', '', '', '浪潮', 'NF8460M3',
         '', '双', '', '无维修', '不在用', '214644963', '', '', ''],
        [6, '6U', '无线控制器', '', '', 'H3C', 'WX2540H',
         '', '单', '', '无维修', '在用', '180X1932279AY58', '', '', ''],
        # 跨机柜重名设备：自动加机柜后缀（服务器 3 台）
        ['机房机柜3', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
        [1, '36-37U', '服务器', '', '', 'DELL', 'E05S',
         '', '双', '', '无维修', '不在用', 'HPFK83X', '', '', ''],
        ['机房机柜4', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
        [7, '5-8U', '服务器', '', '', '浪潮', 'NF8460M3',
         '', '双', '', '无维修', '不在用', '214644966', '', '', ''],
        # 内嵌换行的设备名称/型号（真实资产表存在）
        [7, '8U', '交换机-光纤\n.11和.12虚拟机主机与机柜3存储之间的数据传输', '', '', '华为',
         'OceanStor\nSNS2124', '', '单', '', '无维修', '在用', '210235764810G6000500', '', '', ''],
        # 跨机柜重名设备：自动加机柜后缀（交换机(24口) 2 台）
        ['机房机柜3背面', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
        [1, '41U', '交换机(24口)', '', '', 'H3C', 'S5120',
         '', '单', '', '无维修', '在用', '05T9YC7493AOT7C', '', '', ''],
        ['机房机柜4背面', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None],
        [1, '42U', '交换机(24口)', '', '', 'H3C', 'S5130',
         '', '单', '', '无维修', '在用', 'ANAA0C12350TT7N', '', '', ''],
        # 坏行：无设备名称
        [8, '1U', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    ]


def _write_tmp_xlsx():
    f = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    f.write(_make_xlsx(_sample_rows()).read())
    f.close()
    return f.name


class TestParseAssetExcel:
    def test_parse_shape(self, app):
        from scripts.import_asset_devices import parse_asset_excel
        with app.app_context():
            rows, groups, errors = parse_asset_excel(_write_tmp_xlsx())
            assert groups == 7  # 机柜1 / 背面 / 机柜2 / 机柜3 / 机柜4 / 3背面 / 4背面
            assert len(rows) == 15  # 16 行数据 - 1 行空名称
            assert len(errors) == 1  # 空名称行

    def test_field_mapping(self, app):
        from scripts.import_asset_devices import parse_asset_excel
        with app.app_context():
            rows, _, _ = parse_asset_excel(_write_tmp_xlsx())
            by_name = {r['device_name']: r for r in rows}
            fw = by_name['启明星辰防火墙2']
            assert fw['device_type'] == '防火墙'
            assert fw['brand'] == '天清汉马'
            assert fw['model'] == 'SAG-6000-1600'
            assert fw['ip_address'] == '10.36.34.218'
            assert fw['location'] == '机房机柜1·42U'
            assert fw['license_start'] is not None  # 建设时间 2023-03-01
            assert fw['is_in_use'] is True
            assert fw['is_maintenance'] is False
            import json
            assert json.loads(fw['interface']) == ['24个千兆电口', '4个千兆光口']
            assert by_name['光猫To省水文']['location'] == '机房机柜1背面·32U'
            assert by_name['服务器']['is_in_use'] is False  # 不在用
            assert by_name['无线控制器']['device_type'] == '无线AP'
            assert by_name['ISP2(入侵防御系统)']['device_type'] == 'IPS'
            assert by_name['IPRAN接入设备']['device_type'] == '路由器'  # 名称空白已清洗
            assert 'IPRAN接入设备' in by_name
    def test_multiline_cleanup(self, app):
        from scripts.import_asset_devices import parse_asset_excel
        with app.app_context():
            rows, _, _ = parse_asset_excel(_write_tmp_xlsx())
            r = next(x for x in rows if x['device_name'].startswith('交换机-光纤'))
            assert '\n' not in r['device_name']
            assert '\n' not in r['model']
            assert r['model'] == 'OceanStorSNS2124'


class TestImportApply:
    def test_import_creates_devices(self, app):
        from scripts.import_asset_devices import import_devices
        with app.app_context():
            c = Customer(name='鄱阳湖水文水资源监测中心')
            db.session.add(c)
            db.session.commit()
            created, updated, skipped = import_devices(
                _write_tmp_xlsx(), customer_id=c.id, dry_run=False)
            assert created == 15
            assert updated == 0
            assert skipped == 0
            assert Device.query.filter_by(customer_id=c.id).count() == 15
            # device_count 快照已刷新（全量口径）
            assert c.device_count == 15
            # 跨机柜重名自动加后缀（服务器 3 台：1 原名 + 2 后缀）
            names = {d.device_name for d in Device.query.filter_by(customer_id=c.id).all()}
            assert '服务器' in names
            assert '服务器（机房机柜3）' in names
            assert '服务器（机房机柜4）' in names
            assert '交换机(24口)（机房机柜4背面）' in names

    def test_import_idempotent_and_update(self, app):
        from scripts.import_asset_devices import import_devices
        with app.app_context():
            c = Customer(name='鄱阳湖水文水资源监测中心')
            db.session.add(c)
            db.session.commit()
            import_devices(_write_tmp_xlsx(), customer_id=c.id, dry_run=False)
            # 重跑：默认跳过（幂等）
            created, updated, skipped = import_devices(
                _write_tmp_xlsx(), customer_id=c.id, dry_run=False)
            assert created == 0 and updated == 0 and skipped == 15
            # --update 覆盖更新
            created, updated, skipped = import_devices(
                _write_tmp_xlsx(), customer_id=c.id, dry_run=False, update=True)
            assert created == 0 and updated == 15
            assert Device.query.filter_by(customer_id=c.id).count() == 15

    def test_dry_run_no_write(self, app):
        from scripts.import_asset_devices import import_devices
        with app.app_context():
            c = Customer(name='鄱阳湖水文水资源监测中心')
            db.session.add(c)
            db.session.commit()
            import_devices(_write_tmp_xlsx(), customer_id=c.id, dry_run=True)
            assert Device.query.filter_by(customer_id=c.id).count() == 0
            assert c.device_count == 0
