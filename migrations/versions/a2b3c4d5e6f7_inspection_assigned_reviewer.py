"""inspection assigned reviewer workflow

Revision ID: a2b3c4d5e6f7
Revises: f1b2c3d4e5f6
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa


revision = 'a2b3c4d5e6f7'
down_revision = 'f1b2c3d4e5f6'
branch_labels = None
depends_on = None


def _columns(bind, table):
    return {column['name'] for column in sa.inspect(bind).get_columns(table)}


def _indexes(bind, table):
    return {index['name'] for index in sa.inspect(bind).get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    inspection_columns = _columns(bind, 'inspections')
    if 'reviewer_id' not in inspection_columns:
        with op.batch_alter_table('inspections') as batch_op:
            batch_op.add_column(sa.Column('reviewer_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_inspections_reviewer_id', 'users', ['reviewer_id'], ['id'])
    if 'ix_inspections_reviewer_id' not in _indexes(bind, 'inspections'):
        op.create_index('ix_inspections_reviewer_id', 'inspections', ['reviewer_id'])

    version_columns = _columns(bind, 'submission_versions')
    if 'assigned_reviewer_id' not in version_columns:
        with op.batch_alter_table('submission_versions') as batch_op:
            batch_op.add_column(sa.Column(
                'assigned_reviewer_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_submission_versions_assigned_reviewer_id',
                'users', ['assigned_reviewer_id'], ['id'])


def downgrade():
    bind = op.get_bind()
    version_columns = _columns(bind, 'submission_versions')
    if 'assigned_reviewer_id' in version_columns:
        with op.batch_alter_table('submission_versions') as batch_op:
            batch_op.drop_constraint(
                'fk_submission_versions_assigned_reviewer_id', type_='foreignkey')
            batch_op.drop_column('assigned_reviewer_id')

    inspection_columns = _columns(bind, 'inspections')
    if 'reviewer_id' in inspection_columns:
        if 'ix_inspections_reviewer_id' in _indexes(bind, 'inspections'):
            op.drop_index('ix_inspections_reviewer_id', table_name='inspections')
        with op.batch_alter_table('inspections') as batch_op:
            batch_op.drop_constraint('fk_inspections_reviewer_id', type_='foreignkey')
            batch_op.drop_column('reviewer_id')
