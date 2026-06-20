# -*- coding: utf-8 -*-
"""全局数据导出/导入核心（供 Web 蓝图与未来 CLI 共用）

导出包结构：
    manifest.json   # 版本/表计数/校验
    data.json       # 全量业务数据：{表名: [行, ...]}，按外键依赖排序
    secret.key      # AES 密钥副本（解密设备密码必需）
    files/          # reports/ + uploads/ + static/uploads/ 的文件副本

关键设计：
- 设备/AI 密码以 AES 密文存在 DB，导出时密文原样带出；导入端用同一把
  .secret.key 即可解密 → 所以导出包必须含密钥 → 导出/导入为高敏感操作。
- 导入按 db.metadata.sorted_tables 正序插入、反序清空，保留原始主键 id。
- date/datetime 转 ISO；bytes（如有）转 base64（在 manifest 标注）。
"""
import os
import json
import base64
import zipfile
import tempfile
import shutil
from datetime import datetime, date
from io import BytesIO

from flask import current_app
from sqlalchemy import inspect as sqla_inspect
from models import db


# 需要打包进导出包的文件目录（相对应用根）：（zip 内目录名, 磁盘相对路径）
FILE_DIRS = [
    ('files/reports', 'reports'),
    ('files/uploads', 'uploads'),
    ('files/static_uploads', os.path.join('static', 'uploads')),
]

SECRET_KEY_FILE = '.secret.key'   # AES 密钥（crypto.KEY_FILE 指向它）
BACKUP_FORMAT_VERSION = 1


def _app_root():
    return os.path.abspath(current_app.root_path)


def _json_default(o):
    """JSON 序列化兜底：date/datetime → ISO；bytes → base64 字符串"""
    if isinstance(o, (datetime, date)):
        return {'__iso__': o.isoformat()}
    if isinstance(o, (bytes, bytearray, memoryview)):
        return {'__b64__': base64.b64encode(bytes(o)).decode('ascii')}
    raise TypeError(f'不可序列化的类型: {type(o)}')


def _decode_value(v):
    """反序列化单个值：还原 ISO 日期/base64 bytes"""
    if isinstance(v, dict):
        if '__iso__' in v:
            s = v['__iso__']
            try:
                if 'T' in s:
                    return datetime.fromisoformat(s)
                return date.fromisoformat(s)
            except (ValueError, TypeError):
                return None
        if '__b64__' in v:
            try:
                return base64.b64decode(v['__b64__'])
            except Exception:
                return None
    return v


def _row_to_dict(obj):
    """ORM 行 → dict（只取映射到列的字段，忽略 relationship/动态属性）"""
    insp = sqla_inspect(obj)
    mapper = insp.mapper
    out = {}
    for col in mapper.columns:
        out[col.key] = getattr(obj, col.key)
    return out


def _table_names_in_order():
    """按外键依赖排序的表名（sorted_tables 自带拓扑序）"""
    return [t.name for t in db.metadata.sorted_tables]


def build_export_zip():
    """生成导出 zip 并返回 BytesIO（内存）+ 文件大小。

    对大包更稳妥的做法是落临时文件，这里 reports+uploads 约 35M，内存可接受。
    """
    buf = BytesIO()
    root = _app_root()
    table_counts = {}
    data = {}

    for tname in _table_names_in_order():
        model = _model_for_table(tname)
        if model is None:
            continue  # 无对应模型（纯关联表等跳过，数据多为可重建的关联）
        rows = [_row_to_dict(o) for o in db.session.query(model).all()]
        data[tname] = rows
        table_counts[tname] = len(rows)

    manifest = {
        'format_version': BACKUP_FORMAT_VERSION,
        'app_version': current_app.config.get('APP_VERSION', getattr(current_app, '_itsm_version', 'unknown')),
        'db_dialect': db.engine.dialect.name,
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'table_order': _table_names_in_order(),
        'table_counts': table_counts,
        'has_secret_key': os.path.exists(os.path.join(root, SECRET_KEY_FILE)),
    }

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr('data.json', json.dumps(data, ensure_ascii=False, default=_json_default))
        # 密钥
        key_path = os.path.join(root, SECRET_KEY_FILE)
        if os.path.exists(key_path):
            zf.write(key_path, 'secret.key')
        # 文件目录
        for zip_sub, disk_rel in FILE_DIRS:
            disk_abs = os.path.join(root, disk_rel)
            if not os.path.isdir(disk_abs):
                continue
            for dirpath, _dirs, files in os.walk(disk_abs):
                for fn in files:
                    full = os.path.join(dirpath, fn)
                    arc = os.path.relpath(full, disk_abs)
                    zf.write(full, os.path.join(zip_sub, arc))

    size = buf.tell()
    buf.seek(0)
    return buf, size, manifest


