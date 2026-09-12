"""Durable notification outbox and multiple customer destinations."""
from alembic import op
import sqlalchemy as sa

revision = 'eab32c480125'
down_revision = 'd9a21b37f014'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    cols = {c['name'] for c in inspector.get_columns('customer_notify_bindings')}
    uniques = inspector.get_unique_constraints('customer_notify_bindings')
    with op.batch_alter_table('customer_notify_bindings', naming_convention={'uq': 'uq_%(table_name)s_%(column_0_name)s'}) as batch:
        for u in uniques:
            if u['column_names'] == ['customer_id']:
                batch.drop_constraint(u['name'] or 'uq_customer_notify_bindings_customer_id', type_='unique')
        for name, typ, default in [
            ('name', sa.String(80), '客户群'), ('channel_type', sa.String(20), 'wecom'),
            ('signing_secret_encrypted', sa.Text(), ''), ('subscriptions_json', sa.Text(), '{}'),
            ('quiet_start', sa.Integer(), '0'), ('quiet_end', sa.Integer(), '0'),
            ('digest_minutes', sa.Integer(), '0')]:
            if name not in cols:
                batch.add_column(sa.Column(name, typ, nullable=False, server_default=default))
        if 'next_send_at' not in cols:
            batch.add_column(sa.Column('next_send_at', sa.DateTime()))
    if 'ix_customer_notify_bindings_customer_id' not in {i['name'] for i in inspector.get_indexes('customer_notify_bindings')}:
        op.create_index('ix_customer_notify_bindings_customer_id', 'customer_notify_bindings', ['customer_id'])
    # Definitions are frozen here, independent from future ORM changes.
    if not sa.inspect(op.get_bind()).has_table('notification_events'):
        op.create_table('notification_events',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('dedupe_key', sa.String(200), nullable=False, unique=True),
            sa.Column('event_type', sa.String(64), nullable=False), sa.Column('audience', sa.String(16), nullable=False),
            sa.Column('customer_id', sa.Integer()), sa.Column('entity_type', sa.String(24), nullable=False, server_default=''),
            sa.Column('entity_id', sa.Integer()), sa.Column('payload_json', sa.Text(), nullable=False),
            sa.Column('template_version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=False), sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('confirmed_by', sa.Integer()), sa.Column('confirmed_at', sa.DateTime()),
            sa.Column('feedback', sa.String(500), nullable=False, server_default=''))
        op.create_index('ix_notification_events_customer_id', 'notification_events', ['customer_id'])
        op.create_index('ix_notification_events_created_at', 'notification_events', ['created_at'])
    if not sa.inspect(op.get_bind()).has_table('notification_deliveries'):
        op.create_table('notification_deliveries',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('event_id', sa.String(36), sa.ForeignKey('notification_events.id', ondelete='CASCADE'), nullable=False),
            sa.Column('target_key', sa.String(80), nullable=False), sa.Column('binding_id', sa.Integer()),
            sa.Column('binding_version', sa.Integer()), sa.Column('channel_type', sa.String(24), nullable=False),
            sa.Column('user_id', sa.Integer()), sa.Column('config_fingerprint', sa.String(64)),
            sa.Column('status', sa.String(24), nullable=False), sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('next_attempt_at', sa.DateTime(), nullable=False), sa.Column('lease_until', sa.DateTime()),
            sa.Column('lease_token', sa.String(36)), sa.Column('error_code', sa.String(64), nullable=False, server_default=''),
            sa.Column('finished_at', sa.DateTime()), sa.UniqueConstraint('event_id', 'target_key', name='uq_notification_event_target'))
        for col in ('event_id', 'status', 'next_attempt_at'):
            op.create_index('ix_notification_deliveries_' + col, 'notification_deliveries', [col])
    if not sa.inspect(op.get_bind()).has_table('notification_attempts'):
        op.create_table('notification_attempts', sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('delivery_id', sa.Integer(), sa.ForeignKey('notification_deliveries.id', ondelete='CASCADE'), nullable=False),
            sa.Column('number', sa.Integer(), nullable=False), sa.Column('result', sa.String(24), nullable=False),
            sa.Column('error_code', sa.String(64), nullable=False, server_default=''), sa.Column('created_at', sa.DateTime(), nullable=False))
        op.create_index('ix_notification_attempts_delivery_id', 'notification_attempts', ['delivery_id'])
    if not sa.inspect(op.get_bind()).has_table('notification_preferences'):
        op.create_table('notification_preferences', sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
            sa.Column('daily_digest', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('weekly_digest', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('reminders', sa.Boolean(), nullable=False, server_default=sa.true()))
    if not sa.inspect(op.get_bind()).has_table('notification_worker_states'):
        op.create_table('notification_worker_states', sa.Column('id', sa.String(40), primary_key=True), sa.Column('heartbeat_at', sa.DateTime(), nullable=False))


def downgrade():
    raise RuntimeError('通知历史与多目的地不能安全自动降级；先停消费者并使用兼容代码回退。')
