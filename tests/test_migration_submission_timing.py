"""Legacy persisted states must be repaired, not only future transitions."""
from datetime import datetime
from importlib import import_module

import pytest
import sqlalchemy as sa


@pytest.mark.parametrize('status,review,expected', [
    ('执行中', '已退回', '退回修改'), ('待审核', '待审核', '待审核'),
    ('已完成', '已通过', '已完成'), ('退回修改', '已退回', '退回修改'),
])
def test_legacy_timing_repair_uses_first_submission_and_is_idempotent(status, review, expected):
    migration = import_module('migrations.versions.c8e10f26a903_repair_inspection_submission_timing')
    engine = sa.create_engine('sqlite://')
    meta = sa.MetaData()
    task = sa.Table('inspection_tasks', meta, sa.Column('id', sa.Integer, primary_key=True),
                    sa.Column('status', sa.String), sa.Column('actual_start', sa.DateTime),
                    sa.Column('actual_end', sa.DateTime), sa.Column('actual_effort', sa.Float))
    record = sa.Table('inspections', meta, sa.Column('id', sa.Integer, primary_key=True),
                      sa.Column('task_id', sa.Integer), sa.Column('review_status', sa.String))
    version = sa.Table('submission_versions', meta, sa.Column('id', sa.Integer, primary_key=True),
                       sa.Column('entity_id', sa.Integer), sa.Column('entity_type', sa.String),
                       sa.Column('submitted_at', sa.DateTime), sa.Column('review_status', sa.String))
    meta.create_all(engine)
    start = datetime(2026, 9, 8, 8, 22)
    first_utc = datetime(2026, 9, 8, 0, 49)
    with engine.begin() as conn:
        conn.execute(task.insert(), [dict(id=n, status=status, actual_start=start,
                                         actual_end=datetime(2026, 9, 10) if status == '已完成' else None,
                                         actual_effort=2.31) for n in range(1, 6)])
        conn.execute(record.insert(), [dict(id=n, task_id=n, review_status=review) for n in range(1, 6)])
        conn.execute(version.insert(), [dict(id=n, entity_id=n, entity_type='inspection',
                                            submitted_at=first_utc, review_status=review) for n in (1, 3, 4, 5)])
        # Later resubmission must not replace the first submission boundary.
        conn.execute(version.insert(), dict(id=6, entity_id=1, entity_type='inspection',
                                            submitted_at=datetime(2026, 9, 9, 3), review_status=review))
        conn.execute(record.insert(), dict(id=7, task_id=3, review_status=''))  # newer draft
        conn.execute(task.update().where(task.c.id == 4).values(actual_start=datetime(2026, 9, 9)))
        conn.execute(task.update().where(task.c.id == 5).values(actual_end=datetime(2026, 9, 8, 8, 40)))
        assert migration.repair(conn) == 1
        repaired = conn.execute(sa.select(task).where(task.c.id == 1)).mappings().one()
        assert repaired['status'] == expected
        assert repaired['actual_end'] == datetime(2026, 9, 8, 8, 49)
        assert repaired['actual_effort'] == 0.04  # 08:30–08:49 business time, 8h/person-day.
        assert migration.repair(conn) == 0
        for n in (2, 3, 4, 5):
            assert conn.execute(sa.select(task.c.actual_effort).where(task.c.id == n)).scalar_one() == 2.31
    engine.dispose()
