"""backfill closed tickets into fault records

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-08-29
"""

from alembic import op
import sqlalchemy as sa


revision = 'c7d8e9f0a1b2'
down_revision = 'b6c7d8e9f0a1'
branch_labels = None
depends_on = None


def upgrade():
    """幂等补齐历史已关闭工单；已有故障转工单桥接记录不重复创建。"""
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if not {'tickets', 'faults'} <= tables:
        return
    op.execute(sa.text("""
        INSERT INTO faults (
            customer_id, ticket_id, title, handler, fault_time, fault_type,
            fault_description, impact_range, fault_cause, solution, result,
            recovery_time, report_file, created_at,
            fault_category_level1, fault_category_level2, fault_category_level3,
            symptoms_json, affected_components_json, resolution_steps_json,
            root_cause_category, severity_level, impact_scope, normalized_tags
        )
        SELECT
            t.customer_id, t.id, t.title, COALESCE(t.assigned_to, ''),
            COALESCE(t.created_at, CURRENT_TIMESTAMP),
            COALESCE(NULLIF(t.fault_category_level3, ''),
                     NULLIF(t.fault_category_level2, ''),
                     NULLIF(t.fault_category_level1, ''), ''),
            COALESCE(t.description, ''), COALESCE(t.impact_scope, ''),
            COALESCE(t.diagnosis, ''), COALESCE(t.solution, ''), '已解决',
            COALESCE(t.completed_at, t.accept_at, t.audit_at, t.created_at,
                     CURRENT_TIMESTAMP),
            COALESCE(t.report_file, ''), CURRENT_TIMESTAMP,
            COALESCE(t.fault_category_level1, ''),
            COALESCE(t.fault_category_level2, ''),
            COALESCE(t.fault_category_level3, ''),
            COALESCE(t.symptoms_json, '[]'),
            COALESCE(t.affected_components_json, '[]'),
            COALESCE(t.resolution_steps_json, '[]'),
            COALESCE(t.root_cause_category, ''),
            COALESCE(t.severity_level, ''),
            COALESCE(t.impact_scope, ''),
            COALESCE(t.normalized_tags, '')
          FROM tickets t
         WHERE t.status IN ('已关闭', '已完成')
           AND NOT EXISTS (
               SELECT 1 FROM faults f WHERE f.ticket_id = t.id
           )
    """))


def downgrade():
    # 数据闭环回填不可逆：无法可靠区分迁移生成记录与既有人工故障记录。
    pass
