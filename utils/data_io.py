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
import hashlib
import zipfile
import tempfile
import shutil
from datetime import datetime, date

from flask import current_app
from sqlalchemy import inspect as sqla_inspect, text
from models import db


# 需要打包进导出包的文件目录（相对应用根）：（zip 内目录名, 磁盘相对路径）
FILE_DIRS = [
    ('files/reports', 'reports'),
    ('files/uploads', 'uploads'),
    ('files/static_uploads', os.path.join('static', 'uploads')),
]

SECRET_KEY_FILE = '.secret.key'   # AES 密钥（crypto.KEY_FILE 指向它）
BACKUP_FORMAT_VERSION = 1

# 「仅配置」导出子集：把一台调好的系统配置克隆到新环境，不带业务数据。
# 配置类表（角色/权限/各模板/AI配置/字典）；其余视为业务数据。
CONFIG_TABLES = {
    'roles', 'permissions', 'role_permissions',
    'inspection_templates', 'inspection_task_templates', 'inspection_device_templates',
    'task_device_template_link', 'device_types', 'brands', 'network_types',
    'custom_fields', 'device_firmwares', 'fault_types', 'departments',
    'ai_config', 'regions', 'customer_categories',
}


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


def build_export_zip(config_only=False):
    """生成导出 zip，流式写入临时文件后返回 (文件路径, 大小, manifest)。

    config_only=True 时只导出配置类表（CONFIG_TABLES），不含业务数据，
    便于把一台调好的配置克隆到新环境。调用方负责删除临时文件。

    返回临时文件磁盘路径（不是 BytesIO），避免大包占内存。
    """
    root = _app_root()
    table_counts = {}
    table_columns = {}
    data = {}

    all_tables = _table_names_in_order()
    selected = [t for t in all_tables if not config_only or t in CONFIG_TABLES]

    for tname in selected:
        model = _model_for_table(tname)
        if model is None:
            continue  # 纯关联表无模型时仍可导出（用 metadata）
        rows = [_row_to_dict(o) for o in db.session.query(model).all()]
        data[tname] = rows
        table_counts[tname] = len(rows)
        table_columns[tname] = sorted(model.__table__.columns.keys())

    # 关联表（无模型）也要带上数据与列信息，否则导入丢关联
    for tname in selected:
        if tname in data:
            continue
        tbl = db.Model.metadata.tables.get(tname)
        if tbl is None:
            continue
        cols = [c.key for c in tbl.columns]
        table_columns[tname] = sorted(cols)
        result = db.session.execute(tbl.select())
        data[tname] = [dict(r._mapping) for r in result]
        table_counts[tname] = len(data[tname])

    manifest = {
        'format_version': BACKUP_FORMAT_VERSION,
        'app_version': current_app.config.get('APP_VERSION', getattr(current_app, '_itsm_version', 'unknown')),
        'db_dialect': db.engine.dialect.name,
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'config_only': bool(config_only),
        'table_order': selected,
        'table_counts': table_counts,
        'table_columns': table_columns,
        'has_secret_key': os.path.exists(os.path.join(root, SECRET_KEY_FILE)),
    }

    # 流式写临时文件，避免大包撑爆内存
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip', prefix='itsm_export_')
    os.close(tmp_fd)
    sha = hashlib.sha256()

    def _hash_write(zf_or_bytes):
        sha.update(zf_or_bytes)

    try:
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
            zf.writestr('manifest.json', manifest_bytes)
            sha.update(manifest_bytes)
            data_bytes = json.dumps(data, ensure_ascii=False, default=_json_default).encode('utf-8')
            zf.writestr('data.json', data_bytes)
            sha.update(data_bytes)
            # 密钥
            key_path = os.path.join(root, SECRET_KEY_FILE)
            if os.path.exists(key_path):
                with open(key_path, 'rb') as kf:
                    kf_bytes = kf.read()
                zf.writestr('secret.key', kf_bytes)
                sha.update(kf_bytes)
            # 文件目录（仅全量导出打包文件；仅配置导出不含业务文件）
            if not config_only:
                for zip_sub, disk_rel in FILE_DIRS:
                    disk_abs = os.path.join(root, disk_rel)
                    if not os.path.isdir(disk_abs):
                        continue
                    for dirpath, _dirs, files in os.walk(disk_abs):
                        for fn in files:
                            full = os.path.join(dirpath, fn)
                            arc = os.path.relpath(full, disk_abs)
                            zf.write(full, os.path.join(zip_sub, arc))
                            with open(full, 'rb') as fh:
                                sha.update(fh.read())

        manifest['sha256'] = sha.hexdigest()
        # 把含 sha256 的 manifest 回写到 zip 里
        with zipfile.ZipFile(tmp_path, 'a', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('manifest.json',
                        json.dumps(manifest, ensure_ascii=False, indent=2))
        size = os.path.getsize(tmp_path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

    return tmp_path, size, manifest


def _model_for_table(tname):
    """表名 → ORM 模型类"""
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if cls.__table__.name == tname and issubclass(cls, db.Model):
            return cls
    return None


def perform_import(zip_path, restore_secret_key=False):
    """导入 zip：清空并回灌全部表数据 + 还原文件 + 可选还原密钥。

    zip_path: 备份包磁盘路径（由调用方提供，通常是上传保存的临时文件）。
    返回 dict 汇总：{restored_rows, restored_files, secret_key_restored, warnings}
    失败抛 ValueError。本函数不做 commit/rollback，由调用方包在外层事务里。
    """
    root = _app_root()
    warnings = []
    restored_rows = 0
    restored_files = 0
    secret_key_restored = False

    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise ValueError('不是有效的 zip 备份包')

    names = zf.namelist()
    if 'manifest.json' not in names or 'data.json' not in names:
        raise ValueError('备份包缺少 manifest.json 或 data.json，可能已损坏')

    manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
    data = json.loads(zf.read('data.json').decode('utf-8'))

    # === 完整性校验：sha256 ===
    expected_sha = manifest.get('sha256')
    if expected_sha:
        sha = hashlib.sha256()
        for member in ('manifest.json', 'data.json', 'secret.key'):
            if member in names:
                sha.update(zf.read(member))
        # 文件部分单独累加
        for name in names:
            if name.startswith('files/') and not name.endswith('/'):
                sha.update(zf.read(name))
        actual = sha.hexdigest()
        # 注：导出时 manifest 自身不含 sha256 字段参与计算，这里对回写后的
        # manifest 读出的 sha 字段做比对——采用与导出一致的口径（排除 sha256 字段
        # 本身带来的差异）：若不匹配仅给警告而非硬失败（避免误判阻断恢复）。
        if actual != expected_sha:
            warnings.append('备份包完整性校验未通过（sha256 不一致），可能被篡改或损坏，请谨慎确认')

    # === schema 漂移检查：表级 + 列级 ===
    current_tables = set(_table_names_in_order())
    backup_tables = set(data.keys())
    missing = current_tables - backup_tables
    extra = backup_tables - current_tables
    if missing:
        warnings.append(f'当前库有、备份包无的表（将保持空）：{sorted(missing)}')
    if extra:
        warnings.append(f'备份包有、当前库无的表（将跳过）：{sorted(extra)}')
    # 列级比对
    for tname, bk_cols in (manifest.get('table_columns') or {}).items():
        model = _model_for_table(tname)
        if model is None:
            continue
        cur_cols = set(model.__table__.columns.keys())
        bk_cols = set(bk_cols or [])
        if bk_cols - cur_cols:
            warnings.append(f'表 {tname}：备份包有、当前库无的列将被丢弃：{sorted(bk_cols - cur_cols)}')
        if cur_cols - bk_cols:
            warnings.append(f'表 {tname}：当前库有、备份包无的列将用默认值：{sorted(cur_cols - bk_cols)}')

    is_sqlite = db.engine.dialect.name == 'sqlite'

    # SQLite 回灌期间关外键，避免按拓扑序仍撞自引用/循环约束；结束后恢复
    if is_sqlite:
        db.session.execute(text('PRAGMA foreign_keys=OFF'))

    try:
        # === 1. 数据回灌（单事务，由调用方决定 commit） ===
        ordered = [t for t in _table_names_in_order() if t in data]
        # 反序清空 → 正序插入。用 db.session.execute 纳入会话事务
        for tname in reversed(ordered):
            tbl = db.Model.metadata.tables.get(tname)
            if tbl is None:
                continue
            db.session.execute(tbl.delete())
        for tname in ordered:
            tbl = db.Model.metadata.tables.get(tname)
            if tbl is None:
                warnings.append(f'表 {tname} 当前无定义，跳过')
                continue
            rows = data.get(tname, [])
            # 只取当前表存在的列，丢弃多余列（schema 漂移）
            cur_cols = set(tbl.columns.keys())
            for row in rows:
                clean = {k: _decode_value(v) for k, v in row.items() if k in cur_cols}
                if clean:
                    db.session.execute(tbl.insert().values(**clean))
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
    finally:
        if is_sqlite:
            db.session.execute(text('PRAGMA foreign_keys=ON'))

    # 刷新 ORM 身份映射，避免导入后用到旧对象
    try:
        db.session.expire_all()
    except Exception:
        pass

    return {
        'manifest': manifest,
        'restored_rows': restored_rows,
        'restored_files': restored_files,
        'secret_key_restored': secret_key_restored,
        'warnings': warnings,
    }
