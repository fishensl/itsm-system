"""add user must_change_password

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-08-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a9b0c1d2e3f4'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


def _columns(bind):
    return {column['name'] for column in sa.inspect(bind).get_columns('users')}


def upgrade():
    bind = op.get_bind()
    if 'must_change_password' not in _columns(bind):
        op.add_column('users', sa.Column(
            'must_change_password', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    bind = op.get_bind()
    if 'must_change_password' in _columns(bind):
        op.drop_column('users', 'must_change_password')
