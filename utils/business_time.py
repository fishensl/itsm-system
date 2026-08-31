# -*- coding: utf-8 -*-
"""统一业务时间计算。

新计时事件统一使用 UTC（数据库中为 naive UTC）；展示和工作时段按
Asia/Shanghai 计算。任务安排的历史字段仍是北京本地 naive 时间，调用方
通过 ``business_seconds_local`` 兼容，避免改变既有统计。
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


UTC = timezone.utc
BEIJING = ZoneInfo('Asia/Shanghai')
SECONDS_PER_PERSON_DAY = 8 * 60 * 60


@dataclass(frozen=True)
class BusinessCalendar:
    timezone_name: str = 'Asia/Shanghai'
    weekdays: tuple = (0, 1, 2, 3, 4)
    periods: tuple = (
        (time(8, 30), time(12, 0)),
        (time(13, 30), time(17, 30)),
    )
    version: int = 1

    @property
    def timezone(self):
        return ZoneInfo(self.timezone_name)


DEFAULT_CALENDAR = BusinessCalendar()


def _as_utc(value):
    """将 aware/naive datetime 归一为 aware UTC；naive 按 UTC 解释。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _merge_intervals(intervals, lower, upper):
    normalized = []
    for item in intervals or ():
        if not item or len(item) != 2:
            continue
        start, end = _as_utc(item[0]), _as_utc(item[1])
        if not start or not end:
            continue
        start, end = max(start, lower), min(end, upper)
        if end > start:
            normalized.append((start, end))
    normalized.sort(key=lambda value: value[0])
    merged = []
    for start, end in normalized:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def overlap_seconds(interval, exclusions):
    """返回自然时间区间与排除区间的合并重叠秒数。"""
    if not interval or len(interval) != 2:
        return 0
    start, end = _as_utc(interval[0]), _as_utc(interval[1])
    if not start or not end or end <= start:
        return 0
    return int(sum((right - left).total_seconds()
                   for left, right in _merge_intervals(exclusions, start, end)))


def _business_seconds_without_exclusions(start_utc, end_utc, calendar):
    start_local = start_utc.astimezone(calendar.timezone)
    end_local = end_utc.astimezone(calendar.timezone)
    total = 0
    current_day = start_local.date()
    end_day = end_local.date()
    while current_day <= end_day:
        if current_day.weekday() in calendar.weekdays:
            for period_start, period_end in calendar.periods:
                window_start = datetime.combine(
                    current_day, period_start, tzinfo=calendar.timezone)
                window_end = datetime.combine(
                    current_day, period_end, tzinfo=calendar.timezone)
                overlap_start = max(start_local, window_start)
                overlap_end = min(end_local, window_end)
                if overlap_end > overlap_start:
                    total += int((overlap_end - overlap_start).total_seconds())
        current_day += timedelta(days=1)
    return total


def business_seconds(start_utc, end_utc, calendar=None, exclusions=()):
    """计算 UTC 边界之间的北京工作时间秒数，并扣除排除区间。

    ``exclusions`` 使用相同 UTC 语义，重叠区间会先合并，避免重复扣除。
    当前日历不处理法定节假日；历史快照通过 ``calendar.version`` 固定口径。
    """
    calendar = calendar or DEFAULT_CALENDAR
    start, end = _as_utc(start_utc), _as_utc(end_utc)
    if not start or not end or end <= start:
        return 0
    total = _business_seconds_without_exclusions(start, end, calendar)
    for excluded_start, excluded_end in _merge_intervals(exclusions, start, end):
        total -= _business_seconds_without_exclusions(
            excluded_start, excluded_end, calendar)
    return max(int(total), 0)


def business_seconds_local(start_local, end_local, calendar=None, exclusions=()):
    """兼容北京本地 naive 时间字段（任务安排等旧数据）。"""
    calendar = calendar or DEFAULT_CALENDAR

    def to_utc(value):
        if value is None:
            return None
        aware = value.replace(tzinfo=calendar.timezone) if value.tzinfo is None else value
        return aware.astimezone(UTC)

    converted = []
    for start, end in exclusions or ():
        converted.append((to_utc(start), to_utc(end)))
    return business_seconds(to_utc(start_local), to_utc(end_local),
                            calendar=calendar, exclusions=converted)


def beijing_naive_to_utc(value):
    """北京本地 datetime（naive/aware）转为数据库使用的 naive UTC。"""
    if value is None:
        return None
    aware = value.replace(tzinfo=BEIJING) if value.tzinfo is None else value
    return aware.astimezone(UTC).replace(tzinfo=None)


def parse_beijing_to_utc(value):
    """解析 datetime-local/常用文本并转换为 naive UTC。"""
    if not value:
        return None
    if isinstance(value, datetime):
        return beijing_naive_to_utc(value)
    text = str(value).strip()
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S'):
        try:
            return beijing_naive_to_utc(datetime.strptime(text, fmt))
        except (TypeError, ValueError):
            continue
    return None


def format_duration(seconds):
    """将整数秒格式化为统一的小时/分钟文本。"""
    if seconds is None:
        return ''
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return '<1分钟'
    total_minutes = seconds // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f'{hours}小时{minutes}分钟'
    if hours:
        return f'{hours}小时'
    return f'{minutes}分钟'


def person_days(seconds, hours_per_day=8):
    """整数秒按固定工时折算人天。"""
    if seconds is None:
        return None
    divisor = float(hours_per_day) * 60 * 60
    if divisor <= 0:
        raise ValueError('hours_per_day 必须大于 0')
    return round(max(int(seconds), 0) / divisor, 2)


def format_beijing(value, fmt='%Y-%m-%d %H:%M'):
    """将 UTC datetime 格式化为北京时间；naive 按 UTC 解释。"""
    utc_value = _as_utc(value)
    return utc_value.astimezone(BEIJING).strftime(fmt) if utc_value else ''
