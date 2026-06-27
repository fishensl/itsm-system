"""customer parent_id

V19: 客户表新增 parent_id 列，用于手动指定上级单位。
- 空值 = 按 region+category 自动推导（市级单位 = 同类别同父市的县级单位的父）
- 非空 = 手动覆盖自动推导，强制把本客户挂到指定客户下

仅 add_column + 自引用 FK + 索引；无数据回填。

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def _existing_indexes(bind, table):
    insp = sa.inspect(bind)
    return {ix['name'] for ix in insp.get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'customers')
    is_sqlite = bind.dialect.name == 'sqlite'
    if 'parent_id' not in cols:
        if is_sqlite:
            # SQLite 上 batch_alter_table 会重建整张表，本表的 inspection_frequency
            # 自定义 default 字符串触发 "default value not constant"。
            # 直接 ADD COLUMN，FK 通过 PRAGMA foreign_keys（应用层已开）确保运行时校验。
            op.execute('ALTER TABLE customers ADD COLUMN parent_id INTEGER REFERENCES customers(id) ON DELETE SET NULL')
        else:
            op.add_column('customers',
                          sa.Column('parent_id', sa.Integer(), nullable=True))
            op.create_foreign_key(
                'fk_customers_parent_id', 'customers', 'customers',
                ['parent_id'], ['id'], ondelete='SET NULL',
            )
    if 'ix_customers_parent_id' not in _existing_indexes(bind, 'customers'):
        op.create_index('ix_customers_parent_id', 'customers', ['parent_id'])


def downgrade():
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    if 'ix_customers_parent_id' in _existing_indexes(bind, 'customers'):
        op.drop_index('ix_customers_parent_id', table_name='customers')
    if 'parent_id' in _existing_columns(bind, 'customers'):
        if is_sqlite:
            # SQLite 3.35+ 支持 DROP COLUMN，没有则跳过
            try:
                op.execute('ALTER TABLE customers DROP COLUMN parent_id')
            except Exception:
                pass
        else:
            try:
                op.drop_constraint('fk_customers_parent_id', 'customers', type_='foreignkey')
            except Exception:
                pass
            op.drop_column('customers', 'parent_id')
