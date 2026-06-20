"""pg_type_fixes

PG 类型兼容性修复（迁移前必做）：
  - devices.interface: VARCHAR(128) -> Text（该列存 JSON 数组，PG 严格校验长度会截断/报错）
  - customers.name: 加唯一约束（导入按名反查归属错乱、并发可重名）
  - tickets.number: 加唯一约束（工单号并发可重复）

Revision ID: cb9d639a430f
Revises: 3f82f965fb25
Create Date: 2026-06-20 11:58:17.841877

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cb9d639a430f'
down_revision = '3f82f965fb25'
branch_labels = None
depends_on = None


# 遗留 SQLite 库里 devices 表有几列由旧 ensure_schema 用 ADD COLUMN ... DEFAULT ""（双引号）
# 种入，dflt_value 被存成 '""'（SQLite 视为非常量）。Alembic batch 模式重建表时会把这些
# 默认值原样回放，触发 "default value of column [...] is not constant"。
# 这些列在模型里本就是普通可空列（默认空串），下面在反射 Table 后把它们的 server_default
# 清空，避免回放出非法默认。
_DEVICES_BAD_DEFAULT_COLS = (
    'location', 'license_expiry', 'is_maintenance', 'is_in_use',
    'network_type', 'serial_number', 'os_version', 'rule_version',
    'login_method', 'interface',
)


def _devices_table_for_batch(bind):
    """反射 devices 表用于 batch 重建，清理遗留非法 server_default。"""
    tbl = sa.Table('devices', sa.MetaData(), autoload_with=bind)
    for col in tbl.columns:
        if col.name in _DEVICES_BAD_DEFAULT_COLS:
            col.server_default = None
    return tbl


def _existing_index_unique(bind, table, index_name):
    """反射查表上某索引是否存在、是否唯一。返回 (exists: bool, unique: bool)。"""
    insp = sa.inspect(bind)
    try:
        for ix in insp.get_indexes(table):
            if ix.get('name') == index_name:
                return True, bool(ix.get('unique', False))
    except Exception:
        pass
    return False, False


def _ensure_unique_index(table, column, index_name):
    """确保表上存在指定唯一索引；已存在且唯一则跳过，存在但非唯一则先删后建，不存在则直接建。"""
    bind = op.get_bind()
    exists, unique = _existing_index_unique(bind, table, index_name)
    if exists and unique:
        return  # 已满足
    if exists and not unique:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(index_name)
            batch_op.create_index(index_name, [column], unique=True)
    else:
        op.create_index(index_name, table, [column], unique=True)


def _drop_unique_to_nonunique(table, column, index_name):
    """downgrade：把唯一索引降为非唯一；不存在则直接建非唯一（兼容遗留库本就无该索引）。"""
    bind = op.get_bind()
    exists, _unique = _existing_index_unique(bind, table, index_name)
    if not exists:
        op.create_index(index_name, table, [column], unique=False)
        return
    with op.batch_alter_table(table, schema=None) as batch_op:
        batch_op.drop_index(index_name)
        batch_op.create_index(index_name, [column], unique=False)


def upgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    # --- customers.name 唯一索引 ---
    _ensure_unique_index('customers', 'name', op.f('ix_customers_name'))

    # --- devices.interface: VARCHAR(128) -> Text ---
    # PG 原生支持 ALTER COLUMN TYPE，直接改；SQLite 需 batch 重建整表，
    # 用显式反射 Table 清理遗留非法默认，避免回放 '""' 触发 "not constant" 错误。
    if is_sqlite:
        with op.batch_alter_table('devices', schema=None,
                                  copy_from=_devices_table_for_batch(bind)) as batch_op:
            batch_op.alter_column('interface',
                   existing_type=sa.VARCHAR(length=128),
                   type_=sa.Text(),
                   existing_nullable=True)
    else:
        op.alter_column('devices', 'interface',
               existing_type=sa.VARCHAR(length=128),
               type_=sa.Text(),
               existing_nullable=True)

    # --- tickets.number 唯一索引 ---
    _ensure_unique_index('tickets', 'number', op.f('ix_tickets_number'))


def downgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    _drop_unique_to_nonunique('tickets', 'number', op.f('ix_tickets_number'))

    if is_sqlite:
        with op.batch_alter_table('devices', schema=None,
                                  copy_from=_devices_table_for_batch(bind)) as batch_op:
            batch_op.alter_column('interface',
                   existing_type=sa.Text(),
                   type_=sa.VARCHAR(length=128),
                   existing_nullable=True)
    else:
        op.alter_column('devices', 'interface',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(length=128),
               existing_nullable=True)

    _drop_unique_to_nonunique('customers', 'name', op.f('ix_customers_name'))
