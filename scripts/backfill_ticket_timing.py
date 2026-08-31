# -*- coding: utf-8 -*-
"""为存量工单生成结构化计时事件和冻结快照。

默认仅输出评估报告，不写数据库。实际回填必须显式提供 ``--apply`` 和
发布前配对备份标识，所有写入在一个事务中提交：

    python scripts/backfill_ticket_timing.py
    python scripts/backfill_ticket_timing.py --apply --backup-reference r1-20260830_120000

无法从历史字段可靠推断的时间不会被猜测；报告会列入 ``issues``。由历史
字段生成的快照统一标记 ``is_estimated``，方便后续人工抽检和重算。
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, Ticket, TicketSuspend, TicketTimingEvent
from services.ticket_timing_service import freeze_ticket_timing, record_ticket_event
from utils.constants import TICKET_CLOSED


def _iso(value):
    return value.isoformat(timespec='seconds') if value else None


def build_backfill_plan(ticket, suspends):
    """从明确的旧字段构造单轮事件；返回事件、问题和是否可冻结。"""
    issues = []
    events = []
    start = ticket.started_at
    if not start:
        issues.append('缺少 started_at，未生成计时事件')
        return {'events': events, 'issues': issues, 'freeze': False}

    events.append({'event_type': 'start', 'occurred_at': start})
    for row in suspends:
        if not row.started_at:
            issues.append(f'挂起段 #{row.id} 缺少开始时间')
            continue
        if row.started_at < start:
            issues.append(f'挂起段 #{row.id} 早于处置开始，已跳过')
            continue
        events.append({'event_type': 'suspend', 'occurred_at': row.started_at})
        if row.ended_at:
            if row.ended_at <= row.started_at:
                issues.append(f'挂起段 #{row.id} 结束不晚于开始，未生成恢复事件')
            else:
                events.append({'event_type': 'resume', 'occurred_at': row.ended_at})
        else:
            issues.append(f'挂起段 #{row.id} 尚未闭合')

    finish_type = None
    finish_at = None
    if ticket.audit_status == '通过' and ticket.audit_at:
        finish_type, finish_at = 'audit_approve', ticket.audit_at
    elif ticket.status == TICKET_CLOSED:
        finish_type = 'close'
        finish_at = ticket.accept_at or ticket.completed_at
        if finish_at == ticket.completed_at and finish_at:
            issues.append('缺少审核/验收完成时间，关闭点使用 completed_at')
    if finish_at:
        if finish_at < start:
            issues.append('结束时间早于处置开始，未生成结束事件')
            finish_type, finish_at = None, None
        else:
            events.append({'event_type': finish_type, 'occurred_at': finish_at})

    if ticket.accept_at and ticket.accept_at >= start and ticket.accept_at != finish_at:
        events.append({'event_type': 'accept', 'occurred_at': ticket.accept_at})

    events.sort(key=lambda item: (item['occurred_at'], item['event_type']))
    return {'events': events, 'issues': issues, 'freeze': bool(finish_type and finish_at)}


def backfill_tickets(*, apply=False, limit=None):
    query = Ticket.query.order_by(Ticket.id)
    if limit:
        query = query.limit(limit)
    tickets = query.all()
    suspend_rows = (TicketSuspend.query
                    .filter(TicketSuspend.ticket_id.in_([row.id for row in tickets]))
                    .order_by(TicketSuspend.ticket_id, TicketSuspend.started_at).all()
                    if tickets else [])
    suspends_by_ticket = {}
    for row in suspend_rows:
        suspends_by_ticket.setdefault(row.ticket_id, []).append(row)

    report_rows = []
    written_events = 0
    written_snapshots = 0
    for ticket in tickets:
        existing = TicketTimingEvent.query.filter_by(ticket_id=ticket.id).count()
        if existing:
            report_rows.append({
                'ticket_id': ticket.id,
                'number': ticket.number,
                'result': 'skipped_existing',
                'existing_events': existing,
                'issues': [],
            })
            continue
        plan = build_backfill_plan(ticket, suspends_by_ticket.get(ticket.id, []))
        result = 'preview' if plan['events'] else 'unknown'
        if apply and plan['events']:
            for event in plan['events']:
                record_ticket_event(
                    ticket,
                    event['event_type'],
                    actor_name='数据回填',
                    occurred_at=event['occurred_at'],
                    source='backfill',
                    cycle_no=1,
                )
            db.session.flush()
            written_events += len(plan['events'])
            if plan['freeze']:
                finish_event = next(
                    event for event in reversed(plan['events'])
                    if event['event_type'] in {'audit_approve', 'close'}
                )
                snapshot = freeze_ticket_timing(
                    ticket, finish_event['event_type'], source='backfill',
                    now=finish_event['occurred_at'])
                snapshot.is_estimated = True
                snapshot.estimate_reason = (
                    '存量历史字段回填' +
                    (f"；{'；'.join(plan['issues'])}" if plan['issues'] else '')
                )
                written_snapshots += 1
            result = 'written'
        report_rows.append({
            'ticket_id': ticket.id,
            'number': ticket.number,
            'result': result,
            'events': [
                {'type': item['event_type'], 'at': _iso(item['occurred_at'])}
                for item in plan['events']
            ],
            'freeze': plan['freeze'],
            'issues': plan['issues'],
        })

    summary = {
        'mode': 'apply' if apply else 'dry-run',
        'generated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'tickets_scanned': len(tickets),
        'tickets_with_existing_events': sum(
            row['result'] == 'skipped_existing' for row in report_rows),
        'tickets_unknown': sum(row['result'] == 'unknown' for row in report_rows),
        'events_written': written_events,
        'snapshots_written': written_snapshots,
        'rows': report_rows,
    }
    if apply:
        db.session.commit()
    return summary


def write_report(report, output=None, backup_reference=''):
    report['backup_reference'] = backup_reference or None
    canonical = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    report['sha256'] = hashlib.sha256(canonical).hexdigest()
    if output:
        path = Path(output).resolve()
    else:
        stamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        path = (Path(__file__).resolve().parents[1] / 'reports' /
                f'ticket_timing_backfill_{stamp}.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser(description='存量工单计时事件/快照回填')
    parser.add_argument('--apply', action='store_true', help='实际写入；默认仅预览')
    parser.add_argument('--backup-reference', default='', help='发布前配对备份标识')
    parser.add_argument('--output', help='报告输出路径')
    parser.add_argument('--limit', type=int, help='仅扫描前 N 条（演练用）')
    args = parser.parse_args()
    if args.apply and not args.backup_reference.strip():
        parser.error('--apply 必须同时提供 --backup-reference，先完成配对备份')

    app = create_app()
    with app.app_context():
        try:
            report = backfill_tickets(apply=args.apply, limit=args.limit)
        except Exception:
            db.session.rollback()
            raise
        path = write_report(report, args.output, args.backup_reference.strip())
        print(json.dumps({key: value for key, value in report.items() if key != 'rows'},
                         ensure_ascii=False, indent=2))
        print(f'报告: {path}')
        if not args.apply:
            print('当前为 dry-run，数据库未写入。确认报告并完成配对备份后再使用 --apply。')


if __name__ == '__main__':
    main()
