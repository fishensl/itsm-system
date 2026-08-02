"""system_settings 表（P4 界面版本切换等键值配置）

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd3e4f5a6b7c8'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def _existing_tables(bind):
    insp = sa.inspect(bind)
    return set(insp.get_table_names())


def upgrade():
    bind = op.get_bind()
    if 'system_settings' in _existing_tables(bind):
        return
    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(length=64), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False, server_default=''),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    bind = op.get_bind()
    if 'system_settings' in _existing_tables(bind):
        op.drop_table('system_settings')
