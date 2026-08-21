"""device power supply

设备增加电源配置字段（单电源/双电源）。枚举合法性由 service 写入边界校验，
数据库迁移只增加兼容存量数据的非空空字符串列。

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-08-17 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b0c1d2e3f4a5'
down_revision = 'a9b0c1d2e3f4'
branch_labels = None
depends_on = None


def _columns(bind):
    return {column['name'] for column in sa.inspect(bind).get_columns('devices')}


def upgrade():
    bind = op.get_bind()
    if 'power_supply' not in _columns(bind):
        op.add_column('devices', sa.Column(
            'power_supply', sa.String(length=16), nullable=False, server_default=''))


def downgrade():
    bind = op.get_bind()
    if 'power_supply' in _columns(bind):
        op.drop_column('devices', 'power_supply')
