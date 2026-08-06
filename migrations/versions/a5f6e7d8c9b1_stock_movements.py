"""stock movements 库存流水表

P5: 新增 stock_movements 库存流水表（采购/销售/冲销/盘点调整单一账本）。

Revision ID: a5f6e7d8c9b1
Revises: f7a8b9c0d1e2
Create Date: 2026-08-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5f6e7d8c9b1'
down_revision = '6f5e4d3c2b1a'
branch_labels = None
depends_on = None


def _existing_tables(bind):
    insp = sa.inspect(bind)
    return set(insp.get_table_names())


def upgrade():
    bind = op.get_bind()
    if 'stock_movements' in _existing_tables(bind):
        return
    op.create_table(
        'stock_movements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('spare_part_id', sa.Integer(), sa.ForeignKey('spare_parts.id'), nullable=False, index=True),
        sa.Column('movement_type', sa.String(length=16), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('balance_after', sa.Integer(), nullable=True),
        sa.Column('location', sa.String(length=128), nullable=True),
        sa.Column('source_id', sa.Integer(), nullable=True),
        sa.Column('operator', sa.String(length=64), nullable=True),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, index=True),
    )


def downgrade():
    bind = op.get_bind()
    if 'stock_movements' in _existing_tables(bind):
        op.drop_table('stock_movements')
