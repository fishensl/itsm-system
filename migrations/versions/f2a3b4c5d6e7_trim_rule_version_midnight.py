"""trim synthetic midnight from date-like rule versions

Revision ID: f2a3b4c5d6e7
Revises: b3c4d5e6f7a8
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = 'f2a3b4c5d6e7'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'devices' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('devices')}
    if 'rule_version' not in columns:
        return

    devices = sa.table('devices', sa.column('rule_version', sa.String(128)))
    # Earlier Excel imports stringified date cells as ``YYYY-MM-DD 00:00:00``.
    # Limit cleanup to that exact shape so real version strings remain untouched.
    bind.execute(
        devices.update()
        .where(sa.and_(
            sa.func.length(devices.c.rule_version) == 19,
            devices.c.rule_version.like('____-__-__ 00:00:00'),
        ))
        .values(rule_version=sa.func.substr(devices.c.rule_version, 1, 10))
    )


def downgrade():
    # The removed midnight was synthetic import noise and cannot be reconstructed.
    pass
