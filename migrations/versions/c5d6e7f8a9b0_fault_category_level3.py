"""fault types 三级分级 + faults.fault_category_level3

- fault_types.parent_id: 自引用外键（NULL=一级），二级/三级通过 parent_id 挂载
- fault_types.level: 1/2/3 层级
- faults.fault_category_level3: 三级分类（对齐已有 level1/level2）

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5d6e7f8a9b0'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def _existing_indexes(bind, table):
    insp = sa.inspect(bind)
    return {i['name'] for i in insp.get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'fault_types')
    with op.batch_alter_table('fault_types', schema=None) as batch_op:
        if 'parent_id' not in cols:
            batch_op.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
        if 'level' not in cols:
            batch_op.add_column(sa.Column('level', sa.Integer(), nullable=True,
                                          server_default='1'))
    # 自引用外键（SQLite/PG 均幂等：已存在则跳过）
    idxs = _existing_indexes(bind, 'fault_types')
    if 'ix_fault_types_parent_id' not in idxs:
        op.create_index('ix_fault_types_parent_id', 'fault_types', ['parent_id'],
                        unique=False)
    # 先查 FK 是否已存在（PG information_schema / SQLite PRAGMA）
    fk_exists = False
    if bind.dialect.name == 'sqlite':
        rows = bind.execute(sa.text('PRAGMA foreign_key_list(fault_types)')).fetchall()
        fk_exists = any(r[2] == 'fault_types' for r in rows)
    else:
        rows = bind.execute(sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name='fault_types' AND constraint_type='FOREIGN KEY'")).fetchall()
        fk_exists = bool(rows)
    if not fk_exists:
        op.create_foreign_key('fk_fault_types_parent_id', 'fault_types', 'fault_types',
                              ['parent_id'], ['id'], ondelete='SET NULL')

    fcols = _existing_columns(bind, 'faults')
    if 'fault_category_level3' not in fcols:
        with op.batch_alter_table('faults', schema=None) as batch_op:
            batch_op.add_column(sa.Column('fault_category_level3', sa.String(length=64),
                                          nullable=True, server_default=''))


def downgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'faults')
    if 'fault_category_level3' in cols:
        with op.batch_alter_table('faults', schema=None) as batch_op:
            batch_op.drop_column('fault_category_level3')
    tcols = _existing_columns(bind, 'fault_types')
    with op.batch_alter_table('fault_types', schema=None) as batch_op:
        if 'parent_id' in tcols:
            batch_op.drop_column('parent_id')
        if 'level' in tcols:
            batch_op.drop_column('level')
