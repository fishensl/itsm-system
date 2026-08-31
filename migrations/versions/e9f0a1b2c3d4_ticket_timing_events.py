"""ticket and fault timing events/snapshots

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa


revision = 'e9f0a1b2c3d4'
down_revision = 'd8e9f0a1b2c3'
branch_labels = None
depends_on = None


def _columns(bind, table):
    if table not in sa.inspect(bind).get_table_names():
        return set()
    return {column['name'] for column in sa.inspect(bind).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    ticket_columns = _columns(bind, 'tickets')
    if 'reported_at' not in ticket_columns:
        with op.batch_alter_table('tickets', schema=None) as batch_op:
            batch_op.add_column(sa.Column('reported_at', sa.DateTime(), nullable=True))

    fault_columns = _columns(bind, 'faults')
    if 'handling_started_at' not in fault_columns:
        with op.batch_alter_table('faults', schema=None) as batch_op:
            batch_op.add_column(sa.Column('handling_started_at', sa.DateTime(), nullable=True))

    if 'ticket_timing_events' not in tables:
        op.create_table(
            'ticket_timing_events',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id'), nullable=False),
            sa.Column('cycle_no', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('event_type', sa.String(length=32), nullable=False),
            sa.Column('from_status', sa.String(length=32), nullable=True, server_default=''),
            sa.Column('to_status', sa.String(length=32), nullable=True, server_default=''),
            sa.Column('occurred_at_utc', sa.DateTime(), nullable=False),
            sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('actor_name_snapshot', sa.String(length=64), nullable=True, server_default=''),
            sa.Column('source', sa.String(length=16), nullable=False, server_default='api'),
            sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        op.create_index('ix_ticket_timing_events_ticket_id', 'ticket_timing_events', ['ticket_id'])
        op.create_index('ix_ticket_timing_events_event_type', 'ticket_timing_events', ['event_type'])
        op.create_index('ix_ticket_timing_events_occurred_at_utc', 'ticket_timing_events',
                        ['occurred_at_utc'])
        op.create_index('ix_ticket_timing_event_ticket_cycle_time',
                        'ticket_timing_events',
                        ['ticket_id', 'cycle_no', 'occurred_at_utc'])

    if 'ticket_timing_snapshots' not in tables:
        op.create_table(
            'ticket_timing_snapshots',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('tickets.id'), nullable=False),
            sa.Column('cycle_no', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('response_seconds', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('handling_seconds', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('closure_seconds', sa.Integer(), nullable=True),
            sa.Column('suspended_business_seconds', sa.Integer(), nullable=False,
                      server_default='0'),
            sa.Column('started_at_utc', sa.DateTime(), nullable=True),
            sa.Column('finished_at_utc', sa.DateTime(), nullable=True),
            sa.Column('algorithm_version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('calendar_version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('is_estimated', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('estimate_reason', sa.String(length=256), nullable=True, server_default=''),
            sa.Column('finish_source', sa.String(length=32), nullable=True, server_default=''),
            sa.Column('generated_at_utc', sa.DateTime(), nullable=False),
            sa.Column('source', sa.String(length=16), nullable=False, server_default='api'),
            sa.UniqueConstraint('ticket_id', 'cycle_no',
                                name='uq_ticket_timing_snapshot_cycle'),
        )
        op.create_index('ix_ticket_timing_snapshots_ticket_id', 'ticket_timing_snapshots',
                        ['ticket_id'])


def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if 'ticket_timing_snapshots' in tables:
        op.drop_table('ticket_timing_snapshots')
    if 'ticket_timing_events' in tables:
        op.drop_table('ticket_timing_events')
    if 'handling_started_at' in _columns(bind, 'faults'):
        with op.batch_alter_table('faults', schema=None) as batch_op:
            batch_op.drop_column('handling_started_at')
    if 'reported_at' in _columns(bind, 'tickets'):
        with op.batch_alter_table('tickets', schema=None) as batch_op:
            batch_op.drop_column('reported_at')
