import io
import stat
import zipfile

import pytest
from werkzeug.datastructures import FileStorage

from utils.upload import validate_upload


def check(data, filename):
    file = FileStorage(io.BytesIO(data), filename=filename)
    result = validate_upload(file, {'.xlsx', '.docx', '.pdf', '.zip', '.cfg', '.png', '.xml', '.doc'})
    assert file.tell() == 0
    return result


def archive(items, compression=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression) as z:
        for name, data in items:
            z.writestr(name, data)
    return buffer.getvalue()


@pytest.mark.parametrize('name,data', [
    ('a.docx', b'MZ binary'), ('a.pdf', b'<html>test</html>'),
    ('a.png', b'not a picture'), ('a.cfg', b'MZ executable'),
    ('a.cfg', b'<script>alert(1)</script>'), ('a.doc', b'legacy'),
    ('a.xml', b'<!DOCTYPE a [<!ENTITY x "test">]><a>&x;</a>'),
    ('a.pdf', b'%PDF-1.4 /JavaScript (test) %%EOF'),
])
def test_rejects_disguised_or_active_content(name, data):
    assert not check(data, name)[0]


@pytest.mark.parametrize('member', ['../config.cfg', '/config.cfg', 'C:/config.cfg', 'run.exe', 'nested.zip'])
def test_rejects_unsafe_archive_members(member):
    assert not check(archive([(member, b'data')]), 'config.zip')[0]


def test_rejects_zip_bomb_and_symlink():
    assert not check(archive([('config.cfg', b'A' * (2 * 1024 * 1024))]), 'config.zip')[0]
    link = zipfile.ZipInfo('link.cfg')
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    assert not check(archive([(link, b'../../secret')]), 'config.zip')[0]


def test_safe_config_archive_and_text_are_accepted():
    assert check(archive([('switch/core.cfg', b'hostname core\ninterface vlan 10')]), 'config.zip')[0]
    assert check(b'hostname core\ninterface vlan 10', 'config.cfg')[0]


def test_asset_workbook_rejects_formula_and_accepts_values():
    from openpyxl import Workbook
    workbook = Workbook()
    workbook.active.append(['名称', '备注'])
    workbook.active.append(['core', '=1+1'])
    buffer = io.BytesIO()
    workbook.save(buffer)
    assert not check(buffer.getvalue(), 'assets.xlsx')[0]
    workbook.active['B2'] = 'ordinary text'
    buffer = io.BytesIO()
    workbook.save(buffer)
    assert check(buffer.getvalue(), 'assets.xlsx')[0]


def test_rejects_macro_and_external_office_relationships():
    from docx import Document
    buffer = io.BytesIO()
    Document().save(buffer)
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as original:
        entries = [(name, original.read(name)) for name in original.namelist()]
    assert not check(archive(entries + [('word/vbaProject.bin', b'macro')]), 'report.docx')[0]
    relation = b'<Relationships><Relationship TargetMode="External" Type="template" Target="https://example.invalid"/></Relationships>'
    assert not check(archive(entries + [('word/_rels/evil.rels', relation)]), 'report.docx')[0]
