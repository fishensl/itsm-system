"""customer_engineers 工程师-客户直接关联表

需求：用户管理里可直接勾选工程师负责的客户（多对多），
创建工单/巡检/故障时客户下拉优先按直接关联过滤，无关联时回退负责区域。

Revision ID: c9d0e1f2a3b4
Revises: b2c3d4e5f6a8
Create Date: 2026-08-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d0e1f2a3b4'
down_revision = 'b2c3d4e5f6a8'
branch_labels = None
depends_on = None


def _existing_tables(bind):
    insp = sa.inspect(bind)
    return set(insp.get_table_names())


def upgrade():
    bind = op.get_bind()
    if 'customer_engineers' in _existing_tables(bind):
        return
    op.create_table(
        'customer_engineers',
        sa.Column('customer_id', sa.Integer(),
                  sa.ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('engineer_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade():
    bind = op.get_bind()
    if 'customer_engineers' in _existing_tables(bind):
        op.drop_table('customer_engineers')
