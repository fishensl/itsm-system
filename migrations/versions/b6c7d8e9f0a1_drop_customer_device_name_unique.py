"""drop invalid customer device name uniqueness

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa


revision = 'b6c7d8e9f0a1'
down_revision = 'a5b6c7d8e9f0'
branch_labels = None
depends_on = None


CONSTRAINT_NAME = 'uq_devices_customer_name'


def _has_constraint(bind):
    return any(
        item.get('name') == CONSTRAINT_NAME
        for item in sa.inspect(bind).get_unique_constraints('devices')
    )


def _has_duplicate_names(bind):
    return bool(bind.execute(sa.text("""
        SELECT 1
          FROM devices
         WHERE customer_id IS NOT NULL
         GROUP BY customer_id, device_name
        HAVING COUNT(*) > 1
         LIMIT 1
    """)).first())


def upgrade():
    bind = op.get_bind()
    if _has_constraint(bind):
        with op.batch_alter_table('devices', schema=None) as batch_op:
            batch_op.drop_constraint(CONSTRAINT_NAME, type_='unique')


def downgrade():
    bind = op.get_bind()
    if not _has_constraint(bind) and not _has_duplicate_names(bind):
        with op.batch_alter_table('devices', schema=None) as batch_op:
            batch_op.create_unique_constraint(
                CONSTRAINT_NAME, ['customer_id', 'device_name'])
