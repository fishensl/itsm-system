# -*- coding: utf-8 -*-
"""Vue 导出共享实现（V24 导出筛选）

- 设备三预设列定义（资产表/密码表/安全版本管控表）+ 列解析与取值
- 一次性文件包：ExportFile + token 下载（send_file 后即删 + 创建人校验）
- 密码包：pyzipper AES 加密（下载时 X-Export-Password 响应头一次性下发）
"""
import os
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import joinedload

from domain_metadata import get_entity_schema
from models import db

# 一次性导出文件落盘目录（测试可 monkeypatch）
EXPORT_DIR = os.path.join('reports', 'exports')

# ============================ 设备列定义 ============================
# (code, 中文列名)；用户可自由增删/调序，列码是前后端唯一契约
# 代码仍沿用历史 export_key，避免破坏已有接口；标签等展示口径统一由注册中心维护。
DEVICE_EXPORT_COLUMNS = get_entity_schema('device').export_columns()
DEVICE_EXPORT_AVAILABLE_COLUMNS = get_entity_schema('device').export_columns('export_available')
DEVICE_EXPORT_COLUMN_MAP = dict(DEVICE_EXPORT_AVAILABLE_COLUMNS)

# 三类预设默认列集合（字段顺序按业务给定；用户可在此基础上增删）
DEVICE_PRESETS = get_entity_schema('device').export_preset_columns()
DEVICE_PRESET_LABELS = dict(get_entity_schema('device').export_preset_labels)


def resolve_device_columns(preset, columns):
    """列解析：preset 载入默认列集合；columns 显式覆盖（可增删/调序）。返回列码列表。"""
    if columns:
        cols = [str(c) for c in columns if str(c)]
        unknown = [c for c in cols if c not in DEVICE_EXPORT_COLUMN_MAP]
        if unknown:
            raise ValueError(f'未知导出列：{", ".join(unknown)}')
        return cols
    if preset and preset in DEVICE_PRESETS:
        return list(DEVICE_PRESETS[preset])
    raise ValueError('请选择导出项目或指定导出列')


def device_export_rows(devices, codes, customer_map=None, rack_map=None, pwd_map=None):
    """按列码生成行数据（password 列由调用方校验后放行）"""
    customer_map = customer_map or {}
    rack_map = rack_map or {}
    pwd_map = pwd_map or {}
    rows = []
    for d in devices:
        rows.append([_device_cell(d, code, customer_map, rack_map, pwd_map) for code in codes])
    return rows


def _device_cell(d, code, customer_map, rack_map, pwd_map):
    if code == 'customer':
        return customer_map.get(d.customer_id, '')
    if code == 'rack_location':
        return rack_map.get(d.id, ('', '', ''))[0]
    if code == 'rack_name':
        return rack_map.get(d.id, ('', '', ''))[1]
    if code == 'rack_slot':
        return rack_map.get(d.id, ('', '', ''))[2]
    if code == 'location':
        return d.location or ''
    if code == 'name':
        return d.device_name
    if code == 'type':
        return d.device_type or ''
    if code == 'brand':
        return d.brand or ''
    if code == 'model':
        return d.model or ''
    if code == 'sn':
        return d.serial_number or ''
    if code == 'network_type':
        return d.network_type or ''
    if code == 'ip':
        return d.ip_address or ''
    if code == 'port':
        return d.port if d.port is not None else ''
    if code == 'login_method':
        return d.login_method or ''
    if code == 'username':
        return d.username or ''
    if code == 'interface':
        from utils.json_fields import parse_json
        value = parse_json(d.interface or '', default=[], field_name='device.interface')
        return '、'.join(str(item) for item in value) if isinstance(value, list) else str(value or '')
    if code == 'password':
        from utils.crypto import decrypt_password
        return decrypt_password(d.password_encrypted) if d.password_encrypted else ''
    if code == 'build_date':
        return d.build_date.strftime('%Y-%m-%d') if d.build_date else ''
    if code == 'os_version':
        return d.os_version or ''
    if code == 'rule_version':
        return d.rule_version or ''
    if code == 'license_start':
        return d.license_start.strftime('%Y-%m-%d') if d.license_start else ''
    if code == 'license_expiry':
        return d.license_expiry.strftime('%Y-%m-%d') if d.license_expiry else ''
    if code == 'cert_expiry_date':
        return d.cert_expiry_date.strftime('%Y-%m-%d') if d.cert_expiry_date else ''
    if code == 'is_maintenance':
        return '是' if d.is_maintenance else '否'
    if code == 'is_in_use':
        return '是' if d.is_in_use else '否'
    if code == 'pwd_changed_by':
        return pwd_map.get(d.id, ('', ''))[0]
    if code == 'pwd_changed_at':
        return pwd_map.get(d.id, ('', ''))[1]
    if code == 'remark':
        return d.remark or ''
    if code == 'created_at':
        return d.created_at.strftime('%Y-%m-%d %H:%M') if d.created_at else ''
    return ''


