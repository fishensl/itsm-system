"""device rack_location

设备增加可写的「机房位置」字段：未上架设备可在批量修改中写入自身机房位置
（已上架设备仍读所在机柜 Rack.location）。幂等：先查后加。

Revision ID: f8a9b0c1d2e3
Revises: d7e8f9a0b1c2
Create Date: 2026-08-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f8a9b0c1d2e3'
down_revision = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {col['name'] for col in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    if 'rack_location' not in _existing_columns(bind, 'devices'):
        op.add_column('devices', sa.Column('rack_location', sa.String(length=128), nullable=False,
                                           server_default=''))


def downgrade():
    bind = op.get_bind()
    if 'rack_location' in _existing_columns(bind, 'devices'):
        op.drop_column('devices', 'rack_location')
