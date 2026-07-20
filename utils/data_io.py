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
from sqlalchemy.types import Integer, BigInteger
from models import db


# 需要打包进导出包的文件目录（相对应用根）：（zip 内目录名, 磁盘相对路径）
FILE_DIRS = [
    ('files/reports', 'reports'),
    ('files/uploads', 'uploads'),
    ('files/static_uploads', os.path.join('static', 'uploads')),
]

SECRET_KEY_FILE = '.secret.key'   # AES 密钥（crypto.KEY_FILE 指向它）
BACKUP_FORMAT_VERSION = 1

# ---- 备份包密码保护（可选）：PBKDF2 派生密钥 + Fernet 整包加密，magic 头识别 ----
_BACKUP_MAGIC = b'ITSMBAK1'
_PBKDF2_ITERATIONS = 480_000


def _fernet_for_password(password, salt):
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=_PBKDF2_ITERATIONS)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(password.encode('utf-8'))))


def _encrypt_file_inplace(path, password):
    """把 zip 文件整体加密为 <magic><salt><fernet_token>（原地替换）"""
    salt = os.urandom(16)
    f = _fernet_for_password(password, salt)
    with open(path, 'rb') as fh:
        data = fh.read()
    with open(path, 'wb') as fh:
        fh.write(_BACKUP_MAGIC + salt + f.encrypt(data))


def is_encrypted_backup(path):
    """判断备份包是否带密码保护（magic 头探测）"""
    try:
        with open(path, 'rb') as fh:
            return fh.read(8) == _BACKUP_MAGIC
    except OSError:
        return False


def _decrypt_backup_to_temp(path, password):
    """加密备份包 → 解密出 zip 临时文件；密码错误/损坏抛 ValueError"""
    with open(path, 'rb') as fh:
        blob = fh.read()
    salt, token = blob[8:24], blob[24:]
    f = _fernet_for_password(password or '', salt)
    try:
        data = f.decrypt(token)
    except Exception:
        raise ValueError('备份包密码错误或文件已损坏')
    fd, tmp = tempfile.mkstemp(suffix='.zip', prefix='itsm_dec_')
    with os.fdopen(fd, 'wb') as fh:
        fh.write(data)
    return tmp

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


def _current_alembic_version():
    """读 alembic_version 表当前 head；表不存在或查不到返回 None（兼容裸库/SQLite 本地开发）。"""
    try:
        row = db.session.execute(text('SELECT version_num FROM alembic_version')).first()
        return row[0] if row else None
    except Exception:
        return None


