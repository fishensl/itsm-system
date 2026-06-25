"""device license_start

V18: 设备资产授权时间显示从"截止日"扩展为"开始日 - 截止日"两行展示。
仅在 devices 表新增一列 license_start (Date, nullable)。

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a8b9
Create Date: 2026-06-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a8b9'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    if 'license_start' not in _existing_columns(bind, 'devices'):
        with op.batch_alter_table('devices', schema=None) as batch_op:
            batch_op.add_column(sa.Column('license_start', sa.Date(), nullable=True))


def downgrade():
    bind = op.get_bind()
    if 'license_start' in _existing_columns(bind, 'devices'):
        with op.batch_alter_table('devices', schema=None) as batch_op:
            batch_op.drop_column('license_start')
