# -*- coding: utf-8 -*-
"""拓扑标准模板白名单、XML 校验和旧图显式图例升级。"""
from copy import deepcopy
from pathlib import Path
import re
from uuid import uuid4
from xml.etree import ElementTree as ET


TEMPLATE_VERSION = 1
TEMPLATE_FILES = {
    'network': 'standard-network-v1.drawio',
    'meeting': 'standard-meeting-v1.drawio',
}
MAX_TOPOLOGY_XML_BYTES = 5 * 1024 * 1024
_DANGEROUS_TEXT = re.compile(
    r'<!DOCTYPE|<!ENTITY|<\s*script\b|javascript\s*:|data\s*:\s*text/html', re.I)


def normalize_template_type(value, *, allow_legacy=True):
    value = str(value or '').strip().lower()
    allowed = set(TEMPLATE_FILES)
    if allow_legacy:
        allowed.add('legacy')
    if value not in allowed:
        raise ValueError('拓扑模板类型必须为 network、meeting 或 legacy')
    return value


def validate_topology_xml(xml):
    """拒绝超限、危险声明、事件属性和非 draw.io 根节点。"""
    if not isinstance(xml, str) or not xml.strip():
        raise ValueError('图内容为空')
    if len(xml.encode('utf-8')) > MAX_TOPOLOGY_XML_BYTES:
        raise ValueError('图内容超过 5 MB 限制')
    if _DANGEROUS_TEXT.search(xml):
        raise ValueError('图内容包含不安全的 XML/脚本内容')
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f'图内容不是有效 XML：{exc}') from exc
    tag = root.tag.rsplit('}', 1)[-1]
    if tag not in {'mxGraphModel', 'mxfile'}:
        raise ValueError('图内容根节点必须是 mxGraphModel 或 mxfile')
    for node in root.iter():
        for name, value in node.attrib.items():
            attr = name.rsplit('}', 1)[-1].lower()
            if attr.startswith('on') or _DANGEROUS_TEXT.search(str(value)):
                raise ValueError(f'图内容包含不安全属性：{name}')
    return root


def template_path(template_type):
    kind = normalize_template_type(template_type, allow_legacy=False)
    return Path(__file__).resolve().parents[1] / 'static' / 'templates' / TEMPLATE_FILES[kind]


def load_topology_template(template_type):
    path = template_path(template_type)
    xml = path.read_text(encoding='utf-8')
    validate_topology_xml(xml)
    return xml


def insert_standard_legend(xml, template_type):
    """把标准模板中的锁定图例层复制进旧 mxGraphModel；调用方显式保存。"""
    target = validate_topology_xml(xml)
    if target.tag.rsplit('}', 1)[-1] != 'mxGraphModel':
        raise ValueError('当前图为压缩 mxfile，需先在编辑器中保存为在线图后再插入图例')
    target_root = target.find('root')
    if target_root is None:
        raise ValueError('图内容缺少 root 节点')
    source = validate_topology_xml(load_topology_template(template_type))
    source_root = source.find('root')
    legend_layer = source_root.find("mxCell[@id='standard-legend']") if source_root is not None else None
    if legend_layer is None:
        raise ValueError('标准模板缺少图例层')
    prefix = 'legend-' + uuid4().hex[:10] + '-'
    children = [node for node in list(source_root) if
                node.get('id') == 'standard-legend' or node.get('parent') == 'standard-legend']
    id_map = {node.get('id'): prefix + str(node.get('id')) for node in children if node.get('id')}
    for node in children:
        clone = deepcopy(node)
        if clone.get('id') in id_map:
            clone.set('id', id_map[clone.get('id')])
        parent = clone.get('parent')
        if parent in id_map:
            clone.set('parent', id_map[parent])
        target_root.append(clone)
    return ET.tostring(target, encoding='unicode')
