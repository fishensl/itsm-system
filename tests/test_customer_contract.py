# -*- coding: utf-8 -*-
"""客户合同服务期（P3）：状态派生 / 合同联动回填 / 过期建单门禁 / 自动生成器跳过"""
from datetime import date, timedelta

import pytest

from models import db, Customer, Contract
from utils.customer_contract import contract_status, contract_expired, contract_remaining_days, sync_from_contract
from utils.constants import CUSTOMER_CONTRACT_EXPIRING, CUSTOMER_CONTRACT_EXPIRED, \
    CUSTOMER_CONTRACT_NONE, CUSTOMER_CONTRACT_ACTIVE


@pytest.fixture()
def seed(app):
    with app.app_context():
        c = Customer(name='合同客户')
        db.session.add(c)
        db.session.commit()
        yield c.id


def _reload(cid):
    db.session.expire_all()
    return Customer.query.get(cid)


def _set_end(cid, days):
    c = _reload(cid)
    c.contract_end_date = date.today() + timedelta(days=days)
    db.session.commit()


class TestStatusDerivation:
    def test_none(self, seed):
        c = _reload(seed)
        assert contract_status(c) == CUSTOMER_CONTRACT_NONE
        assert not contract_expired(c)
        assert contract_remaining_days(c) is None

    def test_active(self, seed):
        _set_end(seed, 60)
        assert contract_status(_reload(seed)) == CUSTOMER_CONTRACT_ACTIVE

    def test_expiring_30(self, seed):
        _set_end(seed, 15)
        assert contract_status(_reload(seed)) == CUSTOMER_CONTRACT_EXPIRING
        assert not contract_expired(_reload(seed))

    def test_expired(self, seed):
        _set_end(seed, -3)
        c = _reload(seed)
        assert contract_status(c) == CUSTOMER_CONTRACT_EXPIRED
        assert contract_expired(c)
        assert contract_remaining_days(c) == -3


def _reload(cid):
    db.session.expire_all()
    return Customer.query.get(cid)


class TestContractSyncBackfill:
    def test_create_contract_backfills(self, app, seed):
        with app.app_context():
            c1 = Contract(title='合同A', customer_id=seed, status='执行中',
                          start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
            db.session.add(c1)
            db.session.flush()
            sync_from_contract(contract=c1)
            db.session.commit()
        with app.app_context():
            c = _reload(seed)
            assert c.contract_start_date == date(2026, 1, 1)
            assert c.contract_end_date == date(2026, 12, 31)

    def test_multiple_contracts_max_end(self, app, seed):
        with app.app_context():
            for title, s, e, status in (('A', date(2026, 1, 1), date(2026, 6, 30), '已签'),
                                        ('B', date(2026, 3, 1), date(2027, 3, 31), '执行中'),
                                        ('C', date(2025, 1, 1), date(2025, 12, 31), '已终止')):
                db.session.add(Contract(title=title, customer_id=seed, status=status,
                                        start_date=s, end_date=e))
            db.session.flush()
            sync_from_contract(customer_id=seed)
            db.session.commit()
        with app.app_context():
            c = _reload(seed)
            assert c.contract_start_date == date(2026, 1, 1)   # 执行中/已签最小 start
            assert c.contract_end_date == date(2027, 3, 31)    # 最大 end
            # 已终止合同不参与
            assert c.contract_end_date != date(2025, 12, 31)

    def test_no_active_keeps_manual(self, app, seed):
        with app.app_context():
            c = _reload(seed)
            c.contract_start_date = date(2026, 1, 1)
            c.contract_end_date = date(2026, 12, 31)
            db.session.add(Contract(title='已终止', customer_id=seed, status='已终止',
                                    end_date=date(2025, 12, 31)))
            db.session.flush()
            sync_from_contract(customer_id=seed)
            db.session.commit()
        with app.app_context():
            c = _reload(seed)
            assert c.contract_end_date == date(2026, 12, 31)  # 无有效合同不覆盖手动值


class TestExpiredGate:
    def test_create_ticket_expired_requires_reason(self, app, seed, op_client):
        from services.ticket_service import create_ticket
        from services.base import ServiceError
        with app.app_context():
            _set_end(seed, -1)
            with pytest.raises(ServiceError):
                create_ticket({'title': '过期客户工单', 'customer_id': seed}, 'op')

    def test_create_ticket_with_reason_enters_contract_review(self, app, seed):
        from services.ticket_service import create_ticket
        with app.app_context():
            _set_end(seed, -1)
            t = create_ticket({'title': '过期客户工单', 'customer_id': seed,
                               'contract_exception_reason': '紧急抢修，特批'},
                              'op')
            db.session.commit()
            assert t.status == '合同审批'
            assert t.contract_exception_status == '待审核'

    def test_create_ticket_active_no_review(self, app, seed):
        from services.ticket_service import create_ticket
        with app.app_context():
            _set_end(seed, 60)
            t = create_ticket({'title': '正常客户工单', 'customer_id': seed}, 'op')
            db.session.commit()
            assert t.status == '待派单'
            assert t.contract_exception_status == ''

    def test_contract_review_approved_then_assign(self, app, seed, admin_client):
        from services.ticket_service import create_ticket, contract_review_ticket
        with app.app_context():
            _set_end(seed, -1)
            t = create_ticket({'title': '审批工单', 'customer_id': seed,
                               'contract_exception_reason': '特批'}, 'op')
            db.session.commit()
            contract_review_ticket(t.id, True, 'admin', '同意紧急处理')
            db.session.commit()
            assert t.status == '待派单'
            assert t.contract_exception_status == '通过'

    def test_contract_review_rejected_closes(self, app, seed):
        from services.ticket_service import create_ticket, contract_review_ticket
        with app.app_context():
            _set_end(seed, -1)
            t = create_ticket({'title': '拒绝工单', 'customer_id': seed,
                               'contract_exception_reason': '特批'}, 'op')
            db.session.commit()
            contract_review_ticket(t.id, False, 'admin', '无合同不安排')
            db.session.commit()
            assert t.status == '已关闭'
            assert t.contract_exception_status == '拒绝'


class TestGeneratorSkipsExpired:
    def test_generate_for_customer_skips(self, app, seed):
        from utils.customer_task_generator import generate_for_customer
        from models import InspectionTask
        with app.app_context():
            _reload(seed).inspection_frequency = '每月'
            db.session.commit()
            _set_end(seed, -1)
            n = generate_for_customer(seed)
            assert n == 0
            assert InspectionTask.query.filter_by(customer_id=seed).count() == 0

    def test_generate_for_customer_active_works(self, app, seed):
        from utils.customer_task_generator import generate_for_customer
        from models import InspectionTask
        with app.app_context():
            _reload(seed).inspection_frequency = '每月'
            db.session.commit()
            _set_end(seed, 300)
            n = generate_for_customer(seed)
            db.session.commit()
            assert n > 0
            assert InspectionTask.query.filter_by(customer_id=seed).count() > 0
