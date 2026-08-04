# -*- coding: utf-8 -*-
"""Vue API：数据备份（统计/导出/导入）"""
from models import db, Customer


class TestBackupApi:
    def test_stats_requires_admin(self, op_client, admin_client):
        assert op_client.get('/api/system/backup/stats').status_code == 403
        assert admin_client.get('/api/system/backup/stats').status_code == 200

    def test_export_config_only(self, admin_client, app):
        with app.app_context():
            db.session.add(Customer(name='备份测试客户'))
            db.session.commit()
        r = admin_client.post('/api/system/backup/export', json={'config_only': True})
        assert r.get_json()['code'] == 0
        d = r.get_json()['data']
        assert d['filename'].endswith('.zip')
        assert d['filename'].startswith('itsm_backup_')
        assert d['content']

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
