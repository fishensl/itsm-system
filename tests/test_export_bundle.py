# -*- coding: utf-8 -*-
"""V24 资料包导出：巡检 6 项勾选打包（config_text 开关、仅最新版本、目录结构）、工单处理报告包"""
import io
import os
import shutil
import zipfile
import pytest

from models import (db, Customer, Inspection, Ticket, SubmissionVersion,
                    SubmissionAsset)

_TEST_DIR = os.path.join('static', 'uploads', 'test_export_bundle')


@pytest.fixture()
def files(app):
    """真实写入 static/uploads/test_export_bundle（uploads 为运行时目录），teardown 清理"""
    os.makedirs(_TEST_DIR, exist_ok=True)
    # file_path 约定：相对 static/ 的路径（模型层约定），如 uploads/test_export_bundle/v2.docx
    rel = {
        'v1': 'uploads/test_export_bundle/v1.docx',
        'v2': 'uploads/test_export_bundle/v2.docx',
        'cfg': 'uploads/test_export_bundle/cfg.zip',
        'topo': 'uploads/test_export_bundle/topo.png',
        'assets': 'uploads/test_export_bundle/assets.xlsx',
        'formal': 'uploads/test_export_bundle/formal.docx',
        'tick': 'uploads/test_export_bundle/ticket.docx',
    }
    for p in rel.values():
        with open(os.path.join('static', p), 'wb') as f:
            f.write(('dummy-' + os.path.basename(p)).encode())
    yield rel
    shutil.rmtree(_TEST_DIR, ignore_errors=True)


@pytest.fixture()
def seed(app, files):
    with app.app_context():
        c = Customer(name='打包客户')
        db.session.add(c)
        db.session.flush()
        i = Inspection(title='打包巡检', customer_id=c.id, inspection_date=None,
                       inspector_name='op', overall_status='已通过',
                       review_status='已通过', report_file=files['formal'])
        db.session.add(i)
        db.session.flush()
        # 版本 1（已退回，不应出现在包内）
        v1 = SubmissionVersion(entity_type='inspection', entity_id=i.id, version_no=1,
                               report_file=files['v1'], review_status='已退回')
        db.session.add(v1)
        db.session.flush()
        db.session.add(SubmissionAsset(version_id=v1.id, asset_type='report',
                                       file_path=files['v1'], file_name='v1.docx'))
        # 版本 2（最新）
        v2 = SubmissionVersion(entity_type='inspection', entity_id=i.id, version_no=2,
                               report_file=files['v2'], review_status='已通过')
        db.session.add(v2)
        db.session.flush()
        db.session.add(SubmissionAsset(version_id=v2.id, asset_type='report',
                                       file_path=files['v2'], file_name='v2.docx'))
        db.session.add(SubmissionAsset(version_id=v2.id, asset_type='config_zip',
                                       file_path=files['cfg'], file_name='cfg.zip'))
        db.session.add(SubmissionAsset(version_id=v2.id, asset_type='config_text',
                                       file_name='sw.txt', content_text='hostname SW'))
        db.session.add(SubmissionAsset(version_id=v2.id, asset_type='topology',
                                       file_path=files['topo'], file_name='topo.png'))
        db.session.add(SubmissionAsset(version_id=v2.id, asset_type='asset_list',
                                       file_path=files['assets'], file_name='assets.xlsx'))
        # 工单 + 处理报告版本
        t = Ticket(number='WO-BUNDLE-1', title='打包工单', customer_id=c.id,
                   status='已完成', priority='中', assigned_to='op')
        db.session.add(t)
        db.session.flush()
        tv = SubmissionVersion(entity_type='ticket', entity_id=t.id, version_no=1,
                               report_file=files['tick'], review_status='已通过')
        db.session.add(tv)
        db.session.commit()
        yield {'c': c.id, 'i': i.id, 't': t.id}


def _download_zip(client, download_url):
    r = client.get(download_url)
    assert r.status_code == 200
    return zipfile.ZipFile(io.BytesIO(r.data))


