# -*- coding: utf-8 -*-
"""W0-S2 报告删除/下载加固验证：权限码 report:delete + realpath 防穿越"""

import pytest

from blueprints import ops


class TestSafeReportPath:
    def test_traversal_rejected(self, app, tmp_path):
        with app.app_context():
            assert ops._safe_report_path('../../etc/passwd.docx') is None
            assert ops._safe_report_path('..\\..\\x.docx') is None
            assert ops._safe_report_path('') is None

    def test_bad_extension_rejected(self, app):
        with app.app_context():
            assert ops._safe_report_path('evil.exe') is None
            assert ops._safe_report_path('x.txt') is None

    def test_missing_file_rejected(self, app):
        with app.app_context():
            assert ops._safe_report_path('not-exists.docx') is None

    def test_valid_file_accepted(self, app, tmp_path, monkeypatch):
        reports = tmp_path / 'reports'
        reports.mkdir()
        f = reports / '巡检报告_A.docx'
        f.write_bytes(b'dummy')
        monkeypatch.setattr(ops, 'REPORTS_DIR', str(reports))
        with app.app_context():
            got = ops._safe_report_path('巡检报告_A.docx')
            assert got is not None
            assert got.endswith('巡检报告_A.docx')


class TestReportDeletePermission:
    @pytest.fixture()
    def report_file(self, tmp_path, monkeypatch):
        reports = tmp_path / 'reports'
        reports.mkdir()
        f = reports / '测试报告.docx'
        f.write_bytes(b'dummy')
        monkeypatch.setattr(ops, 'REPORTS_DIR', str(reports))
        return f

    def test_viewer_cannot_delete(self, viewer_client, report_file):
        """viewer 只有 report:view，无 report:delete"""
        r = viewer_client.post('/reports/delete/测试报告.docx')
        assert r.status_code == 302  # 无权限重定向
        assert report_file.exists()  # 文件仍在

    def test_operator_deletes(self, op_client, report_file):
        r = op_client.post('/reports/delete/测试报告.docx')
        assert r.status_code == 302
        assert not report_file.exists()

    def test_traversal_delete_rejected(self, op_client, tmp_path, monkeypatch):
        reports = tmp_path / 'reports'
        reports.mkdir()
        monkeypatch.setattr(ops, 'REPORTS_DIR', str(reports))
        outside = tmp_path / 'secret.docx'
        outside.write_bytes(b'x')
        r = op_client.post('/reports/delete/..%2Fsecret.docx')
        assert r.status_code == 302
        assert outside.exists()  # 目录外文件未被删除


class TestReportDownload:
    def test_download_traversal_404(self, op_client, tmp_path, monkeypatch):
        reports = tmp_path / 'reports'
        reports.mkdir()
        monkeypatch.setattr(ops, 'REPORTS_DIR', str(reports))
        assert op_client.get('/reports/..%2Fsecret.docx').status_code == 404
