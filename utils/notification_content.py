"""Shared notification presentation; task timing keeps the existing work-hour rule."""
from types import SimpleNamespace


def single_line(value):
    return ' '.join(str(value or '').split())


def compact_content(title, content):
    """The transport already renders the subject. Keep each body line only once."""
    result, seen = [], {single_line(title)}
    for line in str(content or '').splitlines():
        line = line.strip()
        if line and line not in seen:
            result.append(line)
            seen.add(line)
    return '\n'.join(result)


def inspection_fields(task, assignee_name='', status=None):
    from services.task_schedule_service import (
        task_actual_duration_seconds, format_task_duration,
    )
    customer = getattr(task, 'customer_rel', None)
    assignee = getattr(task, 'assignee_rel', None)
    start, end = getattr(task, 'scheduled_start', None), getattr(task, 'scheduled_end', None)
    period = f'{start} 至 {end}' if start and end else (f'{start} 起' if start else f'{end} 止' if end else '')
    timing = SimpleNamespace(actual_start=getattr(task, 'actual_start', None),
        actual_end=getattr(task, 'actual_end', None), actual_effort=getattr(task, 'actual_effort', None),
        status=getattr(task, 'status', ''))
    from utils import constants as C
    show_end = timing.status in {C.TASK_REVIEWING, C.TASK_RETURNED, C.TASK_DONE}
    seconds = task_actual_duration_seconds(timing) if show_end else None
    from utils.business_time import person_days
    effort = person_days(seconds) if seconds is not None else timing.actual_effort
    fields = [
        ('计划时间', period),
        ('巡检地点', single_line(getattr(customer, 'name', ''))),
        ('巡检工程师', single_line(assignee_name or getattr(assignee, 'realname', '') or getattr(assignee, 'username', ''))),
        ('任务状态', timing.status if status is None else status),
        ('实施开始', timing.actual_start.strftime('%Y-%m-%d %H:%M') if timing.actual_start else ''),
    ]
    if show_end:
        fields += [
            ('实施结束', timing.actual_end.strftime('%Y-%m-%d %H:%M') if timing.actual_end else ''),
            ('累计耗时', format_task_duration(seconds) if seconds is not None else ''),
            ('累计人天', f'{effort:.2f} 人天' if effort is not None else ''),
        ]
    return fields


def ticket_subject(ticket, customer_name=''):
    customer = getattr(ticket, 'customer_rel', None)
    customer_name = single_line(customer_name or getattr(customer, 'name', '') or getattr(ticket, 'customer_name_text', ''))
    name = single_line(ticket.title)
    if customer_name and not name.startswith(customer_name):
        name = customer_name + name
    return name if name.endswith('处置') else name + '处置'


def ticket_fields(ticket, assignee_name='', status=None, customer_name=''):
    from utils import constants as C
    from utils.business_time import format_beijing
    from services.ticket_timing_service import ticket_timing_payload
    customer = getattr(ticket, 'customer_rel', None)
    customer_name = single_line(customer_name or getattr(customer, 'name', '') or getattr(ticket, 'customer_name_text', ''))
    raw_status = ticket.status
    display_status = C.TASK_DONE if raw_status in {C.TICKET_CHECKED, C.TICKET_CLOSED} else raw_status
    fields = [
        ('计划时间', format_beijing(ticket.visit_at, '%Y-%m-%d %H:%M') if ticket.visit_at else ''),
        ('故障地点', single_line(ticket.fault_location or customer_name)),
        ('处置工程师', single_line(assignee_name or ticket.assigned_to)),
        ('任务状态', display_status if status is None else status),
        ('处置开始', format_beijing(ticket.started_at, '%Y-%m-%d %H:%M') if ticket.started_at else ''),
    ]
    if raw_status in {C.TICKET_CHECKED, C.TICKET_CLOSED}:
        timing = ticket_timing_payload(ticket)
        if timing['started_at'] and timing['finished_at']:
            fields[-1] = ('处置开始', timing['started_at'])
            fields += [('处置结束', timing['finished_at']),
                ('累计耗时', timing['handling_duration_text']),
                ('累计人天', f"{timing['handling_person_days']:.2f} 人天")]
    return fields
