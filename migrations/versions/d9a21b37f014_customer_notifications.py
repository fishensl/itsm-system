"""Customer notification bindings and minimal delivery history."""
from alembic import op
import sqlalchemy as sa

revision = 'd9a21b37f014'
down_revision = 'c8e10f26a903'
branch_labels = None
depends_on = None


def upgrade():
    tables = sa.inspect(op.get_bind()).get_table_names()
    if 'customer_notify_bindings' not in tables:
        op.create_table('customer_notify_bindings',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False, unique=True),
            sa.Column('webhook_encrypted', sa.Text(), nullable=False, server_default=''),
            sa.Column('fingerprint', sa.String(64), unique=True),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('updated_at', sa.DateTime()))
    if 'customer_notify_deliveries' not in tables:
        op.create_table('customer_notify_deliveries',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('customer_id', sa.Integer(), nullable=False),
            sa.Column('event_key', sa.String(180), nullable=False, unique=True),
            sa.Column('event_type', sa.String(48), nullable=False),
            sa.Column('binding_version', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(24), nullable=False),
            sa.Column('created_at', sa.DateTime()))
        op.create_index('ix_customer_notify_deliveries_customer_id', 'customer_notify_deliveries', ['customer_id'])


def downgrade():
    for table in ('customer_notify_deliveries', 'customer_notify_bindings'):
        if table in sa.inspect(op.get_bind()).get_table_names():
            op.drop_table(table)
