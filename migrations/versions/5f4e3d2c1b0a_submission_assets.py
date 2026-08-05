"""submission assets + task template required assets

V22: 巡检提交资料扩展：
- 新建 submission_assets 表：每轮提交（submission_versions）附带的资料明细
  （config_zip 完整配置包 / config_text 核心设备文本配置 / topology 拓扑图 /
   asset_list 资产清单；skip_reason 记录必传项豁免原因）。
- inspection_task_templates 加 required_assets_json：模板级提交必传配置。

Revision ID: 5f4e3d2c1b0a
Revises: 9a8b7c6d5e4f
Create Date: 2026-08-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '5f4e3d2c1b0a'
down_revision = '9a8b7c6d5e4f'
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
    if 'submission_assets' not in tables:
        op.create_table(
            'submission_assets',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('version_id', sa.Integer(), nullable=False),
            sa.Column('asset_type', sa.String(length=32), nullable=True),
            sa.Column('file_path', sa.String(length=256), nullable=True),
            sa.Column('file_name', sa.String(length=256), nullable=True),
            sa.Column('device_id', sa.Integer(), nullable=True),
            sa.Column('content_text', sa.Text(), nullable=True),
            sa.Column('target_id', sa.Integer(), nullable=True),
            sa.Column('skip_reason', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['device_id'], ['devices.id'], name='fk_sa_device_id'),
            sa.ForeignKeyConstraint(['version_id'], ['submission_versions.id'], name='fk_sa_version_id'),
            sa.PrimaryKeyConstraint('id', name='pk_submission_assets'),
        )
        op.create_index('ix_submission_assets_version_id', 'submission_assets',
                        ['version_id'], unique=False)
        op.create_index('ix_submission_assets_asset_type', 'submission_assets',
                        ['asset_type'], unique=False)
    cols = _existing_columns(bind, 'inspection_task_templates')
    if 'required_assets_json' not in cols:
        with op.batch_alter_table('inspection_task_templates', schema=None) as batch_op:
            batch_op.add_column(sa.Column('required_assets_json', sa.Text(), nullable=True))
    sv_cols = _existing_columns(bind, 'submission_versions')
    if 'review_checklist_json' not in sv_cols:
        with op.batch_alter_table('submission_versions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('review_checklist_json', sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    sv_cols = _existing_columns(bind, 'submission_versions')
    if 'review_checklist_json' in sv_cols:
        with op.batch_alter_table('submission_versions', schema=None) as batch_op:
            batch_op.drop_column('review_checklist_json')
    cols = _existing_columns(bind, 'inspection_task_templates')
    if 'required_assets_json' in cols:
        with op.batch_alter_table('inspection_task_templates', schema=None) as batch_op:
            batch_op.drop_column('required_assets_json')
    tables = _existing_tables(bind)
    if 'submission_assets' in tables:
        op.drop_index('ix_submission_assets_asset_type', table_name='submission_assets')
        op.drop_index('ix_submission_assets_version_id', table_name='submission_assets')
        op.drop_table('submission_assets')
