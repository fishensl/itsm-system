"""export files and device export requests

V24: 导出筛选支撑表 —— export_files（一次性导出文件）+ device_export_requests（设备密码导出审核流）。

幂等：表不存在才建。

Revision ID: 9da0e1f2a3b4
Revises: 8c9d0e1f2a3b
Create Date: 2026-08-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '9da0e1f2a3b4'
down_revision = '8c9d0e1f2a3b'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if 'export_files' not in tables:
        op.create_table(
            'export_files',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('token', sa.String(length=64), nullable=False, unique=True),
            sa.Column('file_path', sa.String(length=512), default=''),
            sa.Column('download_name', sa.String(length=256), default=''),
            sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('file_password_encrypted', sa.Text(), default=''),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
            sa.Column('downloaded_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_export_files_token', 'export_files', ['token'])
        op.create_index('ix_export_files_created_by', 'export_files', ['created_by_user_id'])
    if 'device_export_requests' not in tables:
        op.create_table(
            'device_export_requests',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('reason', sa.Text(), default=''),
            sa.Column('filters_json', sa.Text(), default='{}'),
            sa.Column('status', sa.String(length=16), default='pending'),
            sa.Column('reviewed_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('reviewed_at', sa.DateTime(), nullable=True),
            sa.Column('review_comment', sa.Text(), default=''),
            sa.Column('file_token', sa.String(length=64), default=''),
            sa.Column('file_password_encrypted', sa.Text(), default=''),
            sa.Column('downloaded_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_device_export_requests_user', 'device_export_requests', ['user_id'])
        op.create_index('ix_device_export_requests_status', 'device_export_requests', ['status'])


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if 'device_export_requests' in tables:
        op.drop_table('device_export_requests')
    if 'export_files' in tables:
        op.drop_table('export_files')
