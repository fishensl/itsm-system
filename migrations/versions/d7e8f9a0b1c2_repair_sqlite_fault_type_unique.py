"""修复已执行旧版 d6 迁移的 SQLite fault_types 全局唯一约束。

旧版 d6 在 SQLite 上直接跳过约束切换，导致已经升级到 head 的开发库仍保留
``UNIQUE(name)``，启动播种三级分类时无法插入不同父级下同名分类。本迁移
使用显式 copy_from 表定义重建 SQLite 表，只保留 ``(name, parent_id)`` 唯一。
PostgreSQL 已由 d6 完成切换，因此保持幂等空操作。
"""

from alembic import op
import sqlalchemy as sa


revision = 'd7e8f9a0b1c2'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def _copy_table():
    metadata = sa.MetaData()
    return sa.Table(
        'fault_types', metadata,
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('level', sa.Integer(), nullable=True, server_default='1'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['parent_id'], ['fault_types.id'],
            name='fk_fault_types_parent_id', ondelete='SET NULL'),
        sa.UniqueConstraint('name', 'parent_id', name='uq_fault_types_name_parent'),
    )


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'sqlite':
        return
    with op.batch_alter_table(
        'fault_types', schema=None, recreate='always', copy_from=_copy_table()
    ):
        pass
    indexes = {idx['name'] for idx in sa.inspect(bind).get_indexes('fault_types')}
    if 'ix_fault_types_parent_id' not in indexes:
        op.create_index('ix_fault_types_parent_id', 'fault_types', ['parent_id'])


def downgrade():
    # 不恢复会阻止三级分类播种的错误全局唯一约束。
    pass

