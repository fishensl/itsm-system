"""notifications 表（P3 站内通知中心）

Revision ID: b1c2d3e4f5a6
Revises: a8b9c0d1e2f3
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b1c2d3e4f5a6'
down_revision = 'a8b9c0d1e2f3'
branch_labels = None
depends_on = None


def _existing_tables(bind):
    insp = sa.inspect(bind)
    return set(insp.get_table_names())


def upgrade():
    bind = op.get_bind()
    if 'notifications' in _existing_tables(bind):
        return  # 幂等
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False, server_default='system'),
        sa.Column('title', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('link', sa.String(length=256), nullable=False, server_default=''),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_is_read', 'notifications', ['is_read'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])


def downgrade():
    bind = op.get_bind()
    if 'notifications' in _existing_tables(bind):
        op.drop_table('notifications')
