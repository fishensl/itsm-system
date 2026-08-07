# -*- coding: utf-8 -*-
"""上传文件名清洗（保留中文原文件名）与上传校验"""

from utils.upload import _sanitize_filename, validate_upload


class _FakeFile:
    def __init__(self, filename, size=10):
        self.filename = filename
        self._size = size

    def seek(self, *a):
        return 0

    def tell(self):
        return self._size


class TestSanitizeFilename:
    def test_keep_chinese(self):
        """中文文件名保留（secure_filename 会丢中文，曾导致「巡检报告2026.docx」变「2026.docx」）"""
        assert _sanitize_filename('巡检报告2026.docx') == '巡检报告2026.docx'
        assert _sanitize_filename('现场巡检 报告.docx') == '现场巡检_报告.docx'  # 空格→下划线

    def test_ascii_unchanged(self):
        assert _sanitize_filename('report.docx') == 'report.docx'
        assert _sanitize_filename('SW-A_2026-08-01.pdf') == 'SW-A_2026-08-01.pdf'

    def test_illegal_chars_replaced(self):
        # 非法字符 " / \ | ? * 各替换为一个下划线
        assert _sanitize_filename('a<b>c:"/\\|?*.docx') == 'a_b_c_______.docx'
        # 路径穿越由 validate_upload 的 '..'/'.' 开头检查拦截（见 test_reject_traversal）

    def test_empty_fallback(self):
        assert _sanitize_filename('') == 'upload'
        assert _sanitize_filename('   ') == 'upload'

    def test_length_limit(self):
        long_name = '很' * 200 + '.docx'
        assert len(_sanitize_filename(long_name)) == 150


class TestValidateUpload:
    def test_valid_chinese_name(self):
        ok, err, name = validate_upload(_FakeFile('巡检报告2026.docx'), {'.docx'})
        assert ok is True
        assert name == '巡检报告2026.docx'

    def test_reject_traversal(self):
        ok, err, name = validate_upload(_FakeFile('../evil.docx'), {'.docx'})
        assert ok is False

    def test_reject_bad_ext(self):
        ok, err, name = validate_upload(_FakeFile('x.exe'), {'.docx'})
        assert ok is False

    def test_reject_oversize(self):
        ok, err, name = validate_upload(_FakeFile('big.docx', size=30 * 1024 * 1024), {'.docx'}, max_size_mb=20)
        assert ok is False