def build_rack_map(devices):
    """每设备最近一次上架记录 → (Rack.location, Rack.name, 'U{start_u}')（防 N+1）。

    未上架设备返回设备自身 rack_location（批量修改可写入），机柜/机柜号为空。
    """
    rack_map = {}
    for d in devices:
        installs = d.rack_installs or []
        if not installs:
            rack_map[d.id] = ((d.rack_location or ''), '', '')
            continue
        inst = max(installs, key=lambda x: x.id or 0)
        r = inst.rack_rel
        rack_map[d.id] = (
            (r.location or '') if r else '',
            (r.name or '') if r else '',
            f'U{inst.start_u}' if inst.start_u else '',
        )
    return rack_map


def build_pwd_map(devices):
    """每设备最新 PasswordHistory → (changed_by, created_at)（防 N+1）"""
    from sqlalchemy import func
    from models import PasswordHistory
    ids = [d.id for d in devices if d.id]
    if not ids:
        return {}
    sub = (db.session.query(func.max(PasswordHistory.id))
           .filter(PasswordHistory.device_id.in_(ids))
           .group_by(PasswordHistory.device_id).scalar_subquery())
    rows = PasswordHistory.query.filter(PasswordHistory.id.in_(sub)).all()
    return {h.device_id: (
        h.changed_by or '',
        h.created_at.strftime('%Y-%m-%d') if h.created_at else '',
    ) for h in rows}


# ============================ 巡检 / 工单 / 故障 / 备件列定义 ============================
INSPECTION_EXPORT_COLUMNS = get_entity_schema('inspection').export_columns()

TICKET_EXPORT_COLUMNS = get_entity_schema('ticket').export_columns()
TICKET_EXPORT_AVAILABLE_COLUMNS = get_entity_schema('ticket').export_columns('export_available')

FAULT_EXPORT_COLUMNS = get_entity_schema('fault').export_columns()
FAULT_EXPORT_AVAILABLE_COLUMNS = get_entity_schema('fault').export_columns('export_available')

SPARE_EXPORT_COLUMNS = get_entity_schema('spare').export_columns()

CUSTOMER_EXPORT_COLUMNS = get_entity_schema('customer').export_columns('export_available')

BUNDLE_ITEM_LABELS = {
    'report': '现场报告',
    'formal_report': '正式报告',
    'config_zip': '完整配置备份包',
    'config_text': '核心设备文本配置',
    'topology': '拓扑图',
    'asset_list': '资产清单',
}


def resolve_columns(col_defs, columns):
    """通用列解析：columns 显式给定或返回全部默认列。"""
    col_map = dict(col_defs)
    if columns:
        cols = [str(c) for c in columns if str(c)]
        unknown = [c for c in cols if c not in col_map]
        if unknown:
            raise ValueError(f'未知导出列：{", ".join(unknown)}')
        return cols
    return [c for c, _ in col_defs]


def generic_rows(records, codes, cell_fn):
    """通用行生成：cell_fn(record, code) -> 单元格值"""
    return [[cell_fn(r, code) for code in codes] for r in records]


def _safe_name(name):
    """文件名安全化（客户名/标题可能含路径非法字符）"""
    import re
    return re.sub(r'[\\/:*?"<>|\r\n\t]', '_', str(name or '')).strip() or '_'


def device_export_filename(customer_name='', preset=''):
    """设备导出文件名：{客户}_{表格类型}_{日期}.xlsx；未选客户则 {表格类型}_{日期}.xlsx。

    表格类型取所选预设（设备资产表/设备密码表/网络安全版本控制表），未选预设兜底「设备导出」。
    """
    from datetime import date
    type_label = DEVICE_PRESET_LABELS.get(preset) or '设备导出'
    base = f'{_safe_name(customer_name)}_{type_label}' if customer_name else type_label
    return f'{base}_{date.today().isoformat()}.xlsx'


# ============================ 巡检 / 工单 资料包（bundle） ============================
def _latest_versions(entity_type, entity_ids):
    """批量取每实体最新提交版本（一次查询，joinedload assets，内存去重）"""
    from models import SubmissionVersion
    if not entity_ids:
        return {}
    rows = (SubmissionVersion.query
            .options(joinedload(SubmissionVersion.assets))
            .filter(SubmissionVersion.entity_type == entity_type,
                    SubmissionVersion.entity_id.in_(entity_ids))
            .order_by(SubmissionVersion.entity_id, SubmissionVersion.version_no.desc())
            .all())
    out = {}
    for v in rows:
        out.setdefault(v.entity_id, v)
    return out


