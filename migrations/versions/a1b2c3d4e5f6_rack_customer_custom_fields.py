"""rack customer_id + customer extra_fields

新增：
  - racks.customer_id: 机柜直接归属客户（按客户分组管理）
  - customers.extra_fields: 客户自定义字段（JSON 列表 [{name, value}, ...]，每客户独立）

Revision ID: a1b2c3d4e5f6
Revises: 6e2d88637a8d
Create Date: 2026-06-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '6e2d88637a8d'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def _has_table(bind, table):
    return sa.inspect(bind).has_table(table)


def upgrade():
    bind = op.get_bind()

    # 1. racks.customer_id
    rack_cols = _existing_columns(bind, 'racks')
    with op.batch_alter_table('racks', schema=None) as batch_op:
        if 'customer_id' not in rack_cols:
            batch_op.add_column(sa.Column('customer_id', sa.Integer(), nullable=True))
            batch_op.create_index('ix_racks_customer_id', ['customer_id'])

    # 2. customers.extra_fields
    cust_cols = _existing_columns(bind, 'customers')
    with op.batch_alter_table('customers', schema=None) as batch_op:
        if 'extra_fields' not in cust_cols:
            batch_op.add_column(sa.Column('extra_fields', sa.Text(), nullable=True,
                                          server_default=''))

    # 3. 清理早期实现遗留的全局字段定义表（改为每客户独立后不再需要）
    if _has_table(bind, 'customer_custom_fields'):
        op.drop_table('customer_custom_fields')


def downgrade():
    bind = op.get_bind()

    cust_cols = _existing_columns(bind, 'customers')
    with op.batch_alter_table('customers', schema=None) as batch_op:
        if 'extra_fields' in cust_cols:
            batch_op.drop_column('extra_fields')

    rack_cols = _existing_columns(bind, 'racks')
    with op.batch_alter_table('racks', schema=None) as batch_op:
        if 'customer_id' in rack_cols:
            batch_op.drop_index('ix_racks_customer_id')
            batch_op.drop_column('customer_id')
