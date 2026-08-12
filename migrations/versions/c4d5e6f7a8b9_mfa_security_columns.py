"""Add dormant MFA, operation verification and session security columns.

Revision ID: c4d5e6f7a8b9
Revises: e7f8a9b0c1d2
Create Date: 2026-08-12 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'c4d5e6f7a8b9'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


_COLUMNS = (
    sa.Column('mfa_secret_encrypted', sa.Text(), nullable=True),
    sa.Column('mfa_enabled', sa.Boolean(), nullable=True, server_default=sa.false()),
    sa.Column('mfa_op_secret_encrypted', sa.Text(), nullable=True),
    sa.Column('mfa_op_enabled', sa.Boolean(), nullable=True, server_default=sa.false()),
    sa.Column('backup_codes_json', sa.Text(), nullable=True, server_default='[]'),
    sa.Column('auth_version', sa.Integer(), nullable=True, server_default='0'),
    sa.Column('vpn_account', sa.String(length=128), nullable=True, server_default=''),
    sa.Column('op_fail_count', sa.Integer(), nullable=True, server_default='0'),
    sa.Column('op_locked_until', sa.DateTime(), nullable=True),
    sa.Column('login_fail_count', sa.Integer(), nullable=True, server_default='0'),
    sa.Column('login_locked_until', sa.DateTime(), nullable=True),
    sa.Column('mfa_last_counter', sa.BigInteger(), nullable=True),
    sa.Column('mfa_op_last_counter', sa.BigInteger(), nullable=True),
)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'users' not in inspector.get_table_names():
        return
    existing = {column['name'] for column in inspector.get_columns('users')}
    missing = [column for column in _COLUMNS if column.name not in existing]
    if missing:
        with op.batch_alter_table('users', schema=None) as batch_op:
            for column in missing:
                batch_op.add_column(column)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'users' not in inspector.get_table_names():
        return
    existing = {column['name'] for column in inspector.get_columns('users')}
    removable = [column.name for column in reversed(_COLUMNS) if column.name in existing]
    if removable:
        with op.batch_alter_table('users', schema=None) as batch_op:
            for name in removable:
                batch_op.drop_column(name)
