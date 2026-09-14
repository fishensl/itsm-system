"""customer notification inheritance

客户群通知继承能力：
- customers.notify_inherit_parent：无独立群时是否接收最近上级客户的共享群通知（默认开启）
- customer_notify_bindings.inherit_to_children：本群是否允许无独立群的下级客户共用（默认关闭）

仅新增布尔列，无数据回填；幂等（先查后加）。

Revision ID: a7c1e9d3b5f2
Revises: eab32c480125
Create Date: 2026-09-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c1e9d3b5f2'
down_revision = 'eab32c480125'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    return {c['name'] for c in sa.inspect(bind).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    if 'notify_inherit_parent' not in _existing_columns(bind, 'customers'):
        op.add_column('customers', sa.Column(
            'notify_inherit_parent', sa.Boolean(), nullable=False, server_default=sa.true()))
    if 'inherit_to_children' not in _existing_columns(bind, 'customer_notify_bindings'):
        op.add_column('customer_notify_bindings', sa.Column(
            'inherit_to_children', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    bind = op.get_bind()
    if 'inherit_to_children' in _existing_columns(bind, 'customer_notify_bindings'):
        op.drop_column('customer_notify_bindings', 'inherit_to_children')
    if 'notify_inherit_parent' in _existing_columns(bind, 'customers'):
        op.drop_column('customers', 'notify_inherit_parent')
