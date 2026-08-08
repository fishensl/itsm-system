"""multi role codes

V24: 用户多角色 —— users.role_codes（JSON 数组，首个=主角色）。

- 幂等加列 role_codes（Text，JSON 数组字符串）
- 从既有 role 回填（'["operator"]' 形式）
- 补索引 ix_users_role_codes

Revision ID: 7b8c9d0e1f2a
Revises: 6f5e4d3c2b1a
Create Date: 2026-08-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '7b8c9d0e1f2a'
down_revision = 'b2c3d4e5f6a8'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c['name'] for c in insp.get_columns(table)}


def _existing_indexes(bind, table):
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {ix['name'] for ix in insp.get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'users')
    if 'role_codes' not in cols:
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.add_column(sa.Column('role_codes', sa.Text(), nullable=True))
        op.execute(
            "UPDATE users SET role_codes = '[\"' || COALESCE(role, 'viewer') || '\"]' "
            "WHERE role_codes IS NULL"
        )
    if 'ix_users_role_codes' not in _existing_indexes(bind, 'users'):
        op.create_index('ix_users_role_codes', 'users', ['role_codes'])


def downgrade():
    bind = op.get_bind()
    if 'ix_users_role_codes' in _existing_indexes(bind, 'users'):
        op.drop_index('ix_users_role_codes', table_name='users')
    cols = _existing_columns(bind, 'users')
    if 'role_codes' in cols:
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.drop_column('role_codes')
