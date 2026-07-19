# -*- coding: utf-8 -*-
"""新旧双轨收敛：把 faults（旧故障记录）迁移为 tickets（工单）。

策略：
- 仅处理 fault.ticket_id 为 NULL 的记录（幂等，重跑不重复迁移）
- 字段映射：description←fault_description, diagnosis←fault_cause, solution←solution,
  assigned_to←handler, fault_time→created_at/completed_at, 结构化故障字段同名直拷
- 状态映射：result='已解决' → 已关闭（终态）；其他 → 处理中（可继续走工单流程）
- 迁移后回写 fault.ticket_id 建立桥接（旧记录保留可查，不删数据）

用法（项目根目录）：
    python scripts/faults_to_tickets.py            # 预览（dry-run，不写库）
    python scripts/faults_to_tickets.py --apply    # 实际迁移
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, Fault, Ticket, TicketLog, FaultType


def _next_number(dt):
    """按故障时间生成工单号 WO-YYYYMMDD-NNN（NNN 取当日最大+1）"""
    prefix = f"WO-{dt.strftime('%Y%m%d')}-" if dt else None
    if not prefix:
        from datetime import datetime
        prefix = f"WO-{datetime.now().strftime('%Y%m%d')}-"
    last = Ticket.query.filter(Ticket.number.like(prefix + '%'))\
        .order_by(Ticket.id.desc()).first()
    n = 1
    if last:
        try:
            n = int(last.number.split('-')[-1]) + 1
        except (ValueError, IndexError):
            n = 1
    return f'{prefix}{n:03d}'


def migrate_one(f, dry_run=True):
    """迁移单条故障记录，返回 (ticket_number, action)"""
    fault_type = FaultType.query.filter_by(name=f.fault_type).first() if f.fault_type else None
    solved = (f.result or '') == '已解决'
    t = Ticket(
        number=_next_number(f.fault_time),
        source_type='旧故障迁移',
        priority='中',
        status='已关闭' if solved else '处理中',
        title=f.title,
        description=f.fault_description or '',
        customer_id=f.customer_id,
        assigned_to=f.handler or '',
        created_by='数据迁移',
        created_at=f.fault_time,
        completed_at=f.recovery_time if solved else None,
        diagnosis=f.fault_cause or '',
        solution=f.solution or '',
        result=f.result or '',
        report_file=f.report_file or '',
        fault_category_id=fault_type.id if fault_type else None,
        fault_category_level1=f.fault_category_level1 or '',
        fault_category_level2=f.fault_category_level2 or '',
        symptoms_json=f.symptoms_json or '[]',
        affected_components_json=f.affected_components_json or '[]',
        resolution_steps_json=f.resolution_steps_json or '[]',
        root_cause_category=f.root_cause_category or '',
        severity_level=f.severity_level or '',
        impact_scope=f.impact_scope or f.impact_range or '',
        normalized_tags=f.normalized_tags or '',
    )
    if dry_run:
        return t.number, 'preview'
    db.session.add(t)
    db.session.flush()  # 取 t.id
    db.session.add(TicketLog(
        ticket_id=t.id, action='从旧故障记录迁移',
        operator='数据迁移', comment=f'faults.id={f.id}',
        created_at=f.fault_time))
    f.ticket_id = t.id
    return t.number, 'migrated'


def main():
    dry_run = '--apply' not in sys.argv
    app = create_app()
    with app.app_context():
        pending = Fault.query.filter(Fault.ticket_id.is_(None))\
            .order_by(Fault.fault_time).all()
        total = Fault.query.count()
        print(f'faults 总数: {total}，待迁移: {len(pending)}，已桥接: {total - len(pending)}')
        if not pending:
            print('无需迁移。')
            return
        for f in pending:
            number, action = migrate_one(f, dry_run=dry_run)
            print(f"  [{action}] fault#{f.id} 「{f.title[:30]}」 -> {number}")
        if dry_run:
            print('\n以上为预览（未写库）。确认后执行: python scripts/faults_to_tickets.py --apply')
        else:
            db.session.commit()
            print(f'\n已迁移 {len(pending)} 条并回写 fault.ticket_id。')


if __name__ == '__main__':
    main()