def _model_for_table(tname):
    """表名 → ORM 模型类"""
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if cls.__table__.name == tname and issubclass(cls, db.Model):
            return cls
    return None


def perform_import(zip_bytes, restore_secret_key=False):
    """导入 zip：清空并回灌全部表数据 + 还原文件 + 可选还原密钥。

    返回 dict 汇总：{restored_rows, restored_files, secret_key_restored, warnings}
    失败抛 ValueError（调用方事务已在 service 层或路由处理，这里不做 commit/rollback，
    实际写入由调用方包在一个事务里）。
    """
    root = _app_root()
    warnings = []
    restored_rows = 0
    restored_files = 0
    secret_key_restored = False

    bio = BytesIO(zip_bytes)
    try:
        zf = zipfile.ZipFile(bio)
    except zipfile.BadZipFile:
        raise ValueError('不是有效的 zip 备份包')

    names = zf.namelist()
    if 'manifest.json' not in names or 'data.json' not in names:
        raise ValueError('备份包缺少 manifest.json 或 data.json，可能已损坏')

    manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
    data = json.loads(zf.read('data.json').decode('utf-8'))

    # schema 漂移检查：对比当前表集合
    current_tables = set(_table_names_in_order())
    backup_tables = set(data.keys())
    missing = current_tables - backup_tables
    extra = backup_tables - current_tables
    if missing:
        warnings.append(f'当前库有、备份包无的表（将保持空）：{sorted(missing)}')
    if extra:
        warnings.append(f'备份包有、当前库无的表（将跳过）：{sorted(extra)}')

    # === 1. 数据回灌（单事务，由调用方决定 commit） ===
    # 反序清空 → 正序插入。用 db.session.execute 以纳入会话事务
    ordered = [t for t in _table_names_in_order() if t in data]
    for tname in reversed(ordered):
        db.session.execute(db.Model.metadata.tables[tname].delete())
    for tname in ordered:
        model = _model_for_table(tname)
        if model is None:
            warnings.append(f'表 {tname} 无对应模型，跳过')
            continue
        rows = data.get(tname, [])
        for row in rows:
            clean = {k: _decode_value(v) for k, v in row.items()}
            db.session.execute(model.__table__.insert().values(**clean))
            restored_rows += 1

    # === 2. 文件还原 ===
    for zip_sub, disk_rel in FILE_DIRS:
        prefix = zip_sub + '/'
        disk_abs = os.path.join(root, disk_rel)
        os.makedirs(disk_abs, exist_ok=True)
        for name in names:
            if name.startswith(prefix) and not name.endswith('/'):
                rel = name[len(prefix):]
                target = os.path.join(disk_abs, rel)
                # 防路径穿越
                if not os.path.abspath(target).startswith(os.path.abspath(disk_abs) + os.sep) \
                   and os.path.abspath(target) != os.path.abspath(disk_abs):
                    warnings.append(f'跳过可疑路径: {rel}')
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(name) as src, open(target, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                restored_files += 1

    # === 3. 密钥还原（可选） ===
    if restore_secret_key and 'secret.key' in names:
        key_path = os.path.join(root, SECRET_KEY_FILE)
        with zf.open('secret.key') as src, open(key_path, 'wb') as dst:
            shutil.copyfileobj(src, dst)
        secret_key_restored = True
        try:
            os.chmod(key_path, 0o600)
        except Exception:
            pass  # Windows 无效，忽略

    return {
        'manifest': manifest,
        'restored_rows': restored_rows,
        'restored_files': restored_files,
        'secret_key_restored': secret_key_restored,
        'warnings': warnings,
    }
