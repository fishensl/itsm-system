"""inspection_tasks actual_effort

V19b: 任务增加"实际工作量"（单位：人天，Float，nullable），与 estimated_effort 对比。
仅给 inspection_tasks 表新增一列 actual_effort，老数据保持 NULL。

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-06 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    if 'actual_effort' not in _existing_columns(bind, 'inspection_tasks'):
        with op.batch_alter_table('inspection_tasks', schema=None) as batch_op:
            batch_op.add_column(sa.Column('actual_effort', sa.Float(), nullable=True))


def downgrade():
    bind = op.get_bind()
    if 'actual_effort' in _existing_columns(bind, 'inspection_tasks'):
        with op.batch_alter_table('inspection_tasks', schema=None) as batch_op:
            batch_op.drop_column('actual_effort')
