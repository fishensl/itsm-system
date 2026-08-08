# -*- coding: utf-8 -*-
"""Vue API：数据备份（统计/导出/导入）"""
from models import db, Customer


class TestBackupApi:
    def test_stats_requires_admin(self, op_client, admin_client):
        assert op_client.get('/api/system/backup/stats').status_code == 403
        assert admin_client.get('/api/system/backup/stats').status_code == 200

    def test_export_config_only(self, admin_client, app):
        """导出改服务端落盘：返回 token（一次性下载），下载端点可拿到文件"""
        import io
        with app.app_context():
            db.session.add(Customer(name='备份测试客户'))
            db.session.commit()
        r = admin_client.post('/api/system/backup/export', json={'config_only': True})
        assert r.get_json()['code'] == 0
        d = r.get_json()['data']
        assert d['filename'].endswith('.zip')
        assert d['filename'].startswith('itsm_backup_')
        assert d['token']  # 服务端落盘 token（非 base64）
        # 一次性下载可用
        r2 = admin_client.get(f"/api/system/backup/export-download/{d['token']}")
        assert r2.status_code == 200
        assert len(r2.data) > 0
        assert r2.data[:4] == b'PK\x03\x04' or r2.data[:8] == b'ITSMBAK1'  # zip 或加密包 magic

    def test_import_requires_confirm(self, admin_client):
        r = admin_client.post('/api/system/backup/import', data={
            'confirm': 'no', 'restore_secret_key': '0',
        })
        assert r.status_code == 400

    def test_import_rejects_non_zip(self, admin_client):
        r = admin_client.post('/api/system/backup/import', data={
            'confirm': '我确认覆盖', 'restore_secret_key': '0',
        })
        assert r.status_code == 400  # 无文件

    def test_backup_config_defaults(self, admin_client):
        """未配置时返回默认值（开关关闭/03:00/保留30）"""
        r = admin_client.get('/api/system/backup/config')
        assert r.status_code == 200
        d = r.get_json()['data']
        assert d['backup_enabled'] == '0'
        assert d['backup_time'] == '03:00'
        assert d['backup_keep'] == '30'

    def test_backup_config_save(self, admin_client, app):
        """保存并回读自动备份配置；非法值拒绝"""
        r = admin_client.post('/api/system/backup/config', json={
            'backup_enabled': '1', 'backup_time': '04:30', 'backup_keep': '15',
        })
        assert r.status_code == 200
        d = admin_client.get('/api/system/backup/config').get_json()['data']
        assert d['backup_enabled'] == '1'
        assert d['backup_time'] == '04:30'
        assert d['backup_keep'] == '15'
        # 非法时间
        r = admin_client.post('/api/system/backup/config', json={'backup_time': '25:99'})
        assert r.status_code == 400
        # 非法保留份数
        r = admin_client.post('/api/system/backup/config', json={'backup_keep': '0'})
        assert r.status_code == 400

    def test_backup_config_requires_admin(self, op_client):
        assert op_client.get('/api/system/backup/config').status_code == 403
