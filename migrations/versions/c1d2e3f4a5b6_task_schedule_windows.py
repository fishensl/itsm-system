"""inspection task supervisor schedule window

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-08-26

``planned_start``/``planned_end`` remain the contract or frequency requirement
window.  The new nullable columns store the supervisor's execution window.
Existing rows are intentionally not backfilled because their planned dates do
not prove that a supervisor made a separate schedule decision.
"""

from alembic import op
import sqlalchemy as sa


revision = 'c1d2e3f4a5b6'
down_revision = 'b0c1d2e3f4a5'
branch_labels = None
depends_on = None


def _existing_columns(bind, table_name):
    return {column['name'] for column in sa.inspect(bind).get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    columns = _existing_columns(bind, 'inspection_tasks')
    with op.batch_alter_table('inspection_tasks', schema=None) as batch_op:
        if 'scheduled_start' not in columns:
            batch_op.add_column(sa.Column('scheduled_start', sa.Date(), nullable=True))
        if 'scheduled_end' not in columns:
            batch_op.add_column(sa.Column('scheduled_end', sa.Date(), nullable=True))


def downgrade():
    bind = op.get_bind()
    columns = _existing_columns(bind, 'inspection_tasks')
    with op.batch_alter_table('inspection_tasks', schema=None) as batch_op:
        if 'scheduled_end' in columns:
            batch_op.drop_column('scheduled_end')
        if 'scheduled_start' in columns:
            batch_op.drop_column('scheduled_start')
