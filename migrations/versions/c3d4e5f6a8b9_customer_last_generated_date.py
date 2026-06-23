"""customer last_generated_date

V17: 客户巡检频率懒生成需要记录"最近一次生成到的期次起点"，避免每次访问任务安排页都重算。
仅在 customers 表新增一列 last_generated_date (Date, nullable)。

Revision ID: c3d4e5f6a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a8b9'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    if 'last_generated_date' not in _existing_columns(bind, 'customers'):
        with op.batch_alter_table('customers', schema=None) as batch_op:
            batch_op.add_column(sa.Column('last_generated_date', sa.Date(), nullable=True))


def downgrade():
    bind = op.get_bind()
    if 'last_generated_date' in _existing_columns(bind, 'customers'):
        with op.batch_alter_table('customers', schema=None) as batch_op:
            batch_op.drop_column('last_generated_date')