def _collect_bundle_files(entity_type, entities, items, entity_title_fn):
    """按勾选项目收集文件列表。

    :param entities: 实体对象列表（Inspection/Ticket）
    :param items: 勾选项（BUNDLE_ITEM_LABELS 的 key 子集）
    :param entity_title_fn: (entity, version) -> (目录名, 是否有效)
    :return: [(完整路径, zip 内相对路径)]
    """
    versions = _latest_versions(entity_type, [e.id for e in entities])
    files = []
    for e in entities:
        v = versions.get(e.id)
        folder, ok = entity_title_fn(e, v)
        if not ok:
            continue
        assets = v.assets if v else []
        for a in assets:
            if a.asset_type not in items or not a.file_path:
                continue
            full = os.path.join('static', a.file_path.replace('/', os.sep))
            arc = f'{folder}/{BUNDLE_ITEM_LABELS.get(a.asset_type, a.asset_type)}/{a.file_name or os.path.basename(a.file_path)}'
            files.append((full, arc))
        # config_text 特例：content_text 无文件时写 .txt
        if 'config_text' in items:
            for a in assets:
                if a.asset_type == 'config_text' and not a.file_path and a.content_text:
                    txt_path = _write_content_txt(a)
                    if txt_path:
                        fname = a.file_name or f'config_{a.id}.txt'
                        files.append((txt_path, f'{folder}/核心设备文本配置/{fname}'))
    return files


def _write_content_txt(asset):
    """config_text 的 content_text → 临时 .txt 文件"""
    import tempfile
    try:
        fd, path = tempfile.mkstemp(suffix='.txt', prefix='cfgtext_')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(asset.content_text or '')
        return path
    except OSError:
        return None


def build_records_bundle(excel_path, files, zip_name='资料包'):
    """打包明细 Excel + 文件列表为 zip（复用 utils.report_zip.build_records_zip）。"""
    from utils.report_zip import build_records_zip
    return build_records_zip(excel_path, files, zip_name)


# ============================ 一次性文件包 ============================
def save_export_file(tmp_path, download_name, password=None, user_id=None, ttl_hours=24):
    """临时文件 → reports/exports/{token}.zip + ExportFile 登记。

    password 非空时用 pyzipper（AES-256）加密重打包，zip 密码 Fernet 入库，
    下载时经 X-Export-Password 一次性下发。返回 token。
    """
    from models import ExportFile
    from utils.crypto import encrypt_password as _ep
    token = uuid.uuid4().hex
    os.makedirs(EXPORT_DIR, exist_ok=True)
    final_path = os.path.join(EXPORT_DIR, f'{token}.zip')
    file_password_encrypted = ''
    if password:
        import pyzipper
        with pyzipper.AESZipFile(
                final_path, 'w',
                compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(password.encode())
            zf.write(tmp_path, arcname=os.path.basename(download_name) or 'export.xlsx')
        file_password_encrypted = _ep(password)
    else:
        import shutil
        shutil.move(tmp_path, final_path)
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    f = ExportFile(
        token=token,
        file_path=final_path.replace(os.sep, '/'),
        download_name=download_name or 'export.zip',
        created_by_user_id=user_id,
        file_password_encrypted=file_password_encrypted,
        expires_at=datetime.utcnow() + timedelta(hours=ttl_hours),
    )
    db.session.add(f)
    db.session.commit()
    return token


def serve_export_file(token, user_id, is_admin):
    """一次性下载：创建人/admin 校验 → send_file + X-Export-Password → 标记已下载 → 事后删文件。

    不可用/已下载/过期/无权限时返回 None（调用方回 404）。
    """
    from flask import send_file
    from models import ExportFile
    from utils.crypto import decrypt_password
    f = ExportFile.query.filter_by(token=token).first()
    if not f or f.downloaded_at:
        return None
    if f.expires_at and f.expires_at < datetime.utcnow():
        return None
    if not is_admin and f.created_by_user_id != user_id:
        return None
    full = os.path.realpath(f.file_path)
    if not os.path.isfile(full):
        return None
    f.downloaded_at = datetime.utcnow()
    db.session.commit()
    resp = send_file(full, as_attachment=True, download_name=f.download_name or 'export.zip')
    if f.file_password_encrypted:
        resp.headers['X-Export-Password'] = decrypt_password(f.file_password_encrypted)

    @resp.call_on_close
    def _cleanup():
        try:
            os.remove(full)
        except OSError:
            pass
    return resp
