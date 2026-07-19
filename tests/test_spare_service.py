# -*- coding: utf-8 -*-
"""备件 FIFO 出库：扣减顺序 / 超扣拒绝 / 删单冲销"""
import pytest

from models import db, SpareStock
from services.base import ServiceError
from services import spare_service


@pytest.fixture()
def ctx(app):
    with app.app_context():
        yield


@pytest.fixture()
def part(ctx):
    return spare_service.create_spare_part({'name': '光模块', 'code': 'GM-01', 'min_stock': 2})


def _stocks(part_id):
    return SpareStock.query.filter_by(spare_part_id=part_id).order_by(SpareStock.id).all()


class TestPurchaseInbound:
    def test_purchase_creates_stock(self, ctx, part):
        spare_service.create_purchase_order(
            {'spare_part_id': part.id, 'quantity': 10, 'unit_price': 100}, 'admin')
        stocks = _stocks(part.id)
        assert len(stocks) == 1
        assert stocks[0].quantity == 10

    def test_purchase_accumulates_first_row(self, ctx, part):
        for _ in range(2):
            spare_service.create_purchase_order(
                {'spare_part_id': part.id, 'quantity': 5, 'unit_price': 100}, 'admin')
        assert _stocks(part.id)[0].quantity == 10

    def test_zero_quantity_rejected(self, ctx, part):
        with pytest.raises(ServiceError):
            spare_service.create_purchase_order(
                {'spare_part_id': part.id, 'quantity': 0}, 'admin')


class TestFifoOutbound:
    def _prepare_two_rows(self, part):
        """库位A 10 个（id 小，先入）+ 库位B 5 个"""
        spare_service.create_purchase_order(
            {'spare_part_id': part.id, 'quantity': 10, 'unit_price': 100, 'location': 'A'}, 'admin')
        db.session.add(SpareStock(spare_part_id=part.id, quantity=5, location='B'))
        db.session.commit()

    def test_fifo_deducts_oldest_first(self, ctx, part):
        self._prepare_two_rows(part)
        # 出 12：A 扣空(10)，B 扣 2 剩 3
        spare_service.create_sales_order(
            {'spare_part_id': part.id, 'quantity': 12, 'unit_price': 150}, 'admin')
        a, b = _stocks(part.id)
        assert a.quantity == 0
        assert b.quantity == 3

    def test_fifo_within_single_row(self, ctx, part):
        self._prepare_two_rows(part)
        spare_service.create_sales_order(
            {'spare_part_id': part.id, 'quantity': 4, 'unit_price': 150}, 'admin')
        a, b = _stocks(part.id)
        assert a.quantity == 6
        assert b.quantity == 5

    def test_oversell_rejected_and_stock_unchanged(self, ctx, part):
        self._prepare_two_rows(part)
        with pytest.raises(ServiceError) as exc:
            spare_service.create_sales_order(
                {'spare_part_id': part.id, 'quantity': 100, 'unit_price': 1}, 'admin')
        assert '库存不足' in str(exc.value)
        a, b = _stocks(part.id)
        assert a.quantity == 10 and b.quantity == 5  # 超扣拒绝后库存不变


class TestOrderReversal:
    def test_delete_sales_order_restores_stock(self, ctx, part):
        spare_service.create_purchase_order(
            {'spare_part_id': part.id, 'quantity': 10, 'unit_price': 100}, 'admin')
        so = spare_service.create_sales_order(
            {'spare_part_id': part.id, 'quantity': 6, 'unit_price': 150}, 'admin')
        assert _stocks(part.id)[0].quantity == 4
        spare_service.delete_sales_order(so.id)
        assert _stocks(part.id)[0].quantity == 10

    def test_delete_purchase_order_deducts_back(self, ctx, part):
        po = spare_service.create_purchase_order(
            {'spare_part_id': part.id, 'quantity': 10, 'unit_price': 100}, 'admin')
        spare_service.delete_purchase_order(po.id)
        assert _stocks(part.id)[0].quantity == 0


class TestSparePartCrud:
    def test_duplicate_name_rejected(self, ctx, part):
        with pytest.raises(ServiceError):
            spare_service.create_spare_part({'name': '光模块'})

    def test_delete_with_stock_rejected(self, ctx, part):
        spare_service.create_purchase_order(
            {'spare_part_id': part.id, 'quantity': 1, 'unit_price': 1}, 'admin')
        with pytest.raises(ServiceError):
            spare_service.delete_spare_part(part.id)
