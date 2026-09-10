"""Repair legacy inspection tasks from actual submission history.

Revision ID: c8e10f26a903
Revises: f2a3b4c5d6e7
"""
from datetime import timedelta
import logging

from alembic import op
import sqlalchemy as sa

revision = 'c8e10f26a903'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def repair(bind):
    """Use version timestamps only; never infer submission from record creation."""
    from utils.business_time import business_seconds_local, person_days

    names = set(sa.inspect(bind).get_table_names())
    if not {'inspection_tasks', 'inspections', 'submission_versions'} <= names:
        return 0
    meta = sa.MetaData()
    tasks = sa.Table('inspection_tasks', meta, autoload_with=bind)
    records = sa.Table('inspections', meta, autoload_with=bind)
    versions = sa.Table('submission_versions', meta, autoload_with=bind)
    latest_record = dict(bind.execute(sa.select(
        records.c.task_id, sa.func.max(records.c.id)).where(
        records.c.task_id.is_not(None)).group_by(records.c.task_id)).all())
    history = {}
    for row in bind.execute(sa.select(
            records.c.task_id, records.c.id.label('record_id'),
            records.c.review_status.label('record_status'),
            versions.c.id, versions.c.submitted_at, versions.c.review_status,
    ).join(versions, sa.and_(versions.c.entity_id == records.c.id,
                            versions.c.entity_type == 'inspection'))
            .order_by(versions.c.submitted_at, versions.c.id)).mappings():
        history.setdefault(row['task_id'], []).append(row)
    changed = 0
    for task in bind.execute(sa.select(tasks).where(tasks.c.status.in_(
            ['执行中', '待审核', '退回修改', '已完成']))).mappings():
        rows = history.get(task['id'], [])
        if not rows or not task['actual_start'] or any(row['submitted_at'] is None for row in rows):
            continue
        first, last = rows[0], rows[-1]
        # A newer draft or conflicting review state may represent real rework.
        if (last['record_id'] != latest_record.get(task['id']) or
                last['record_status'] != last['review_status']):
            continue
        status = {'已退回': '退回修改', '待审核': '待审核', '已通过': '已完成'}.get(last['review_status'])
        if status is None or (task['status'] == '已完成') != (status == '已完成'):
            continue
        if first['review_status'] not in {'已退回', '待审核', '已通过'}:
            continue
        # SubmissionVersion is UTC naive; task actual_* uses Beijing local naive.
        end = first['submitted_at'] + timedelta(hours=8)
        if end < task['actual_start']:
            continue  # Explicitly restarted task, or inconsistent historical clock.
        if task['actual_end'] and task['actual_end'] < end:
            continue  # Preserve an independently recorded earlier implementation end.
        effort = person_days(business_seconds_local(task['actual_start'], end))
        if (task['actual_end'] == end and task['actual_effort'] == effort and task['status'] == status):
            continue
        bind.execute(tasks.update().where(tasks.c.id == task['id']).values(
            status=status, actual_end=end, actual_effort=effort))
        changed += 1
    logging.getLogger('alembic.runtime.migration').info(
        'Repaired %s inspection task submission boundaries; no notifications sent', changed)
    return changed


def upgrade():
    repair(op.get_bind())


def downgrade():
    # Do not restore known incorrect timing; paired deployment backup holds old data.
    pass
