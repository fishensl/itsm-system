"""unique customer device name

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-08-28
"""

from alembic import op
import sqlalchemy as sa


revision = 'a5b6c7d8e9f0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


CONSTRAINT_NAME = 'uq_devices_customer_name'


def _has_constraint(bind):
    inspector = sa.inspect(bind)
    return any(
        item.get('name') == CONSTRAINT_NAME
        for item in inspector.get_unique_constraints('devices')
    )


def upgrade():
    bind = op.get_bind()
    if not _has_constraint(bind):
        # PostgreSQL/SQLite 对 NULL customer_id 均允许多行；未归属设备更新仍必须带 ID。
        with op.batch_alter_table('devices', schema=None) as batch_op:
            batch_op.create_unique_constraint(
                CONSTRAINT_NAME, ['customer_id', 'device_name'])


def downgrade():
    bind = op.get_bind()
    if _has_constraint(bind):
        with op.batch_alter_table('devices', schema=None) as batch_op:
            batch_op.drop_constraint(CONSTRAINT_NAME, type_='unique')
