"""device power dictionary and rated power

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-28
"""

from alembic import op
import sqlalchemy as sa


revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def _tables(bind):
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table_name):
    return {column['name'] for column in sa.inspect(bind).get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    tables = _tables(bind)
    if 'device_power_configs' not in tables:
        op.create_table(
            'device_power_configs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(length=32), nullable=False),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('name', name='uq_device_power_configs_name'),
        )
        power_table = sa.table(
            'device_power_configs',
            sa.column('name', sa.String()),
            sa.column('sort_order', sa.Integer()),
            sa.column('is_active', sa.Boolean()),
        )
        op.bulk_insert(power_table, [
            {'name': '单电源', 'sort_order': 10, 'is_active': True},
            {'name': '双电源', 'sort_order': 20, 'is_active': True},
            {'name': '四电源', 'sort_order': 30, 'is_active': True},
        ])

    if 'rated_power_w' not in _columns(bind, 'devices'):
        with op.batch_alter_table('devices', schema=None) as batch_op:
            batch_op.add_column(sa.Column('rated_power_w', sa.Integer(), nullable=True))

    check_names = {
        item.get('name') for item in sa.inspect(bind).get_check_constraints('devices')
    }
    if 'ck_devices_rated_power_nonnegative' not in check_names:
        with op.batch_alter_table('devices', schema=None) as batch_op:
            batch_op.create_check_constraint(
                'ck_devices_rated_power_nonnegative',
                'rated_power_w IS NULL OR rated_power_w >= 0')

    # 旧机柜上架功率仅在同一设备所有正值一致时回填；冲突值留待预演人工处理。
    op.execute(sa.text("""
        UPDATE devices
           SET rated_power_w = (
               SELECT MIN(ri.rated_w)
                 FROM rack_installs ri
                WHERE ri.device_id = devices.id AND ri.rated_w > 0
           )
         WHERE rated_power_w IS NULL
           AND 1 = (
               SELECT COUNT(DISTINCT ri.rated_w)
                 FROM rack_installs ri
                WHERE ri.device_id = devices.id AND ri.rated_w > 0
           )
    """))


def downgrade():
    bind = op.get_bind()
    if 'rated_power_w' in _columns(bind, 'devices'):
        with op.batch_alter_table('devices', schema=None) as batch_op:
            batch_op.drop_constraint('ck_devices_rated_power_nonnegative', type_='check')
            batch_op.drop_column('rated_power_w')
    if 'device_power_configs' in _tables(bind):
        op.drop_table('device_power_configs')
