"""Temporary spreadsheet responses must remove generated files."""
import os

from utils.excel_export import export_xlsx, send_temp_export


def test_send_temp_export_cleans_file_on_close(app):
    with app.test_request_context('/'):
        path, name = export_xlsx(['列'], [['值']], 'test.xlsx')
        assert os.path.exists(path)
        response = send_temp_export(path, name)
        response.close()
        assert not os.path.exists(path)
