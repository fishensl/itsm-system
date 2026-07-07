"""topology svg path

V20.3: topologies 表加 svg_path 列，在线图保存后自动导出 SVG（矢量预览）。
PDF 由服务端 cairosvg 从 SVG 转换生成（drawio embed 不支持 pdf 导出）。

Revision ID: 2c3d4e5f6a7b
Revises: 1b2c3d4e5f6a
Create Date: 2026-07-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '2c3d4e5f6a7b'
down_revision = '1b2c3d4e5f6a'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'topologies')
    if 'svg_path' not in cols:
        with op.batch_alter_table('topologies', schema=None) as batch_op:
            batch_op.add_column(sa.Column('svg_path', sa.String(length=512), nullable=True))


def downgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'topologies')
    if 'svg_path' in cols:
        with op.batch_alter_table('topologies', schema=None) as batch_op:
            batch_op.drop_column('svg_path')
