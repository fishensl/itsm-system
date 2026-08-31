"""credential envelope challenges

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa


revision = 'f0a1b2c3d4e5'
down_revision = 'e9f0a1b2c3d4'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if 'credential_envelope_challenges' not in tables:
        _create_challenge_table()
    if 'credential_download_tickets' not in tables:
        _create_download_ticket_table()


def _create_challenge_table():
    op.create_table(
        'credential_envelope_challenges',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('username_snapshot', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('auth_version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('auth_strength', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('login_at', sa.DateTime(), nullable=False),
        sa.Column('mfa_verified_at', sa.DateTime(), nullable=False),
        sa.Column('session_binding_hash', sa.String(length=64), nullable=False),
        sa.Column('operation_binding_hash', sa.String(length=64), nullable=True),
        sa.Column('purpose', sa.String(length=64), nullable=False),
        sa.Column('method', sa.String(length=8), nullable=False),
        sa.Column('path', sa.String(length=256), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=True),
        sa.Column('target_id', sa.String(length=64), nullable=True),
        sa.Column('history_id', sa.String(length=64), nullable=True),
        sa.Column('client_public_jwk', sa.Text(), nullable=False),
        sa.Column('server_public_jwk', sa.Text(), nullable=False),
        sa.Column('server_private_key_wrapped', sa.Text(), nullable=True),
        sa.Column('wrap_kid', sa.String(length=64), nullable=False),
        sa.Column('salt', sa.String(length=64), nullable=False),
        sa.Column('context_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='issued'),
        sa.Column('client_ciphertext_hash', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('issued','used','rejected','expired')",
            name='ck_credential_envelope_challenge_status'),
        sa.CheckConstraint(
            'expires_at > created_at',
            name='ck_credential_envelope_challenge_expiry'),
    )
    op.create_index('ix_credential_envelope_challenges_user_id',
                    'credential_envelope_challenges', ['user_id'])
    op.create_index('ix_credential_envelope_challenges_purpose',
                    'credential_envelope_challenges', ['purpose'])
    op.create_index('ix_credential_envelope_challenges_status',
                    'credential_envelope_challenges', ['status'])
    op.create_index('ix_credential_envelope_challenges_expires_at',
                    'credential_envelope_challenges', ['expires_at'])
    op.create_index('ix_credential_envelope_challenges_session_binding_hash',
                    'credential_envelope_challenges', ['session_binding_hash'])
    op.create_index('ix_credential_challenge_user_status_expiry',
                    'credential_envelope_challenges', ['user_id', 'status', 'expires_at'])


def _create_download_ticket_table():
    op.create_table(
        'credential_download_tickets',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('export_file_id', sa.Integer(), sa.ForeignKey('export_files.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('purpose', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            'expires_at > created_at',
            name='ck_credential_download_ticket_expiry'),
    )
    op.create_index('ix_credential_download_tickets_export_file_id',
                    'credential_download_tickets', ['export_file_id'])
    op.create_index('ix_credential_download_tickets_user_id',
                    'credential_download_tickets', ['user_id'])
    op.create_index('ix_credential_download_tickets_purpose',
                    'credential_download_tickets', ['purpose'])
    op.create_index('ix_credential_download_tickets_expires_at',
                    'credential_download_tickets', ['expires_at'])


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if 'credential_download_tickets' in tables:
        op.drop_table('credential_download_tickets')
    if 'credential_envelope_challenges' in tables:
        op.drop_table('credential_envelope_challenges')
