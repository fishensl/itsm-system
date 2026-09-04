"""unify login and high-risk operation MFA

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = 'b3c4d5e6f7a8'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def _users_table():
    return sa.table(
        'users',
        sa.column('mfa_secret_encrypted', sa.Text()),
        sa.column('mfa_enabled', sa.Boolean()),
        sa.column('mfa_op_secret_encrypted', sa.Text()),
        sa.column('mfa_op_enabled', sa.Boolean()),
        sa.column('mfa_last_counter', sa.BigInteger()),
        sa.column('mfa_op_last_counter', sa.BigInteger()),
    )


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'users' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('users')}
    required = {
        'mfa_secret_encrypted', 'mfa_enabled', 'mfa_op_secret_encrypted',
        'mfa_op_enabled', 'mfa_last_counter', 'mfa_op_last_counter',
    }
    if not required.issubset(columns):
        return

    users = _users_table()
    # Preserve an active legacy operation binding only when the account binding
    # is absent or invalid. If both exist, the login/account binding wins.
    bind.execute(
        users.update()
        .where(sa.and_(
            users.c.mfa_op_enabled.is_(True),
            users.c.mfa_op_secret_encrypted.is_not(None),
            sa.or_(
                users.c.mfa_enabled.is_not(True),
                users.c.mfa_secret_encrypted.is_(None),
            ),
        ))
        .values(
            mfa_secret_encrypted=users.c.mfa_op_secret_encrypted,
            mfa_enabled=True,
            mfa_last_counter=users.c.mfa_op_last_counter,
        )
    )
    bind.execute(
        users.update().values(
            mfa_op_secret_encrypted=None,
            mfa_op_enabled=False,
            mfa_op_last_counter=None,
        )
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'users' not in inspector.get_table_names():
        return
    columns = {column['name'] for column in inspector.get_columns('users')}
    required = {
        'mfa_secret_encrypted', 'mfa_enabled', 'mfa_op_secret_encrypted',
        'mfa_op_enabled', 'mfa_last_counter', 'mfa_op_last_counter',
    }
    if not required.issubset(columns):
        return

    users = _users_table()
    # Best-effort compatibility for an application rollback: the old operation
    # verifier can use the same seed. No new secret is invented.
    bind.execute(
        users.update()
        .where(sa.and_(
            users.c.mfa_enabled.is_(True),
            users.c.mfa_secret_encrypted.is_not(None),
        ))
        .values(
            mfa_op_secret_encrypted=users.c.mfa_secret_encrypted,
            mfa_op_enabled=True,
            mfa_op_last_counter=users.c.mfa_last_counter,
        )
    )
