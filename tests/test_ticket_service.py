# -*- coding: utf-8 -*-
"""工单状态机：合法转换全覆盖 + 非法转换拒绝 + 日志原子性"""
import pytest

from models import Ticket, TicketLog
from services.base import ServiceError
from services import ticket_service


@pytest.fixture()
def ctx(app):
    with app.app_context():
        yield


def _create(ctx, title='核心交换机离线'):
    return ticket_service.create_ticket({'title': title, 'priority': '高'}, 'admin')


class TestTicketLifecycle:
    """完整生命周期：创建→派单→接单→提交→审核通过→验收通过→关闭"""

    def test_full_lifecycle(self, ctx):
        t = _create(ctx)
        assert t.status == '待派单'
        assert t.number.startswith('WO-')
        assert t.number.endswith('-001')

        ticket_service.assign_ticket(t.id, 'op', 'admin')
        assert Ticket.query.get(t.id).status == '已派单'
        assert Ticket.query.get(t.id).assigned_to == 'op'

        ticket_service.accept_ticket(t.id, 'op')
        assert Ticket.query.get(t.id).status == '处理中'

        ticket_service.submit_ticket(t.id, 'op', diagnosis='光模块故障', solution='更换模块')
        tk = Ticket.query.get(t.id)
        assert tk.status == '待审核'
        assert tk.diagnosis == '光模块故障'

        ticket_service.audit_ticket(t.id, True, 'admin')
        assert Ticket.query.get(t.id).status == '已验收'

        ticket_service.accept_check_ticket(t.id, 'admin', approved=True)
        assert Ticket.query.get(t.id).status == '已关闭'

        # 全流程日志完整
        logs = TicketLog.query.filter_by(ticket_id=t.id).all()
        assert len(logs) >= 6

    def test_number_increments(self, ctx):
        t1 = _create(ctx, '工单A')
        t2 = _create(ctx, '工单B')
        assert t1.number != t2.number
        assert int(t2.number.split('-')[-1]) == int(t1.number.split('-')[-1]) + 1

    def test_sla_deadline_by_priority(self, ctx):
        """S6 SLA：按优先级计算截止时间（高=4h/中=24h/低=72h）"""
        from datetime import datetime, timedelta
        from utils.constants import SLA_HOURS_BY_PRIORITY
        now = datetime.utcnow()
        for prio, hours in SLA_HOURS_BY_PRIORITY.items():
            t = ticket_service.create_ticket(
                {'title': f'SLA-{prio}', 'priority': prio}, 'admin')
            delta = t.sla_deadline - now
            # 允许少量构建耗时误差（<2 分钟）
            assert abs(delta.total_seconds() - hours * 3600) < 120, prio

    def test_number_advances_after_delete(self, ctx):
        """删除工单后新单号按「剩余最大序号 + 1」推进：不回退、不与存续工单重号"""
        from models import db, TicketLog
        t1 = _create(ctx, '工单A')
        t2 = _create(ctx, '工单B')
        seq1 = int(t1.number.split('-')[-1])
        seq2 = int(t2.number.split('-')[-1])
        assert seq2 == seq1 + 1
        # 删除序号更大的 t2（当日最后一张，先清其日志）
        TicketLog.query.filter_by(ticket_id=t2.id).delete()
        db.session.delete(t2)
        db.session.commit()
        t3 = _create(ctx, '工单C')
        seq3 = int(t3.number.split('-')[-1])
        # 新单号 = 剩余最大序号(seq1) + 1，不回退
        assert seq3 == seq1 + 1
        # 存续工单号全部唯一（无碰撞）
        assert len({t1.number, t3.number}) == 2


class TestIllegalTransitions:
    """非法转换必须抛 ServiceError 且状态不变"""

    def test_submit_from_pending_rejected(self, ctx):
        t = _create(ctx)
        with pytest.raises(ServiceError):
            ticket_service.submit_ticket(t.id, 'admin')
        assert Ticket.query.get(t.id).status == '待派单'

    def test_audit_from_pending_rejected(self, ctx):
        t = _create(ctx)
        with pytest.raises(ServiceError):
            ticket_service.audit_ticket(t.id, True, 'admin')

    def test_closed_is_terminal(self, ctx):
        t = _create(ctx)
        ticket_service.close_ticket(t.id, 'admin')
        assert Ticket.query.get(t.id).status == '已关闭'
        with pytest.raises(ServiceError):
            ticket_service.assign_ticket(t.id, 'op', 'admin')

    def test_reopen_closed_ticket(self, ctx):
        """已关闭工单可重开回处理中（纠正性操作）"""
        t = _create(ctx)
        ticket_service.close_ticket(t.id, 'admin')
        assert Ticket.query.get(t.id).status == '已关闭'
        ticket_service.reopen_ticket(t.id, 'admin', remark='误关重开')
        tk = Ticket.query.get(t.id)
        assert tk.status == '处理中'
        # 重开后仍可继续走处理流程
        ticket_service.submit_ticket(t.id, 'admin')
        assert Ticket.query.get(t.id).status == '待审核'

    def test_reopen_non_closed_rejected(self, ctx):
        """非已关闭工单不可重开"""
        t = _create(ctx)
        with pytest.raises(ServiceError):
            ticket_service.reopen_ticket(t.id, 'admin')

    def test_unknown_state_rejected(self, ctx):
        t = _create(ctx)
        with pytest.raises(ServiceError):
            ticket_service._transition(t, '不存在的状态', 'admin')

    def test_audit_reject_returns_to_processing(self, ctx):
        t = _create(ctx)
        ticket_service.assign_ticket(t.id, 'op', 'admin')
        ticket_service.accept_ticket(t.id, 'op')
        ticket_service.submit_ticket(t.id, 'op')
        ticket_service.audit_ticket(t.id, False, 'admin', remark='方案不完整')
        tk = Ticket.query.get(t.id)
        assert tk.status == '处理中'
        assert tk.audit_status == '拒绝'

    def test_accept_check_reject_returns_to_processing(self, ctx):
        t = _create(ctx)
        for fn in (lambda: ticket_service.assign_ticket(t.id, 'op', 'admin'),
                   lambda: ticket_service.accept_ticket(t.id, 'op'),
                   lambda: ticket_service.submit_ticket(t.id, 'op'),
                   lambda: ticket_service.audit_ticket(t.id, True, 'admin')):
            fn()
        ticket_service.accept_check_ticket(t.id, 'admin', approved=False)
        assert Ticket.query.get(t.id).status == '处理中'


class TestTicketValidation:
    def test_empty_title_rejected(self, ctx):
        with pytest.raises(ServiceError):
            ticket_service.create_ticket({'title': '  '}, 'admin')

    def test_assign_without_assignee_rejected(self, ctx):
        t = _create(ctx)
        with pytest.raises(ServiceError):
            ticket_service.assign_ticket(t.id, '', 'admin')
