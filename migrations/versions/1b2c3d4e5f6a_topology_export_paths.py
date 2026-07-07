"""topology pdf/vsdx export paths

V20.1: topologies 表加 pdf_path / vsdx_path 两列，
在线图保存后自动导出 PDF 和 VSDX 便于列表页快速下载。

Revision ID: 1b2c3d4e5f6a
Revises: 0a1b2c3d4e5f
Create Date: 2026-07-07 02:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '1b2c3d4e5f6a'
down_revision = '0a1b2c3d4e5f'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'topologies')
    with op.batch_alter_table('topologies', schema=None) as batch_op:
        if 'pdf_path' not in cols:
            batch_op.add_column(sa.Column('pdf_path', sa.String(length=512), nullable=True))
        if 'vsdx_path' not in cols:
            batch_op.add_column(sa.Column('vsdx_path', sa.String(length=512), nullable=True))


def downgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'topologies')
    with op.batch_alter_table('topologies', schema=None) as batch_op:
        for col in ('pdf_path', 'vsdx_path'):
            if col in cols:
                batch_op.drop_column(col)
