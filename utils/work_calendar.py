# -*- coding: utf-8 -*-
"""中国法定节假日与调休工作日的单一数据源。

年度安排只在国务院办公厅正式通知后录入。未覆盖年份由业务时间引擎按
周一至周五工作、周末休息的基础周历处理，避免猜测尚未发布的调休日期。
"""
from datetime import date, timedelta


CALENDAR_VERSION = 'cn-gov-2026-v1'
BUSINESS_CALENDAR_VERSION = 2
CALENDAR_SOURCE = (
    '国务院办公厅关于2026年部分节假日安排的通知'
    '（国办发明电〔2025〕7号）'
)


def _date_range(start, end):
    current = date.fromisoformat(start)
    finish = date.fromisoformat(end)
    while current <= finish:
        yield current
        current += timedelta(days=1)


_HOLIDAY_PERIODS_2026 = (
    ('2026-01-01', '2026-01-03', '元旦'),
    ('2026-02-15', '2026-02-23', '春节'),
    ('2026-04-04', '2026-04-06', '清明节'),
    ('2026-05-01', '2026-05-05', '劳动节'),
    ('2026-06-19', '2026-06-21', '端午节'),
    ('2026-09-25', '2026-09-27', '中秋节'),
    ('2026-10-01', '2026-10-07', '国庆节'),
)

HOLIDAY_NAMES = {
    day: name
    for start, end, name in _HOLIDAY_PERIODS_2026
    for day in _date_range(start, end)
}

MAKEUP_WORKDAY_NAMES = {
    date(2026, 1, 4): '元旦调休上班',
    date(2026, 2, 14): '春节调休上班',
    date(2026, 2, 28): '春节调休上班',
    date(2026, 5, 9): '劳动节调休上班',
    date(2026, 9, 20): '国庆节调休上班',
    date(2026, 10, 10): '国庆节调休上班',
}

HOLIDAYS = frozenset(HOLIDAY_NAMES)
MAKEUP_WORKDAYS = frozenset(MAKEUP_WORKDAY_NAMES)
COVERED_YEARS = (2026,)


def work_calendar_payload():
    """返回前端日历标记所需的稳定 JSON 数据。"""
    return {
        'version': CALENDAR_VERSION,
        'source': CALENDAR_SOURCE,
        'covered_years': list(COVERED_YEARS),
        'holidays': [
            {'date': day.isoformat(), 'name': HOLIDAY_NAMES[day]}
            for day in sorted(HOLIDAYS)
        ],
        'makeup_workdays': [
            {'date': day.isoformat(), 'name': MAKEUP_WORKDAY_NAMES[day]}
            for day in sorted(MAKEUP_WORKDAYS)
        ],
    }
