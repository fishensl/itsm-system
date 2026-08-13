# -*- coding: utf-8 -*-
"""Vue API：数据备份（统计/导出/导入）"""
from models import db, Customer


class TestBackupApi:
    def test_stats_requires_admin(self, op_client, admin_client):
        assert op_client.get('/api/system/backup/stats').status_code == 403
        assert admin_client.get('/api/system/backup/stats').status_code == 200

    def test_export_config_only(self, admin_client, app):
        """导出改服务端落盘：返回 token（一次性下载），下载端点可拿到文件"""
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

    def test_backup_result_status_is_persisted_and_exposed(self, app, admin_client):
        with app.app_context():
            from utils.backup_config import record_backup_result, save_backup_config
            save_backup_config({'backup_enabled': '1'})
            failed = record_backup_result(False, 'pg_dump failed\nconnection closed', 3.2)
            assert failed['health'] == 'failed'
            assert failed['consecutive_failures'] == 1
            assert '\n' not in failed['last_error']
            succeeded = record_backup_result(True, duration_seconds=4.5)
            assert succeeded['health'] == 'ok'
            assert succeeded['consecutive_failures'] == 0
            assert succeeded['last_success_at'].endswith('Z')
        stats = admin_client.get('/api/system/backup/stats').get_json()['data']
        assert stats['backup']['health'] == 'ok'
        overview = admin_client.get('/api/system/overview').get_json()['data']
        assert overview['backup']['rpo_age_hours'] is not None

    def test_scheduler_failure_records_state_and_alerts_admins(self, app, monkeypatch):
        import subprocess
        import utils.notifications as notifications
        import utils.scheduler as scheduler

        alerts = []
        monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs:
                            subprocess.CompletedProcess(args[0], 2, '', 'pg_dump failed'))
        monkeypatch.setattr(notifications, 'notify_backup_failure', alerts.append)
        with app.app_context():
            from utils.backup_config import get_backup_status, save_backup_config
            save_backup_config({'backup_enabled': '1'})
            assert scheduler._backup_job() == 0
            status = get_backup_status()
            assert status['health'] == 'failed'
            assert status['consecutive_failures'] == 1
            assert alerts and '连续失败 1 次' in alerts[0]

    def test_import_creates_pre_backup(self, tmp_path):
        """导入前自动备份当前数据到 BACKUP_DIR/pre_import_<ts>.zip（响应携带文件名）"""
        import io
        import os
        import zipfile

        # 独立 app 实例指定 BACKUP_DIR（隔离，不污染项目 backups/）
        from app import create_app
        app2 = create_app({
            'TESTING': True,
            'SECRET_KEY': 'test-secret-key-for-pytest',
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'WTF_CSRF_ENABLED': False,
            'RATELIMIT_ENABLED': False,
            'BACKUP_DIR': str(tmp_path),
        })
        with app2.app_context():
            from models import User
            from models.base import db as _db
            _db.create_all()
            from utils.seed_permissions import seed_all
            seed_all()
            _db.session.add(User.create_with_password(
                username='admin', password='test123456', realname='管理员', role='admin'))
            _db.session.commit()
        client = app2.test_client()
        client.post('/api/auth/login', json={'username': 'admin', 'password': 'test123456'})

        # 最小备份包（含 manifest + data.json，供导入）
        def _make_zip() -> bytes:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w') as zf:
                zf.writestr('manifest.json',
                            '{"format_version":1,"table_counts":{},"table_columns":{},"sha256":""}')
                zf.writestr('data.json', '{}')
            return buf.getvalue()

        r = client.post('/api/system/backup/import', data={
            'backup_file': (io.BytesIO(_make_zip()), 'bak.zip'),
            'confirm': '我确认覆盖', 'restore_secret_key': '0',
        }, content_type='multipart/form-data')
        assert r.status_code == 200, r.get_json()
        d = r.get_json()['data']
        assert d['pre_import_file'] and d['pre_import_file'].startswith('pre_import_')
        # 落盘文件存在且与响应一致
        files = [f for f in os.listdir(str(tmp_path)) if f.startswith('pre_import_')]
        assert len(files) == 1
        assert files[0] == d['pre_import_file']
        assert '导入前已自动备份' in d['message']

    def test_import_stops_when_pre_backup_fails(self, admin_client, monkeypatch):
        import io
        import zipfile
        import utils.data_io as data_io

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('manifest.json',
                        '{"format_version":1,"table_counts":{},"table_columns":{},"sha256":""}')
            zf.writestr('data.json', '{}')
        buf.seek(0)

        def _fail_backup(*_args, **_kwargs):
            raise OSError('disk full')

        monkeypatch.setattr(data_io, 'build_export_zip', _fail_backup)
        response = admin_client.post('/api/system/backup/import', data={
            'backup_file': (buf, 'bak.zip'),
            'confirm': '我确认覆盖',
            'restore_secret_key': '0',
        }, content_type='multipart/form-data')
        assert response.status_code == 500
        assert '已停止导入' in response.get_json()['message']
