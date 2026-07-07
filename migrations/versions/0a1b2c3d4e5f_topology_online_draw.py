"""topology online draw

V20: 拓扑图模块增加在线绘制（drawio 集成）。
topologies 表新增 diagram_xml / source / thumbnail_path / updated_at 四列。
老数据 source 回填为 'upload'，diagram_xml 空字符串。

Revision ID: 0a1b2c3d4e5f
Revises: b8c9d0e1f2a3
Create Date: 2026-07-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0a1b2c3d4e5f'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'topologies')
    with op.batch_alter_table('topologies', schema=None) as batch_op:
        if 'diagram_xml' not in cols:
            batch_op.add_column(sa.Column('diagram_xml', sa.Text(), nullable=True))
        if 'source' not in cols:
            batch_op.add_column(sa.Column('source', sa.String(length=16), nullable=True))
        if 'thumbnail_path' not in cols:
            batch_op.add_column(sa.Column('thumbnail_path', sa.String(length=512), nullable=True))
        if 'updated_at' not in cols:
            batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))
    # 回填：老数据均为上传图
    bind.execute(sa.text(
        "UPDATE topologies SET source='upload', diagram_xml='' WHERE source IS NULL"
    ))


def downgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'topologies')
    with op.batch_alter_table('topologies', schema=None) as batch_op:
        for col in ('diagram_xml', 'source', 'thumbnail_path', 'updated_at'):
            if col in cols:
                batch_op.drop_column(col)
