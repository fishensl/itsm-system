# -*- coding: utf-8 -*-
"""工单/故障统一计时服务。"""
from datetime import datetime

from models import (
    db,
    Ticket,
    TicketSuspend,
    TicketTimingEvent,
    TicketTimingSnapshot,
    User,
)
from utils.business_time import (
    DEFAULT_CALENDAR,
    beijing_naive_to_utc,
    business_seconds,
    format_beijing,
    format_duration,
    person_days,
)
from utils.constants import (
    FAULT_RESOLVED,
    TICKET_CLOSED,
)
from utils.json_fields import dumps_json


ALGORITHM_VERSION = 1
TIMING_EVENT_TYPES = frozenset({
    'start', 'submit', 'audit_reject', 'audit_approve', 'suspend', 'resume',
    'accept', 'close', 'reopen',
})
FINISH_EVENT_TYPES = frozenset({'audit_approve', 'close'})


def current_cycle(ticket_id):
    event_cycle = (db.session.query(db.func.max(TicketTimingEvent.cycle_no))
                   .filter(TicketTimingEvent.ticket_id == ticket_id).scalar())
    snapshot_cycle = (db.session.query(db.func.max(TicketTimingSnapshot.cycle_no))
                      .filter(TicketTimingSnapshot.ticket_id == ticket_id).scalar())
    return max(int(event_cycle or 1), int(snapshot_cycle or 1))


def record_ticket_event(ticket, event_type, actor_name='', from_status='', to_status='',
                        occurred_at=None, source='api', metadata=None, cycle_no=None,
                        idempotent=False):
    if event_type not in TIMING_EVENT_TYPES:
        raise ValueError(f'未知计时事件: {event_type}')
    occurred_at = occurred_at or datetime.utcnow()
    cycle_no = int(cycle_no or current_cycle(ticket.id))
    if idempotent:
        existing = TicketTimingEvent.query.filter_by(
            ticket_id=ticket.id, cycle_no=cycle_no, event_type=event_type).first()
        if existing:
            return existing
    user = User.query.filter_by(username=actor_name).first() if actor_name else None
    event = TicketTimingEvent(
        ticket_id=ticket.id,
        cycle_no=cycle_no,
        event_type=event_type,
        from_status=from_status or '',
        to_status=to_status or '',
        occurred_at_utc=occurred_at,
        actor_user_id=user.id if user else None,
        actor_name_snapshot=actor_name or '',
        source=source,
        metadata_json=dumps_json(metadata or {}),
        created_at=datetime.utcnow(),
    )
    db.session.add(event)
    return event


def begin_new_cycle(ticket, actor_name, occurred_at, from_status, to_status,
                    source='api', reason='reopen'):
    old_cycle = current_cycle(ticket.id)
    record_ticket_event(
        ticket, 'reopen', actor_name, from_status, to_status, occurred_at,
        source=source, metadata={'reason': reason}, cycle_no=old_cycle,
    )
    new_cycle = old_cycle + 1
    record_ticket_event(
        ticket, 'start', actor_name, from_status, to_status, occurred_at,
        source=source, metadata={'reason': reason}, cycle_no=new_cycle,
        idempotent=True,
    )
    return new_cycle


def _events(ticket_id, cycle_no):
    return (TicketTimingEvent.query
            .filter_by(ticket_id=ticket_id, cycle_no=cycle_no)
            .order_by(TicketTimingEvent.occurred_at_utc, TicketTimingEvent.id).all())


def _event_suspensions(events, end_at):
    exclusions = []
    opened = None
    for event in events:
        if event.event_type == 'suspend' and opened is None:
            opened = event.occurred_at_utc
        elif event.event_type == 'resume' and opened is not None:
            exclusions.append((opened, event.occurred_at_utc))
            opened = None
    if opened is not None and end_at:
        exclusions.append((opened, end_at))
    return exclusions


def _legacy_suspensions(ticket_id, end_at):
    rows = (TicketSuspend.query.filter_by(ticket_id=ticket_id)
            .order_by(TicketSuspend.started_at).all())
    return [(row.started_at, row.ended_at or end_at)
            for row in rows if row.started_at and (row.ended_at or end_at)]


def _natural_seconds(start, end):
    if not start or not end or end <= start:
        return 0
    return int((end - start).total_seconds())


