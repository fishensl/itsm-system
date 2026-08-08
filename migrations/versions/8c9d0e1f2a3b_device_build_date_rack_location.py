"""device build_date and rack location

V24: 导出筛选字段支撑 —— devices.build_date（建设时间）+ racks.location（机房位置）。

幂等：先查后加，PG/SQLite 通用。

Revision ID: 8c9d0e1f2a3b
Revises: 7b8c9d0e1f2a
Create Date: 2026-08-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '8c9d0e1f2a3b'
down_revision = '7b8c9d0e1f2a'
branch_labels = None
depends_on = None


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return set()
    return {c['name'] for c in insp.get_columns(table)}


def _add_column_if_missing(table, column, column_type):
    bind = op.get_bind()
    cols = _existing_columns(bind, table)
    if column not in cols:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column(column, column_type, nullable=True))


def upgrade():
    _add_column_if_missing('devices', 'build_date', sa.Date())
    _add_column_if_missing('racks', 'location', sa.String(length=128))


def downgrade():
    bind = op.get_bind()
    for table, column in [('devices', 'build_date'), ('racks', 'location')]:
        if column in _existing_columns(bind, table):
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.drop_column(column)
