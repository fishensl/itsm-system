"""contract service period + ticket suspension + notify channels

合同服务期（P3）：
- customers: contract_start_date / contract_end_date / contract_expiry_notified /
  office_room / map_location
工单处置闭环（P3/P4）：
- tickets: customer_name_text（外网手填客户名）/ contract_exception_*（过期例外）/
  suspended_*（挂起）
- inspection_tasks: contract_exception_*（过期例外）
- 新表 ticket_suspends / ticket_progresses / customer_contract_reviews
多渠道通知平台（P3）：
- users: notify_accounts_json（{wecom: "..."} 等渠道账号）
- 新表 notify_channel_configs / notify_rules

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4c5d6e7f8a9'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def _columns(bind, table):
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c['name'] for c in insp.get_columns(table)}


def _tables(bind):
    return set(sa.inspect(bind).get_table_names())


def upgrade():
    bind = op.get_bind()
    cols = _columns(bind, 'customers')
    with op.batch_alter_table('customers', schema=None) as batch_op:
        if 'contract_start_date' not in cols:
            batch_op.add_column(sa.Column('contract_start_date', sa.Date(), nullable=True))
        if 'contract_end_date' not in cols:
            batch_op.add_column(sa.Column('contract_end_date', sa.Date(), nullable=True))
        if 'contract_expiry_notified' not in cols:
            batch_op.add_column(sa.Column('contract_expiry_notified', sa.Date(), nullable=True))
        if 'office_room' not in cols:
            batch_op.add_column(sa.Column('office_room', sa.String(64), nullable=False,
                                          server_default=''))
        if 'map_location' not in cols:
            batch_op.add_column(sa.Column('map_location', sa.String(256), nullable=False,
                                          server_default=''))

    tcols = _columns(bind, 'tickets')
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        if 'customer_name_text' not in tcols:
            batch_op.add_column(sa.Column('customer_name_text', sa.String(128), nullable=False,
                                          server_default=''))
        if 'contract_exception_status' not in tcols:
            batch_op.add_column(sa.Column('contract_exception_status', sa.String(16),
                                          nullable=False, server_default=''))
        if 'contract_exception_reason' not in tcols:
            batch_op.add_column(sa.Column('contract_exception_reason', sa.Text(), nullable=False,
                                          server_default=''))
        if 'contract_exception_by' not in tcols:
            batch_op.add_column(sa.Column('contract_exception_by', sa.String(64), nullable=False,
                                          server_default=''))
        if 'contract_exception_at' not in tcols:
            batch_op.add_column(sa.Column('contract_exception_at', sa.DateTime(), nullable=True))
        if 'suspended_at' not in tcols:
            batch_op.add_column(sa.Column('suspended_at', sa.DateTime(), nullable=True))
        if 'suspended_seconds' not in tcols:
            batch_op.add_column(sa.Column('suspended_seconds', sa.Integer(), nullable=False,
                                          server_default='0'))
        if 'suspend_timeout_notified_at' not in tcols:
            batch_op.add_column(sa.Column('suspend_timeout_notified_at', sa.DateTime(),
                                          nullable=True))

    icols = _columns(bind, 'inspection_tasks')
    with op.batch_alter_table('inspection_tasks', schema=None) as batch_op:
        if 'contract_exception_status' not in icols:
            batch_op.add_column(sa.Column('contract_exception_status', sa.String(16),
                                          nullable=False, server_default=''))
        if 'contract_exception_reason' not in icols:
            batch_op.add_column(sa.Column('contract_exception_reason', sa.Text(), nullable=False,
                                          server_default=''))
        if 'contract_exception_by' not in icols:
            batch_op.add_column(sa.Column('contract_exception_by', sa.String(64), nullable=False,
                                          server_default=''))
        if 'contract_exception_at' not in icols:
            batch_op.add_column(sa.Column('contract_exception_at', sa.DateTime(), nullable=True))

    ucols = _columns(bind, 'users')
    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'notify_accounts_json' not in ucols:
            batch_op.add_column(sa.Column('notify_accounts_json', sa.Text(), nullable=False,
                                          server_default='{}'))

    tables = _tables(bind)
    if 'ticket_suspends' not in tables:
        op.create_table(
            'ticket_suspends',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id'), nullable=False,
                      index=True),
            sa.Column('reason', sa.Text(), nullable=False, server_default=''),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('ended_at', sa.DateTime(), nullable=True),
            sa.Column('operator', sa.String(64), nullable=False, server_default=''),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
    if 'ticket_progresses' not in tables:
        op.create_table(
            'ticket_progresses',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id'), nullable=False,
                      index=True),
            sa.Column('content', sa.Text(), nullable=False, server_default=''),
            sa.Column('photos_json', sa.Text(), nullable=False, server_default='[]'),
            sa.Column('operator', sa.String(64), nullable=False, server_default=''),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
    if 'customer_contract_reviews' not in tables:
        op.create_table(
            'customer_contract_reviews',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'),
                      nullable=False, index=True),
            sa.Column('requester_user_id', sa.Integer(), sa.ForeignKey('users.id'),
                      nullable=True),
            sa.Column('reason', sa.Text(), nullable=False, server_default=''),
            sa.Column('status', sa.String(16), nullable=False, server_default=''),  # ''/待审核/通过/拒绝
            sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('reviewed_at', sa.DateTime(), nullable=True),
            sa.Column('review_comment', sa.Text(), nullable=False, server_default=''),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
    if 'notify_channel_configs' not in tables:
        op.create_table(
            'notify_channel_configs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('channel_type', sa.String(32), nullable=False, unique=True),
            sa.Column('name', sa.String(64), nullable=False, server_default=''),
            sa.Column('config_json', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )
    if 'notify_rules' not in tables:
        op.create_table(
            'notify_rules',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('event_type', sa.String(32), nullable=False, unique=True),
            sa.Column('label', sa.String(128), nullable=False, server_default=''),
            sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('recipients_json', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    tables = _tables(bind)
    for t in ('notify_rules', 'notify_channel_configs', 'customer_contract_reviews',
              'ticket_progresses', 'ticket_suspends'):
        if t in tables:
            op.drop_table(t)
    for table, cols in (
            ('users', ('notify_accounts_json',)),
            ('inspection_tasks', ('contract_exception_at', 'contract_exception_by',
                                  'contract_exception_reason', 'contract_exception_status')),
            ('tickets', ('suspend_timeout_notified_at', 'suspended_seconds', 'suspended_at',
                         'contract_exception_at', 'contract_exception_by',
                         'contract_exception_reason', 'contract_exception_status',
                         'customer_name_text')),
            ('customers', ('map_location', 'office_room', 'contract_expiry_notified',
                           'contract_end_date', 'contract_start_date'))):
        present = _columns(bind, table)
        to_drop = [c for c in cols if c in present]
        if to_drop:
            with op.batch_alter_table(table, schema=None) as batch_op:
                for c in to_drop:
                    batch_op.drop_column(c)
