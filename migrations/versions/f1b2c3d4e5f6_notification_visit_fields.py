"""notification visit and fault location fields

Revision ID: f1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa


revision = 'f1b2c3d4e5f6'
down_revision = 'f0a1b2c3d4e5'
branch_labels = None
depends_on = None


def _columns(bind, table):
    return {column['name'] for column in sa.inspect(bind).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    ticket_columns = _columns(bind, 'tickets')
    with op.batch_alter_table('tickets') as batch_op:
        if 'fault_location' not in ticket_columns:
            batch_op.add_column(sa.Column(
                'fault_location', sa.String(length=256), nullable=False,
                server_default=''))
        if 'visit_at' not in ticket_columns:
            batch_op.add_column(sa.Column('visit_at', sa.DateTime(), nullable=True))

    task_columns = _columns(bind, 'inspection_tasks')
    if 'visit_at' not in task_columns:
        with op.batch_alter_table('inspection_tasks') as batch_op:
            batch_op.add_column(sa.Column('visit_at', sa.DateTime(), nullable=True))


def downgrade():
    bind = op.get_bind()
    task_columns = _columns(bind, 'inspection_tasks')
    if 'visit_at' in task_columns:
        with op.batch_alter_table('inspection_tasks') as batch_op:
            batch_op.drop_column('visit_at')

    ticket_columns = _columns(bind, 'tickets')
    with op.batch_alter_table('tickets') as batch_op:
        if 'visit_at' in ticket_columns:
            batch_op.drop_column('visit_at')
        if 'fault_location' in ticket_columns:
            batch_op.drop_column('fault_location')