def _calculate(ticket, now=None, cycle_no=None, events=None, legacy_suspensions=None):
    now = now or datetime.utcnow()
    cycle_no = int(cycle_no or current_cycle(ticket.id))
    events = _events(ticket.id, cycle_no) if events is None else events
    start_event = next((event for event in events if event.event_type == 'start'), None)
    finish_event = next((event for event in reversed(events)
                         if event.event_type in FINISH_EVENT_TYPES), None)
    closure_event = next((event for event in reversed(events)
                          if event.event_type in {'accept', 'close'}), None)

    estimated_reasons = []
    started_at = start_event.occurred_at_utc if start_event else None
    if not started_at and cycle_no == 1 and ticket.started_at:
        started_at = ticket.started_at
        estimated_reasons.append('缺少结构化 start 事件，使用历史 started_at')

    finished_at = finish_event.occurred_at_utc if finish_event else None
    if not finished_at and cycle_no == 1:
        if ticket.audit_status == '通过' and ticket.audit_at:
            finished_at = ticket.audit_at
            estimated_reasons.append('缺少 audit_approve 事件，使用历史 audit_at')
        elif ticket.status == TICKET_CLOSED and ticket.accept_at:
            finished_at = ticket.accept_at
            estimated_reasons.append('缺少 close 事件，使用历史 accept_at')
        elif ticket.status == TICKET_CLOSED and ticket.completed_at:
            finished_at = ticket.completed_at
            estimated_reasons.append('缺少最终审核/关闭事件，使用历史 completed_at')

    handling_end = finished_at or (now if started_at else None)
    exclusions = _event_suspensions(events, handling_end)
    if not exclusions and started_at:
        exclusions = (_legacy_suspensions(ticket.id, handling_end)
                      if legacy_suspensions is None else [
                          (row.started_at, row.ended_at or handling_end)
                          for row in legacy_suspensions
                          if row.started_at and (row.ended_at or handling_end)
                      ])
        if exclusions and not events:
            estimated_reasons.append('挂起区间来自历史 TicketSuspend')
    handling_seconds = (business_seconds(started_at, handling_end, exclusions=exclusions)
                        if started_at and handling_end else 0)
    suspended_business_seconds = sum(
        business_seconds(start, end) for start, end in exclusions if start and end)

    response_end = ticket.accepted_at or started_at
    response_seconds = _natural_seconds(ticket.created_at, response_end)
    closure_at = closure_event.occurred_at_utc if closure_event else None
    if not closure_at and ticket.status == TICKET_CLOSED:
        closure_at = ticket.accept_at or finished_at
    closure_seconds = (_natural_seconds(ticket.created_at, closure_at)
                       if closure_at else None)
    source = 'events' if start_event else ('estimated' if started_at else 'unknown')
    return {
        'source': source,
        'cycle_no': cycle_no,
        'reported_at': ticket.reported_at or ticket.created_at,
        'started_at': started_at,
        'finished_at': finished_at,
        'response_seconds': response_seconds,
        'handling_seconds': handling_seconds,
        'closure_seconds': closure_seconds,
        'suspended_business_seconds': suspended_business_seconds,
        'is_estimated': bool(estimated_reasons),
        'estimate_reason': '；'.join(estimated_reasons),
        'finish_source': finish_event.event_type if finish_event else '',
        'algorithm_version': ALGORITHM_VERSION,
        'calendar_version': DEFAULT_CALENDAR.version,
        'active': bool(started_at and not finished_at),
    }


def _snapshot_calculation(snapshot, ticket):
    return {
        'source': 'snapshot',
        'cycle_no': snapshot.cycle_no,
        'reported_at': ticket.reported_at or ticket.created_at,
        'started_at': snapshot.started_at_utc,
        'finished_at': snapshot.finished_at_utc,
        'response_seconds': snapshot.response_seconds or 0,
        'handling_seconds': snapshot.handling_seconds or 0,
        'closure_seconds': snapshot.closure_seconds,
        'suspended_business_seconds': snapshot.suspended_business_seconds or 0,
        'is_estimated': bool(snapshot.is_estimated),
        'estimate_reason': snapshot.estimate_reason or '',
        'finish_source': snapshot.finish_source or '',
        'algorithm_version': snapshot.algorithm_version or ALGORITHM_VERSION,
        'calendar_version': snapshot.calendar_version or DEFAULT_CALENDAR.version,
        'active': False,
    }


