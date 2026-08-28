"""device import idempotency batches

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-08-28
"""

from alembic import op
import sqlalchemy as sa


revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if 'device_import_batches' not in sa.inspect(bind).get_table_names():
        op.create_table(
            'device_import_batches',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('batch_id', sa.String(length=64), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('file_sha256', sa.String(length=64), nullable=False),
            sa.Column('mode', sa.String(length=16), nullable=False),
            sa.Column('clear_empty', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('result_json', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.UniqueConstraint('batch_id', name='uq_device_import_batches_batch_id'),
        )
        op.create_index('ix_device_import_batches_batch_id', 'device_import_batches', ['batch_id'])
        op.create_index('ix_device_import_batches_user_id', 'device_import_batches', ['user_id'])


def downgrade():
    bind = op.get_bind()
    if 'device_import_batches' in sa.inspect(bind).get_table_names():
        op.drop_table('device_import_batches')
