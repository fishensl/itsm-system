"""audit_logs 表（P4 操作审计查询页）

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def _existing_tables(bind):
    insp = sa.inspect(bind)
    return set(insp.get_table_names())


def upgrade():
    bind = op.get_bind()
    if 'audit_logs' in _existing_tables(bind):
        return
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('username', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('action', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('target_type', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('detail', sa.String(length=512), nullable=False, server_default=''),
        sa.Column('ip', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_audit_logs_username', 'audit_logs', ['username'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])


def downgrade():
    bind = op.get_bind()
    if 'audit_logs' in _existing_tables(bind):
        op.drop_table('audit_logs')
