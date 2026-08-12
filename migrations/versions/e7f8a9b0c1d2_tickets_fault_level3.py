"""tickets.fault_category_level3

工单故障分类与 Fault 对齐：tickets 补 fault_category_level3 列（三级分类）。

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name'] for c in insp.get_columns('tickets')}
    if 'fault_category_level3' not in cols:
        with op.batch_alter_table('tickets', schema=None) as batch_op:
            batch_op.add_column(sa.Column('fault_category_level3', sa.String(length=64),
                                          nullable=True, server_default=''))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c['name'] for c in insp.get_columns('tickets')}
    if 'fault_category_level3' in cols:
        with op.batch_alter_table('tickets', schema=None) as batch_op:
            batch_op.drop_column('fault_category_level3')