def _serialize(calculation):
    return {
        'source': calculation['source'],
        'cycle_no': calculation['cycle_no'],
        'reported_at': format_beijing(calculation['reported_at']),
        'started_at': format_beijing(calculation['started_at']),
        'finished_at': format_beijing(calculation['finished_at']),
        'response_seconds': calculation['response_seconds'],
        'response_duration_text': format_duration(calculation['response_seconds']),
        'handling_seconds': calculation['handling_seconds'],
        'handling_duration_text': format_duration(calculation['handling_seconds']),
        'handling_person_days': person_days(calculation['handling_seconds']),
        'closure_seconds': calculation['closure_seconds'],
        'closure_duration_text': format_duration(calculation['closure_seconds']),
        'suspended_business_seconds': calculation['suspended_business_seconds'],
        'is_estimated': calculation['is_estimated'],
        'estimate_reason': calculation['estimate_reason'],
        'finish_source': calculation['finish_source'],
        'algorithm_version': calculation['algorithm_version'],
        'calendar_version': calculation['calendar_version'],
        'active': calculation['active'],
    }


def ticket_timing_payload(ticket, now=None, *, cycle_no=None, events=None,
                          snapshot=None, legacy_suspensions=None):
    cycle_no = int(cycle_no or current_cycle(ticket.id))
    if snapshot is None:
        snapshot = TicketTimingSnapshot.query.filter_by(
            ticket_id=ticket.id, cycle_no=cycle_no).first()
    calculation = (_snapshot_calculation(snapshot, ticket) if snapshot
                   else _calculate(ticket, now=now, cycle_no=cycle_no,
                                   events=events,
                                   legacy_suspensions=legacy_suspensions))
    return _serialize(calculation)


def ticket_timing_payloads(tickets, now=None):
    """批量生成 payload，列表接口固定使用三次附加查询避免 N+1。"""
    tickets = list(tickets or ())
    ids = [ticket.id for ticket in tickets if ticket.id]
    if not ids:
        return {}
    event_rows = (TicketTimingEvent.query
                  .filter(TicketTimingEvent.ticket_id.in_(ids))
                  .order_by(TicketTimingEvent.ticket_id,
                            TicketTimingEvent.cycle_no,
                            TicketTimingEvent.occurred_at_utc,
                            TicketTimingEvent.id).all())
    snapshot_rows = (TicketTimingSnapshot.query
                     .filter(TicketTimingSnapshot.ticket_id.in_(ids)).all())
    suspend_rows = (TicketSuspend.query
                    .filter(TicketSuspend.ticket_id.in_(ids))
                    .order_by(TicketSuspend.ticket_id, TicketSuspend.started_at).all())
    events_by_ticket = {}
    snapshots_by_ticket = {}
    suspends_by_ticket = {}
    for event in event_rows:
        events_by_ticket.setdefault(event.ticket_id, []).append(event)
    for snapshot in snapshot_rows:
        snapshots_by_ticket.setdefault(snapshot.ticket_id, []).append(snapshot)
    for suspend in suspend_rows:
        suspends_by_ticket.setdefault(suspend.ticket_id, []).append(suspend)

    payloads = {}
    for ticket in tickets:
        ticket_events = events_by_ticket.get(ticket.id, [])
        ticket_snapshots = snapshots_by_ticket.get(ticket.id, [])
        cycle_no = max(
            [1] + [row.cycle_no for row in ticket_events] +
            [row.cycle_no for row in ticket_snapshots]
        )
        events = [row for row in ticket_events if row.cycle_no == cycle_no]
        snapshot = next((row for row in ticket_snapshots
                         if row.cycle_no == cycle_no), None)
        payloads[ticket.id] = ticket_timing_payload(
            ticket, now=now, cycle_no=cycle_no, events=events,
            snapshot=snapshot, legacy_suspensions=suspends_by_ticket.get(ticket.id, []))
    return payloads


