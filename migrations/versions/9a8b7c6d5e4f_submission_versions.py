"""submission versions + inspection submitted report

V21: 巡检/工单审核闭环版本化：
- 新建 submission_versions 表：每次"上传报告+提交审核"追加一条版本，
  审核结果/意见挂在版本上，形成完整可复查的提交历史。
- inspections 表加 submitted_report 列：工程师上传的最新现场报告指针
  （历史版本存 submission_versions.report_file）。

Revision ID: 9a8b7c6d5e4f
Revises: d3e4f5a6b7c8
Create Date: 2026-08-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '9a8b7c6d5e4f'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def _existing_tables(bind):
    insp = sa.inspect(bind)
    return set(insp.get_table_names())


def _existing_columns(bind, table):
    insp = sa.inspect(bind)
    return {c['name'] for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    tables = _existing_tables(bind)
    if 'submission_versions' not in tables:
        op.create_table(
            'submission_versions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('entity_type', sa.String(length=16), nullable=True),
            sa.Column('entity_id', sa.Integer(), nullable=True),
            sa.Column('version_no', sa.Integer(), nullable=True),
            sa.Column('report_file', sa.String(length=256), nullable=True),
            sa.Column('content_json', sa.Text(), nullable=True),
            sa.Column('submitted_by', sa.Integer(), nullable=True),
            sa.Column('submitted_at', sa.DateTime(), nullable=True),
            sa.Column('review_status', sa.String(length=16), nullable=True),
            sa.Column('reviewed_by', sa.Integer(), nullable=True),
            sa.Column('reviewed_at', sa.DateTime(), nullable=True),
            sa.Column('review_comment', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], name='fk_sv_reviewed_by'),
            sa.ForeignKeyConstraint(['submitted_by'], ['users.id'], name='fk_sv_submitted_by'),
            sa.PrimaryKeyConstraint('id', name='pk_submission_versions'),
            sa.UniqueConstraint('entity_type', 'entity_id', 'version_no',
                                name='uq_submission_versions_entity_version'),
        )
        op.create_index('ix_submission_versions_entity', 'submission_versions',
                        ['entity_type', 'entity_id'], unique=False)
        op.create_index('ix_submission_versions_review_status', 'submission_versions',
                        ['review_status'], unique=False)
    cols = _existing_columns(bind, 'inspections')
    if 'submitted_report' not in cols:
        with op.batch_alter_table('inspections', schema=None) as batch_op:
            batch_op.add_column(sa.Column('submitted_report', sa.String(length=256), nullable=True))


def downgrade():
    bind = op.get_bind()
    cols = _existing_columns(bind, 'inspections')
    if 'submitted_report' in cols:
        with op.batch_alter_table('inspections', schema=None) as batch_op:
            batch_op.drop_column('submitted_report')
    tables = _existing_tables(bind)
    if 'submission_versions' in tables:
        op.drop_index('ix_submission_versions_review_status', table_name='submission_versions')
        op.drop_index('ix_submission_versions_entity', table_name='submission_versions')
        op.drop_table('submission_versions')
