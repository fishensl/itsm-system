from datetime import datetime

from models import (db, Fault, Ticket, TicketSuspend, TicketTimingEvent,
                    TicketTimingSnapshot)
from scripts.backfill_ticket_timing import backfill_tickets
from services import ticket_service
from services.ticket_timing_service import (
    fault_timing_payload,
    freeze_ticket_timing,
    record_ticket_event,
    ticket_timing_payload,
)


def _ticket(title='计时工单'):
    return ticket_service.create_ticket({'title': title, 'priority': '中'}, 'admin')


def test_lifecycle_writes_structured_events_and_snapshot(app):
    with app.app_context():
        ticket = _ticket()
        ticket_service.assign_ticket(ticket.id, 'op', 'admin')
        ticket_service.accept_ticket(ticket.id, 'op')
        ticket_service.submit_ticket(ticket.id, 'op')
        ticket_service.audit_ticket(ticket.id, True, 'admin')

        event_types = [row.event_type for row in TicketTimingEvent.query.filter_by(
            ticket_id=ticket.id).order_by(TicketTimingEvent.id)]
        assert event_types == ['start', 'submit', 'audit_approve']
        snapshot = TicketTimingSnapshot.query.filter_by(
            ticket_id=ticket.id, cycle_no=1).one()
        assert snapshot.finish_source == 'audit_approve'
        assert snapshot.started_at_utc is not None
        assert snapshot.finished_at_utc is not None


def test_business_timing_excludes_structured_suspend_intervals(app):
    with app.app_context():
        ticket = Ticket(
            number='WO-TIMING-001', title='固定时间计时', status='已验收',
            created_at=datetime(2026, 8, 24, 0, 0),
            accepted_at=datetime(2026, 8, 24, 0, 30),
        )
        db.session.add(ticket)
        db.session.flush()
        record_ticket_event(ticket, 'start', 'op', '已派单', '处理中',
                            occurred_at=datetime(2026, 8, 24, 0, 30))
        record_ticket_event(ticket, 'suspend', 'op', '处理中', '已挂起',
                            occurred_at=datetime(2026, 8, 24, 2, 30))
        record_ticket_event(ticket, 'resume', 'op', '已挂起', '处理中',
                            occurred_at=datetime(2026, 8, 24, 6, 30))
        record_ticket_event(ticket, 'audit_approve', 'admin', '待审核', '已验收',
                            occurred_at=datetime(2026, 8, 24, 9, 30))
        freeze_ticket_timing(ticket, 'audit_approve', now=datetime(2026, 8, 24, 9, 30))
        db.session.commit()

        payload = ticket_timing_payload(ticket)
        assert payload['source'] == 'snapshot'
        assert payload['response_seconds'] == 30 * 60
        assert payload['handling_seconds'] == 5 * 60 * 60
        assert payload['handling_duration_text'] == '5小时'
        assert payload['handling_person_days'] == 0.62
        assert payload['suspended_business_seconds'] == 2.5 * 60 * 60


def test_reopen_preserves_old_snapshot_and_starts_new_cycle(app):
    with app.app_context():
        ticket = _ticket('重开计时')
        ticket_service.close_ticket(ticket.id, 'admin')
        assert TicketTimingSnapshot.query.filter_by(
            ticket_id=ticket.id, cycle_no=1).count() == 1

        ticket_service.reopen_ticket(ticket.id, 'admin', '继续处理')
        payload = ticket_timing_payload(Ticket.query.get(ticket.id))
        assert payload['cycle_no'] == 2
        assert payload['active'] is True
        assert TicketTimingSnapshot.query.filter_by(
            ticket_id=ticket.id, cycle_no=1).count() == 1


def test_linked_fault_reuses_ticket_timing(app):
    with app.app_context():
        ticket = _ticket('故障计时真源')
        ticket_service.assign_ticket(ticket.id, 'op', 'admin')
        ticket_service.accept_ticket(ticket.id, 'op')
        fault = Fault(title='关联故障', ticket_id=ticket.id)
        db.session.add(fault)
        db.session.commit()

        payload = fault_timing_payload(fault)
        assert payload['source'] == 'ticket'
        assert payload['source_ticket_id'] == ticket.id
        assert payload['cycle_no'] == 1


def test_legacy_ticket_backfill_is_idempotent_and_marked_estimated(app):
    with app.app_context():
        ticket = Ticket(
            number='WO-TIMING-LEGACY', title='历史工单', status='已验收',
            created_at=datetime(2026, 8, 24, 0, 0),
            started_at=datetime(2026, 8, 24, 0, 30),
            audit_status='通过', audit_at=datetime(2026, 8, 24, 9, 30),
        )
        db.session.add(ticket)
        db.session.flush()
        db.session.add(TicketSuspend(
            ticket_id=ticket.id,
            started_at=datetime(2026, 8, 24, 2, 30),
            ended_at=datetime(2026, 8, 24, 6, 30),
        ))
        db.session.commit()

        report = backfill_tickets(apply=True)
        assert report['events_written'] == 4
        snapshot = TicketTimingSnapshot.query.filter_by(ticket_id=ticket.id).one()
        assert snapshot.source == 'backfill'
        assert snapshot.is_estimated is True
        assert snapshot.handling_seconds == 5 * 60 * 60

        second = backfill_tickets(apply=True)
        assert second['events_written'] == 0
        assert TicketTimingEvent.query.filter_by(ticket_id=ticket.id).count() == 4
