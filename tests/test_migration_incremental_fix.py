# -*- coding: utf-8 -*-
"""迁移增量补列测试：模拟"服务器已跑过旧迁移（alembic 版本已越过），
新迁移负责幂等补列"的真实升级路径，防止再犯修改已发布迁移文件的错误。"""
import os
import tempfile

import pytest
from alembic import command


@pytest.fixture()
def mig_app():
    """独立临时 SQLite + 独立 app（每用例全新库，不走 conftest 共享库）"""
    from app import create_app
    tmp = tempfile.mkdtemp(prefix='itsm_mig_test_')
    db_uri = 'sqlite:///' + os.path.join(tmp, 'mig.db').replace(os.sep, '/')
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'mig-test-key',
        'WTF_CSRF_ENABLED': False,
        'RATELIMIT_ENABLED': False,
        'SQLALCHEMY_DATABASE_URI': db_uri,
    })
    return app, db_uri


def _run_alembic(app, db_uri, func, rev=None):
    """在 app context 内执行 alembic 命令（upgrade/downgrade）"""
    from alembic.config import Config
    cfg = Config(os.path.join('migrations', 'alembic.ini'))
    cfg.set_main_option('script_location', os.path.join('.', 'migrations'))
    cfg.set_main_option('sqlalchemy.url', db_uri)
    with app.app_context():
        if rev:
            func(cfg, rev)
        else:
            func(cfg)


class TestMigrationIncrementalFix:
    def test_upgrade_from_stale_schema_repairs_columns(self, mig_app):
        """服务器场景：alembic 已标记 head 但列缺失（被修改的迁移不重跑所致）→
        发布新迁移 6f5e4d3c2b1a 后 upgrade 幂等补列"""
        import sqlite3
        app, db_uri = mig_app
        db_path = db_uri.replace('sqlite:///', '')

        # 1) 升到 5f4e3d2c1b0a（服务器曾停留的版本）
        _run_alembic(app, db_uri, command.upgrade, '5f4e3d2c1b0a')

        # 2) 模拟服务器真实缺失状态：相关列被删（等价于修改后迁移未生效）
        conn = sqlite3.connect(db_path)
        conn.execute('ALTER TABLE submission_versions DROP COLUMN revision_requirements')
        conn.execute('ALTER TABLE submission_versions DROP COLUMN review_checklist_json')
        conn.execute('ALTER TABLE inspections DROP COLUMN submitted_report')
        conn.execute('ALTER TABLE inspection_task_templates DROP COLUMN required_assets_json')
        conn.commit()
        conn.close()

        # 3) 升级到 head → 新迁移 6f5e4d3c2b1a 幂等补列
        _run_alembic(app, db_uri, command.upgrade, 'head')

        conn = sqlite3.connect(db_path)
        sv_cols = {r[1] for r in conn.execute('PRAGMA table_info(submission_versions)')}
        insp_cols = {r[1] for r in conn.execute('PRAGMA table_info(inspections)')}
        tpl_cols = {r[1] for r in conn.execute('PRAGMA table_info(inspection_task_templates)')}
        assert 'revision_requirements' in sv_cols
        assert 'review_checklist_json' in sv_cols
        assert 'submitted_report' in insp_cols
        assert 'required_assets_json' in tpl_cols
        conn.close()

        # 4) 幂等重放：再 upgrade 一次不报错、列仍在
        _run_alembic(app, db_uri, command.upgrade, 'head')
        conn = sqlite3.connect(db_path)
        sv_cols = {r[1] for r in conn.execute('PRAGMA table_info(submission_versions)')}
        assert 'review_checklist_json' in sv_cols
        conn.close()

    def test_versions_api_works_after_repair(self, mig_app):
        """补列后 versions API 正常返回（模拟服务器修复后的行为）"""
        import sqlite3
        app, db_uri = mig_app
        _run_alembic(app, db_uri, command.upgrade, '5f4e3d2c1b0a')
        db_path = db_uri.replace('sqlite:///', '')
        # 模拟服务器缺列状态
        conn = sqlite3.connect(db_path)
        conn.execute('ALTER TABLE submission_versions DROP COLUMN revision_requirements')
        conn.execute('ALTER TABLE submission_versions DROP COLUMN review_checklist_json')
        conn.commit()
        conn.close()
        # 新迁移修复
        _run_alembic(app, db_uri, command.upgrade, 'head')

        from models import db, Customer, Inspection, SubmissionVersion
        with app.app_context():
            c = Customer(name='迁移客户')
            db.session.add(c)
            db.session.flush()
            i = Inspection(title='迁移巡检', customer_id=c.id, review_status='待审核')
            db.session.add(i)
            db.session.flush()
            v = SubmissionVersion(entity_type='inspection', entity_id=i.id,
                                  version_no=1, review_status='待审核')
            db.session.add(v)
            db.session.commit()
            iid = i.id
        client = app.test_client()
        from tests.conftest import login
        with app.app_context():
            from models import User
            if not User.query.filter_by(username='admin').first():
                from utils.seed_permissions import seed_all
                seed_all()
                db.session.add(User.create_with_password(
                    username='admin', password='x', realname='admin', role='admin'))
                db.session.commit()
        login(client, 'admin', 'x')
        r = client.get(f'/api/inspections/{iid}/versions')
        assert r.status_code == 200, r.get_json()
        data = r.get_json()['data']
        assert len(data) == 1
        assert data[0]['version_no'] == 1
        assert data[0]['checklist'] == {}  # 旧数据无勾选 → 空字典
        assert data[0]['assets'] == []
