"""rack install side

机柜上架记录保存正面/背面，使同一 U 位可按安装面独立占用；已有托管记录
从设备安装位置回填。幂等：先查列再增删。

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa


revision = 'd8e9f0a1b2c3'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    return {column['name'] for column in sa.inspect(bind).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    if 'rack_installs' not in sa.inspect(bind).get_table_names():
        return
    if 'install_side' not in _existing_columns(bind, 'rack_installs'):
        op.add_column('rack_installs', sa.Column(
            'install_side', sa.String(length=16), nullable=False, server_default=''))
    if 'devices' in sa.inspect(bind).get_table_names():
        op.execute(sa.text("""
            UPDATE rack_installs
               SET install_side = COALESCE(
                   (SELECT devices.location
                      FROM devices
                     WHERE devices.id = rack_installs.device_id), '')
             WHERE COALESCE(install_side, '') = ''
        """))


def downgrade():
    bind = op.get_bind()
    if ('rack_installs' in sa.inspect(bind).get_table_names()
            and 'install_side' in _existing_columns(bind, 'rack_installs')):
        with op.batch_alter_table('rack_installs') as batch_op:
            batch_op.drop_column('install_side')
