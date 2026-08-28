"""topology template type and version

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-08-28
"""

from alembic import op
import sqlalchemy as sa


revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def _columns(bind):
    return {column['name'] for column in sa.inspect(bind).get_columns('topologies')}


def upgrade():
    bind = op.get_bind()
    columns = _columns(bind)
    with op.batch_alter_table('topologies', schema=None) as batch_op:
        if 'template_type' not in columns:
            batch_op.add_column(sa.Column(
                'template_type', sa.String(length=16), nullable=False,
                server_default='legacy'))
        if 'template_version' not in columns:
            batch_op.add_column(sa.Column(
                'template_version', sa.Integer(), nullable=False,
                server_default='1'))


def downgrade():
    bind = op.get_bind()
    columns = _columns(bind)
    with op.batch_alter_table('topologies', schema=None) as batch_op:
        if 'template_version' in columns:
            batch_op.drop_column('template_version')
        if 'template_type' in columns:
            batch_op.drop_column('template_type')
