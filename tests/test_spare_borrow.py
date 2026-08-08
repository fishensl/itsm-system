# -*- coding: utf-8 -*-
"""备件借用/归还：service 层（超借拒绝/归还回补/逾期标记）+ API 层"""
from datetime import date, timedelta

import pytest

from models import db, SparePart, SpareStock, SpareBorrow, StockMovement
from services.base import ServiceError
from services import spare_service


@pytest.fixture()
def ctx(app):
    with app.app_context():
        yield


def _make_part(app, name='光模块', qty=10):
    with app.app_context():
        p = SparePart(name=name, code=f'SP-{name}', unit='个', min_stock=2)
        db.session.add(p)
        db.session.flush()
        db.session.add(SpareStock(spare_part_id=p.id, quantity=qty, location='A柜'))
        db.session.commit()
        return p.id


class TestBorrowService:
    def test_borrow_and_return(self, ctx):
        pid = SparePart(name='B1', unit='个')
        db.session.add(pid)
        db.session.flush()
        db.session.add(SpareStock(spare_part_id=pid.id, quantity=5, location='L1'))
        db.session.commit()
        # 借出 3
        b = spare_service.create_spare_borrow(
            {'spare_part_id': pid.id, 'quantity': 3, 'borrower': '张三',
             'expected_return_date': (date.today() + timedelta(days=7)).isoformat()}, 'admin')
        assert b.status == '借用中'
        stock = SpareStock.query.filter_by(spare_part_id=pid.id).first()
        assert stock.quantity == 2  # 5 - 3
        mv = StockMovement.query.filter_by(spare_part_id=pid.id, movement_type='borrow').first()
        assert mv and mv.quantity == -3
        # 归还
        spare_service.return_spare_borrow(b.id, 'admin')
        assert SpareBorrow.query.get(b.id).status == '已归还'
        assert SpareBorrow.query.get(b.id).return_date == date.today()
        stock2 = SpareStock.query.filter_by(spare_part_id=pid.id).first()
        assert stock2.quantity == 5  # 回补
        mv2 = StockMovement.query.filter_by(spare_part_id=pid.id,
                                            movement_type='borrow_return').first()
        assert mv2 and mv2.quantity == 3

    def test_borrow_over_stock_rejected(self, ctx):
        pid = SparePart(name='B2', unit='个')
        db.session.add(pid)
        db.session.flush()
        db.session.add(SpareStock(spare_part_id=pid.id, quantity=2, location='L1'))
        db.session.commit()
        with pytest.raises(ServiceError):
            spare_service.create_spare_borrow(
                {'spare_part_id': pid.id, 'quantity': 5, 'borrower': '张三'}, 'admin')
        # 库存未变
        assert SpareStock.query.filter_by(spare_part_id=pid.id).first().quantity == 2

    def test_borrow_requires_borrower(self, ctx):
        pid = SparePart(name='B3', unit='个')
        db.session.add(pid)
        db.session.flush()
        db.session.add(SpareStock(spare_part_id=pid.id, quantity=2, location='L1'))
        db.session.commit()
        with pytest.raises(ServiceError):
            spare_service.create_spare_borrow(
                {'spare_part_id': pid.id, 'quantity': 1, 'borrower': '  '}, 'admin')

    def test_return_twice_rejected(self, ctx):
        pid = SparePart(name='B4', unit='个')
        db.session.add(pid)
        db.session.flush()
        db.session.add(SpareStock(spare_part_id=pid.id, quantity=5, location='L1'))
        db.session.commit()
        b = spare_service.create_spare_borrow(
            {'spare_part_id': pid.id, 'quantity': 2, 'borrower': '李四'}, 'admin')
        spare_service.return_spare_borrow(b.id, 'admin')
        with pytest.raises(ServiceError):
            spare_service.return_spare_borrow(b.id, 'admin')

    def test_overdue_marked(self, ctx):
        pid = SparePart(name='B5', unit='个')
        db.session.add(pid)
        db.session.flush()
        db.session.add(SpareStock(spare_part_id=pid.id, quantity=5, location='L1'))
        db.session.flush()
        # 直接插入一条逾期未还记录（预计归还日已过）
        db.session.add(SpareBorrow(spare_part_id=pid.id, borrower='王五', quantity=1,
                                   expected_return_date=date.today() - timedelta(days=3),
                                   status='借用中'))
        db.session.commit()
        _, total = spare_service.list_spare_borrows()
        rows = SpareBorrow.query.all()
        assert rows[0].status == '逾期'


class TestBorrowApi:
    def test_borrow_flow_api(self, admin_client, app):
        pid = _make_part(app, 'API备件', 10)
        # 借出
        r = admin_client.post('/api/spare-borrows', json={
            'spare_part_id': pid, 'quantity': 2, 'borrower': '测试借用',
            'expected_return_date': (date.today() + timedelta(days=5)).isoformat(),
        })
        assert r.status_code == 200, r.get_json()
        bid = r.get_json()['data']['id']
        # 列表
        r2 = admin_client.get('/api/spare-borrows')
        d = r2.get_json()['data']
        assert d['total'] == 1
        assert d['items'][0]['borrower'] == '测试借用'
        assert d['items'][0]['status'] == '借用中'
        # 库存已扣
        with app.app_context():
            assert SpareStock.query.filter_by(spare_part_id=pid).first().quantity == 8
        # 归还
        r3 = admin_client.post(f'/api/spare-borrows/{bid}/return', json={})
        assert r3.status_code == 200
        with app.app_context():
            assert SpareStock.query.filter_by(spare_part_id=pid).first().quantity == 10
            assert SpareBorrow.query.get(bid).status == '已归还'

    def test_borrow_requires_perm(self, viewer_client, app):
        pid = _make_part(app, '权限备件', 5)
        # viewer 无 spare:add
        r = viewer_client.post('/api/spare-borrows', json={
            'spare_part_id': pid, 'quantity': 1, 'borrower': 'x',
        })
        assert r.status_code == 403
