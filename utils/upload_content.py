"""Bounded file-structure checks. These checks are not antivirus or CDR."""
import io
import os
import re
import stat
import warnings
import zipfile
from pathlib import PurePosixPath

from defusedxml import ElementTree

TEXT_EXTENSIONS = {'.txt', '.cfg', '.conf', '.log', '.text', '.ini', '.json', '.yaml', '.yml'}
IMAGE_FORMATS = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.gif': 'GIF',
                 '.bmp': 'BMP', '.webp': 'WEBP'}
OFFICE_PARTS = {'.docx': 'word/document.xml', '.xlsx': 'xl/workbook.xml', '.vsdx': 'visio/document.xml'}
ARCHIVE_EXTENSIONS = TEXT_EXTENSIONS | set(IMAGE_FORMATS) | set(OFFICE_PARTS) | {'.pdf', '.xml', '.drawio'}
MAX_ARCHIVE_ENTRIES = 2000
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_XML_BYTES = 16 * 1024 * 1024


class UnsafeUpload(ValueError):
    pass


def _xml(data):
    if len(data) > MAX_XML_BYTES:
        raise UnsafeUpload('XML 内容过大')
    return ElementTree.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)


def _archive(stream, ext, budget):
    with zipfile.ZipFile(stream) as archive:
        entries = archive.infolist()
        if not entries or len(entries) > MAX_ARCHIVE_ENTRIES:
            raise UnsafeUpload('压缩包为空或文件数量超限')
        total = 0
        seen = set()
        for entry in entries:
            name = entry.filename.replace('\\', '/')
            parts = PurePosixPath(name).parts
            if (name.startswith('/') or ':' in name or '..' in parts or
                    '\x00' in name or name.casefold() in seen):
                raise UnsafeUpload('压缩包包含不安全或重复路径')
            seen.add(name.casefold())
            if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                raise UnsafeUpload('不支持符号链接或加密压缩包')
            total += entry.file_size
            if (total > budget or entry.file_size > MAX_MEMBER_BYTES or
                    (entry.file_size > 1024 * 1024 and
                     entry.file_size > max(1, entry.compress_size) * 200)):
                raise UnsafeUpload('压缩包展开大小或压缩比超限')
        names = {e.filename for e in entries}
        if ext in OFFICE_PARTS and not {'[Content_Types].xml', OFFICE_PARTS[ext]} <= names:
            raise UnsafeUpload('Office 文件结构与扩展名不符')
        for entry in entries:
            if entry.is_dir():
                continue
            name = entry.filename.replace('\\', '/').lower()
            member_ext = os.path.splitext(name)[1]
            if ext in OFFICE_PARTS:
                if ('vbaproject' in name or '/embeddings/' in name or '/activex/' in name or
                        '/externallinks/' in name or member_ext in {'.exe', '.dll', '.js', '.vbs'}):
                    raise UnsafeUpload('Office 文件包含宏、嵌入对象或外部数据链接')
            elif member_ext not in ARCHIVE_EXTENSIONS:
                raise UnsafeUpload('压缩包包含不允许的文件类型或嵌套压缩包')
            # read() validates CRC; the central-directory budget bounds memory use.
            data = archive.read(entry)
            if ext in OFFICE_PARTS:
                if member_ext in {'.xml', '.rels'}:
                    root = _xml(data)
                    if ext == '.xlsx' and name.startswith('xl/worksheets/'):
                        rows = [n for n in root.iter() if n.tag.rsplit('}', 1)[-1] == 'row']
                        if len(rows) > 5000:
                            raise UnsafeUpload('Excel 实际行数超过 5000')
                        for row in rows:
                            if int(row.attrib.get('r', '0')) > 5000 or len(row) > 256:
                                raise UnsafeUpload('Excel 行数或列数超限')
                    for node in root.iter():
                        values = ' '.join(node.attrib.values()).lower()
                        if 'macroenabled' in values or 'vbaproject' in values:
                            raise UnsafeUpload('不支持含宏的 Office 文件')
                        if (node.attrib.get('TargetMode', '').lower() == 'external' and
                                not node.attrib.get('Type', '').endswith('/hyperlink')):
                            raise UnsafeUpload('Office 文件包含外部资源关系')
                        if (ext == '.xlsx' and node.tag.rsplit('}', 1)[-1] == 'f'):
                            raise UnsafeUpload('资产/导入表不允许公式，请粘贴为值后上传')
                elif member_ext in IMAGE_FORMATS:
                    inspect_content(io.BytesIO(data), member_ext, budget)
            else:
                inspect_content(io.BytesIO(data), member_ext, budget)


def inspect_content(stream, ext, budget=128 * 1024 * 1024):
    """Validate a seekable stream, leaving it at the beginning even after failure."""
    try:
        stream.seek(0)
        head = stream.read(1024)
        stream.seek(0)
        if not head:
            raise UnsafeUpload('不能上传空文件')
        if ext in {'.doc', '.xls', '.vsd'}:
            raise UnsafeUpload('旧版二进制 Office 文件无法安全检查，请转换为 docx/xlsx/vsdx 或 PDF')
        if ext in OFFICE_PARTS or ext == '.zip':
            _archive(stream, ext, budget)
        elif ext in IMAGE_FORMATS:
            from PIL import Image
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(stream) as picture:
                    if picture.format != IMAGE_FORMATS[ext] or picture.width * picture.height > 25_000_000:
                        raise UnsafeUpload('图片格式不符或像素数量超限')
                    picture.verify()
        elif ext == '.pdf':
            if not head.startswith(b'%PDF-'):
                raise UnsafeUpload('PDF 文件签名不正确')
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 2048))
            if b'%%EOF' not in stream.read():
                raise UnsafeUpload('PDF 文件结构不完整')
            # Supplementary check only; compressed/obfuscated payloads need AV/CDR.
            stream.seek(0)
            tail = b''
            while chunk := stream.read(64 * 1024):
                data = tail + chunk
                if re.search(rb'/(JavaScript|JS|Launch|EmbeddedFile|OpenAction|AA)\b', data):
                    raise UnsafeUpload('PDF 包含活动内容或嵌入文件')
                tail = data[-64:]
        elif ext in {'.xml', '.drawio'}:
            _xml(stream.read(MAX_XML_BYTES + 1))
        elif ext in TEXT_EXTENSIONS:
            # Device configurations are inert text, never executable server content.
            if head.startswith((b'MZ', b'\x7fELF', b'PK\x03\x04')) or b'\x00' in head:
                raise UnsafeUpload('配置文件必须是文本，不能使用二进制或压缩文件伪装')
            tail = b''
            while chunk := stream.read(64 * 1024):
                if b'\x00' in chunk:
                    raise UnsafeUpload('文本文件包含二进制内容')
                data = (tail + chunk).lower()
                if any(marker in data for marker in (b'<?php', b'<script', b'<html', b'<!doctype html')):
                    raise UnsafeUpload('文本文件包含网页或脚本内容')
                tail = data[-32:]
        else:
            raise UnsafeUpload('没有适用于此文件类型的安全校验器')
    except UnsafeUpload:
        raise
    except Exception as exc:
        raise UnsafeUpload('文件内容损坏或与扩展名不符') from exc
    finally:
        stream.seek(0)
