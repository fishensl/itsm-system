"""inspection_tasks estimated_effort

V19: 任务安排增加"预估工作量"（单位：人天，Float，nullable）。
仅给 inspection_tasks 表新增一列 estimated_effort，老数据保持 NULL（未设置）。

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    if 'estimated_effort' not in _existing_columns(bind, 'inspection_tasks'):
        with op.batch_alter_table('inspection_tasks', schema=None) as batch_op:
            batch_op.add_column(sa.Column('estimated_effort', sa.Float(), nullable=True))


def downgrade():
    bind = op.get_bind()
    if 'estimated_effort' in _existing_columns(bind, 'inspection_tasks'):
        with op.batch_alter_table('inspection_tasks', schema=None) as batch_op:
            batch_op.drop_column('estimated_effort')
