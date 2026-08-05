"""fix missing review columns

V23.1: 修复服务器增量升级漏列问题。

背景：9a8b7c6d5e4f / 5f4e3d2c1b0a 两个已发布的迁移文件在后续提交中被修改
（追加加列逻辑），而服务器 alembic_version 早已越过这两个版本 → 修改后的
加列逻辑永不执行，导致 PG 上 submission_versions 缺 revision_requirements /
review_checklist_json 列，v2.3 代码访问缺列 → /api/inspections/<id>/versions 500。

本迁移幂等补齐所有相关列（先查后加，PG/SQLite 通用）：
- submission_versions: revision_requirements / review_checklist_json
- inspections: submitted_report（兜底）
- inspection_task_templates: required_assets_json（兜底）

Revision ID: 6f5e4d3c2b1a
Revises: 5f4e3d2c1b0a
Create Date: 2026-08-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '6f5e4d3c2b1a'
down_revision = '5f4e3d2c1b0a'
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
    _add_column_if_missing('submission_versions', 'revision_requirements', sa.Text())
    _add_column_if_missing('submission_versions', 'review_checklist_json', sa.Text())
    _add_column_if_missing('inspections', 'submitted_report', sa.String(length=256))
    _add_column_if_missing('inspection_task_templates', 'required_assets_json', sa.Text())


def downgrade():
    # 这些列由历史迁移负责；本迁移仅为补齐缺失，降级不删列（避免破坏已补库）
    pass
