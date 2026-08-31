from datetime import datetime, timezone

import pytest

from utils.business_time import (
    business_seconds,
    business_seconds_local,
    format_duration,
    overlap_seconds,
    person_days,
)


def _utc(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_business_seconds_uses_beijing_work_periods():
    # 北京周一 08:00-18:00 = 7.5 个工作小时。
    assert business_seconds(_utc('2026-08-24T00:00:00'),
                            _utc('2026-08-24T10:00:00')) == 7.5 * 3600


def test_business_seconds_skips_weekend_and_merges_exclusions():
    start = _utc('2026-08-21T00:30:00')  # 北京周五 08:30
    end = _utc('2026-08-24T09:30:00')    # 北京周一 17:30
    exclusions = [
        (_utc('2026-08-24T01:00:00'), _utc('2026-08-24T02:00:00')),
        (_utc('2026-08-24T01:30:00'), _utc('2026-08-24T02:30:00')),
    ]
    # 两个完整工作日 15h，排除区间合并后扣 1.5h。
    assert business_seconds(start, end, exclusions=exclusions) == 13.5 * 3600


def test_business_seconds_uses_statutory_holidays_and_makeup_workdays():
    # 2026-06-19（周五）是端午节，不应计入实施耗时。
    assert business_seconds_local(
        datetime(2026, 6, 19, 8, 30),
        datetime(2026, 6, 19, 17, 30),
    ) == 0
    # 2026-02-14（周六）为春节调休上班日，应按正常工作时段计入。
    assert business_seconds_local(
        datetime(2026, 2, 14, 8, 30),
        datetime(2026, 2, 14, 17, 30),
    ) == 7.5 * 3600
    # 尚无正式年度安排时仍按基础周历，不能臆造调休。
    assert business_seconds_local(
        datetime(2027, 2, 13, 8, 30),
        datetime(2027, 2, 13, 17, 30),
    ) == 0


def test_local_compatibility_matches_existing_task_semantics():
    assert business_seconds_local(
        datetime(2026, 8, 24, 8, 30),
        datetime(2026, 8, 24, 17, 30),
    ) == 7.5 * 3600


def test_overlap_duration_and_person_days_helpers():
    start = _utc('2026-08-24T00:00:00')
    end = _utc('2026-08-24T08:00:00')
    assert overlap_seconds((start, end), [
        (_utc('2026-08-24T01:00:00'), _utc('2026-08-24T03:00:00')),
        (_utc('2026-08-24T02:00:00'), _utc('2026-08-24T04:00:00')),
    ]) == 3 * 3600
    assert format_duration(8 * 3600 + 4 * 60) == '8小时4分钟'
    assert person_days(8 * 3600) == 1
    assert person_days(4 * 3600) == 0.5
    with pytest.raises(ValueError):
        person_days(1, hours_per_day=0)