def build_export_zip(config_only=False, password=None):
    """构建导出 zip；password 非空时整包加密（magic 头 + PBKDF2 + Fernet）"""
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
        'alembic_version': _current_alembic_version(),
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

    # === SHA256 设计 ===
    # 注意：manifest.json 自身**不**参与 SHA 计算（鸡生蛋问题：manifest 里要带 sha256
    # 字段，但写之前 sha 已经决定）。校验范围 = data.json + secret.key + files/*
    # （按 archive 内路径字典序，保证导出/导入端可重现）。
    sha = hashlib.sha256()

    data_bytes = json.dumps(data, ensure_ascii=False, default=_json_default).encode('utf-8')
    sha.update(data_bytes)

    key_path = os.path.join(root, SECRET_KEY_FILE)
    secret_bytes = None
    if os.path.exists(key_path):
        with open(key_path, 'rb') as kf:
            secret_bytes = kf.read()
        sha.update(secret_bytes)

    # 收集要打包的文件，排序保证 SHA 可重现
    file_entries = []  # [(arcname, disk_path)]
    if not config_only:
        for zip_sub, disk_rel in FILE_DIRS:
            disk_abs = os.path.join(root, disk_rel)
            if not os.path.isdir(disk_abs):
                continue
            for dirpath, _dirs, files in os.walk(disk_abs):
                for fn in files:
                    full = os.path.join(dirpath, fn)
                    arc = os.path.join(zip_sub, os.path.relpath(full, disk_abs)).replace('\\', '/')
                    file_entries.append((arc, full))
    file_entries.sort(key=lambda x: x[0])
    for arc, full in file_entries:
        with open(full, 'rb') as fh:
            sha.update(fh.read())

    manifest['sha256'] = sha.hexdigest()

    # 写一次到位（manifest 最后写，但 zip 顺序不影响校验，因为校验排除 manifest 本身）
    try:
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('manifest.json',
                        json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr('data.json', data_bytes)
            if secret_bytes is not None:
                zf.writestr('secret.key', secret_bytes)
            for arc, full in file_entries:
                zf.write(full, arc)
        size = os.path.getsize(tmp_path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

    if password:
        _encrypt_file_inplace(tmp_path, password)
        size = os.path.getsize(tmp_path)

    return tmp_path, size, manifest


def _model_for_table(tname):
    """表名 → ORM 模型类"""
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if cls.__table__.name == tname and issubclass(cls, db.Model):
            return cls
    return None


def _reset_pg_sequences(ordered_tables):
    """PG 导入后重置自增序列：显式 id 回灌不推进序列，须 setval 到 MAX(id) 否则后续插入主键冲突。

    通过 information_schema 读各表主键列的 DEFAULT（形如 nextval('seq_name'::regclass)），
    解析出序列名后 setval。跳过：无主键、复合主键、非整型主键、无序列默认的列。
    返回 warnings 列表（单个表失败仅告警不中断整体导入）。
    """
    warnings = []
    for tname in ordered_tables:
        tbl = db.Model.metadata.tables.get(tname)
        if tbl is None:
            continue
        pk_cols = list(tbl.primary_key.columns)
        if len(pk_cols) != 1:
            continue
        pk = pk_cols[0]
        # 仅处理整型自增主键
        if not isinstance(pk.type, (Integer, BigInteger)):
            continue
        try:
            # 查该列的默认值表达式（nextval('seq'::regclass)）
            row = db.session.execute(text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c AND column_default LIKE 'nextval%'"
            ), {'t': tname, 'c': pk.name}).first()
            if not row or not row[0]:
                continue  # 该列无序列默认（如关联表复合主键的整型列），跳过
            default_expr = row[0]
            # 解析 nextval('seq_name'::regclass) 中的序列名
            import re as _re
            m = _re.search(r"nextval\('([^']+)'", default_expr)
            if not m:
                continue
            seq_name = m.group(1)
            db.session.execute(text(
                f"SELECT setval('{seq_name}', COALESCE("
                f"(SELECT MAX({pk.name}) FROM {tname}), 1), true)"
            ))
        except Exception as e:
            warnings.append(f'重置 {tname}.{pk.name} 序列失败（非致命）: {e}')
    return warnings


def perform_import(zip_path, restore_secret_key=False, password=None):
    """导入备份包；带密码保护的包需先解密（password 错误抛 ValueError）。

    注意：解密出的临时 zip 在用完后由本函数负责清理。
    """
    _dec_tmp = None
    if is_encrypted_backup(zip_path):
        if not password:
            raise ValueError('该备份包已加密，请提供密码')
        _dec_tmp = _decrypt_backup_to_temp(zip_path, password)
        zip_path = _dec_tmp
    try:
        return _perform_import_inner(zip_path, restore_secret_key)
    finally:
        if _dec_tmp:
            try:
                os.remove(_dec_tmp)
            except OSError:
                pass


def _perform_import_inner(zip_path, restore_secret_key=False):
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
    # 校验范围与导出端一致：data.json + secret.key + files/*（archive 名字典序），
    # 不含 manifest.json 自身（manifest 里要带 sha256 字段，自引用算不出来）。
    expected_sha = manifest.get('sha256')
    if expected_sha:
        sha = hashlib.sha256()
        for member in ('data.json', 'secret.key'):
            if member in names:
                sha.update(zf.read(member))
        files_members = sorted(n for n in names
                               if n.startswith('files/') and not n.endswith('/'))
        for name in files_members:
            sha.update(zf.read(name))
        actual = sha.hexdigest()
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

    # alembic 版本提示（仅信息）：备份与当前库不同 head 时给警告
    bk_alembic = manifest.get('alembic_version')
    cur_alembic = _current_alembic_version()
    if bk_alembic and cur_alembic and bk_alembic != cur_alembic:
        warnings.append(
            f'备份包数据库版本 {bk_alembic} 与当前库 {cur_alembic} 不一致，'
            '导入后可能存在 schema 漂移，请关注上面的表/列差异提示'
        )

    is_sqlite = db.engine.dialect.name == 'sqlite'
    is_pg = db.engine.dialect.name == 'postgresql'

    # SQLite 回灌期间关外键，避免按拓扑序仍撞自引用/循环约束；结束后恢复
    if is_sqlite:
        db.session.execute(text('PRAGMA foreign_keys=OFF'))

    # PG：循环/自引用外键（如 departments.head_id↔users.department_id、
    # departments.parent_id、regions.parent_id）即使按拓扑序也会在插入中途违反约束；
    # 把所有约束推迟到事务末尾再校验，给回灌留出完整窗口。
    # 依赖迁移 e5f6a7b8c9d0_pg_deferrable_fks：把所有 FK 设为 DEFERRABLE INITIALLY DEFERRED
    # —— 否则 SET CONSTRAINTS ALL DEFERRED 对 NOT DEFERRABLE 的约束是空操作。
    if is_pg:
        db.session.execute(text('SET CONSTRAINTS ALL DEFERRED'))

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

        # === PG: 带入显式 id 后重置序列 ===
        # 显式 id 的 INSERT 不会推进 PG 自增序列；不重置则后续新插入会与回灌的主键冲突。
        if is_pg:
            seq_warnings = _reset_pg_sequences(ordered)
            warnings.extend(seq_warnings)

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
        if is_pg:
            # 恢复约束为立即校验（默认行为），避免影响后续正常写操作
            db.session.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))

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