class TestInspectionBundle:
    def test_all_items_zip_structure(self, app, op_client, seed, monkeypatch, tmp_path):
        from blueprints import vue_export
        monkeypatch.setattr(vue_export, 'EXPORT_DIR', str(tmp_path))
        r = op_client.post('/api/inspections/export-bundle', json={
            'items': ['report', 'formal_report', 'config_zip', 'config_text',
                      'topology', 'asset_list'],
            'customer_id': seed['c']})
        assert r.get_json()['code'] == 0
        d = r.get_json()['data']
        assert d['download_url'].startswith('/api/v2/export-download/')
        zf = _download_zip(op_client, d['download_url'])
        names = set(zf.namelist())
        base = '打包客户/巡检{}_打包巡检'.format(seed['i'])
        assert f'{base}/现场报告/v2.docx' in names
        assert f'{base}/正式报告/formal.docx' in names
        assert f'{base}/完整配置备份包/cfg.zip' in names
        assert f'{base}/核心设备文本配置/sw.txt' in names
        assert f'{base}/拓扑图/topo.png' in names
        assert f'{base}/资产清单/assets.xlsx' in names
        assert '记录明细.xlsx' in names
        # 仅最新版本：v1 报告不应出现
        assert not any('v1.docx' in n for n in names)
        # 路径防穿越 + 中文正常
        assert all('..' not in n for n in names)
        # config_text 内容正确
        with zf.open(f'{base}/核心设备文本配置/sw.txt') as f:
            assert f.read().decode() == 'hostname SW'

    def test_config_text_toggle_off(self, app, op_client, seed, monkeypatch, tmp_path):
        from blueprints import vue_export
        monkeypatch.setattr(vue_export, 'EXPORT_DIR', str(tmp_path))
        r = op_client.post('/api/inspections/export-bundle', json={
            'items': ['report', 'formal_report'], 'customer_id': seed['c']})
        assert r.get_json()['code'] == 0
        zf = _download_zip(op_client, r.get_json()['data']['download_url'])
        names = set(zf.namelist())
        assert not any('配置' in n for n in names)
        assert any('现场报告' in n for n in names)

    def test_download_one_time(self, app, op_client, seed, monkeypatch, tmp_path):
        from blueprints import vue_export
        monkeypatch.setattr(vue_export, 'EXPORT_DIR', str(tmp_path))
        r = op_client.post('/api/inspections/export-bundle', json={
            'items': ['report'], 'customer_id': seed['c']})
        url = r.get_json()['data']['download_url']
        assert op_client.get(url).status_code == 200
        # 二次下载 404（一次性）
        r2 = op_client.get(url)
        assert r2.status_code == 404

    def test_other_user_cannot_download(self, app, op_client, viewer_client, seed, monkeypatch, tmp_path):
        from blueprints import vue_export
        monkeypatch.setattr(vue_export, 'EXPORT_DIR', str(tmp_path))
        r = op_client.post('/api/inspections/export-bundle', json={
            'items': ['report'], 'customer_id': seed['c']})
        url = r.get_json()['data']['download_url']
        r2 = viewer_client.get(url)
        assert r2.status_code == 404  # 非创建人不可下载


class TestTicketBundle:
    def test_report_latest_version_only(self, app, op_client, seed, monkeypatch, tmp_path):
        from blueprints import vue_export
        monkeypatch.setattr(vue_export, 'EXPORT_DIR', str(tmp_path))
        with app.app_context():
            t = db.session.get(Ticket, seed['t'])
            # 加一个更新版本（v2）模拟最新处理报告
            v2 = SubmissionVersion(entity_type='ticket', entity_id=t.id, version_no=2,
                                   report_file='uploads/test_export_bundle/ticket2.docx',
                                   review_status='已通过')
            db.session.add(v2)
            db.session.commit()
        with open(os.path.join(_TEST_DIR, 'ticket2.docx'), 'wb') as f:
            f.write(b'dummy-ticket2.docx')
        r = op_client.post('/api/tickets/export-bundle', json={
            'items': ['report'], 'customer_id': seed['c']})
        assert r.get_json()['code'] == 0
        zf = _download_zip(op_client, r.get_json()['data']['download_url'])
        names = set(zf.namelist())
        base = '打包客户/工单{}_打包工单'.format(seed['t'])
        assert f'{base}/处理报告/ticket2.docx' in names
        assert not any('ticket.docx' in n for n in names)
        assert '记录明细.xlsx' in names

    def test_bundle_empty_400(self, app, op_client, seed):
        r = op_client.post('/api/tickets/export-bundle', json={
            'items': ['report'], 'date_from': '2099-01-01'})
        assert r.status_code == 400