def freeze_ticket_timing(ticket, finish_source, source='api', now=None):
    now = now or datetime.utcnow()
    cycle_no = current_cycle(ticket.id)
    calculation = _calculate(ticket, now=now, cycle_no=cycle_no)
    snapshot = TicketTimingSnapshot.query.filter_by(
        ticket_id=ticket.id, cycle_no=cycle_no).first()
    if not snapshot:
        snapshot = TicketTimingSnapshot(ticket_id=ticket.id, cycle_no=cycle_no)
        db.session.add(snapshot)
    snapshot.response_seconds = calculation['response_seconds']
    snapshot.handling_seconds = calculation['handling_seconds']
    snapshot.closure_seconds = calculation['closure_seconds']
    snapshot.suspended_business_seconds = calculation['suspended_business_seconds']
    snapshot.started_at_utc = calculation['started_at']
    snapshot.finished_at_utc = calculation['finished_at'] or now
    snapshot.algorithm_version = ALGORITHM_VERSION
    snapshot.calendar_version = DEFAULT_CALENDAR.version
    snapshot.is_estimated = calculation['is_estimated']
    snapshot.estimate_reason = calculation['estimate_reason']
    snapshot.finish_source = finish_source
    snapshot.generated_at_utc = now
    snapshot.source = source
    return snapshot


def ticket_resolution_at(ticket):
    event = (TicketTimingEvent.query
             .filter(TicketTimingEvent.ticket_id == ticket.id,
                     TicketTimingEvent.event_type.in_({'audit_approve', 'accept', 'close'}))
             .order_by(TicketTimingEvent.occurred_at_utc.desc(),
                       TicketTimingEvent.id.desc()).first())
    if event:
        return event.occurred_at_utc
    if ticket.audit_status == '通过' and ticket.audit_at:
        return ticket.audit_at
    if ticket.accept_status == '通过' and ticket.accept_at:
        return ticket.accept_at
    return ticket.completed_at


def fault_timing_payload(fault, now=None):
    if fault.ticket_id:
        ticket = Ticket.query.get(fault.ticket_id)
        if ticket:
            payload = ticket_timing_payload(ticket, now=now)
            payload['source'] = 'ticket'
            payload['source_ticket_id'] = ticket.id
            return payload
    now = now or datetime.utcnow()
    # 旧 Fault 的 fault_time/recovery_time 为北京本地 naive；新增
    # handling_started_at 按 UTC naive 保存。
    started_at = fault.handling_started_at or beijing_naive_to_utc(fault.fault_time)
    finished_at = beijing_naive_to_utc(fault.recovery_time)
    active = bool(started_at and not finished_at and fault.result != FAULT_RESOLVED)
    end_at = finished_at or (now if active else None)
    seconds = business_seconds(started_at, end_at) if started_at and end_at else 0
    estimated = not bool(fault.handling_started_at)
    return {
        'source': 'estimated' if estimated else 'manual',
        'source_ticket_id': None,
        'cycle_no': 1,
        'reported_at': format_beijing(beijing_naive_to_utc(fault.fault_time)),
        'started_at': format_beijing(started_at),
        'finished_at': format_beijing(finished_at),
        'response_seconds': 0,
        'response_duration_text': '',
        'handling_seconds': seconds,
        'handling_duration_text': format_duration(seconds),
        'handling_person_days': person_days(seconds),
        'closure_seconds': _natural_seconds(
            beijing_naive_to_utc(fault.fault_time), finished_at),
        'closure_duration_text': format_duration(
            _natural_seconds(beijing_naive_to_utc(fault.fault_time), finished_at)
        ) if finished_at else '',
        'suspended_business_seconds': 0,
        'is_estimated': estimated,
        'estimate_reason': '缺少处置开始时间，使用故障时间' if estimated else '',
        'finish_source': 'recovery' if finished_at else '',
        'algorithm_version': ALGORITHM_VERSION,
        'calendar_version': DEFAULT_CALENDAR.version,
        'active': active,
    }


def fault_timing_payloads(faults, now=None):
    """批量生成故障计时 payload；关联工单统一复用工单事件与快照。"""
    faults = list(faults or ())
    ticket_ids = sorted({fault.ticket_id for fault in faults if fault.ticket_id})
    tickets = Ticket.query.filter(Ticket.id.in_(ticket_ids)).all() if ticket_ids else []
    ticket_map = {ticket.id: ticket for ticket in tickets}
    ticket_payload_map = ticket_timing_payloads(tickets, now=now)
    payloads = {}
    for fault in faults:
        ticket = ticket_map.get(fault.ticket_id)
        if ticket:
            payload = dict(ticket_payload_map[ticket.id])
            payload['source'] = 'ticket'
            payload['source_ticket_id'] = ticket.id
        else:
            payload = fault_timing_payload(fault, now=now)
        payloads[fault.id] = payload
    return payloads
