# -*- coding: utf-8 -*-
"""P3 备件/销售 Vue API：列表/筛选/详情/增删改/库存联动/字典/权限"""
from datetime import date, timedelta

import pytest

from models import (db, Customer, SparePart, SpareStock, PurchaseOrder, SalesOrder,
                    Opportunity, Quotation, Contract, Project, InspectionTask,
                    InspectionTaskTemplate)


@pytest.fixture()
def seed(app):
    with app.app_context():
        c1 = Customer(name='销售客户A')
        c2 = Customer(name='销售客户B')
        db.session.add_all([c1, c2])
        db.session.flush()
        p1 = SparePart(name='风扇模块', code='SP-FAN-01', category='散热', min_stock=5,
                       unit='个', reference_price=100, brand='华为', model='FAN-X')
        p2 = SparePart(name='硬盘', code='SP-DISK-01', category='存储', min_stock=0,
                       unit='块', reference_price=800)
        db.session.add_all([p1, p2])
        db.session.flush()
        s1 = SpareStock(spare_part_id=p1.id, location='A1', quantity=3)
        db.session.add(s1)
        db.session.commit()
        yield {'c1': c1.id, 'c2': c2.id, 'p1': p1.id, 'p2': p2.id, 's1': s1.id}


# ==================== 备件档案 ====================
class TestSparePartList:
    def test_list_shape_with_stock_aggregate(self, op_client, seed):
        r = op_client.get('/api/spare-parts')
        assert r.status_code == 200
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['total'] == 2
        by_id = {i['id']: i for i in data['items']}
        item = by_id[seed['p1']]
        assert set(['id', 'code', 'name', 'category', 'brand', 'model', 'specification',
                    'unit', 'min_stock', 'reference_price', 'remark',
                    'total_stock', 'stock_alert']).issubset(item.keys())
        # LEFT JOIN 聚合：p1 库存 3 < 安全库存 5 → 预警
        assert item['total_stock'] == 3
        assert item['stock_alert'] is True
        assert item['stock_alert_label'] == '库存预警'
        assert by_id[seed['p2']]['total_stock'] == 0
        assert by_id[seed['p2']]['stock_alert'] is False
        assert by_id[seed['p2']]['stock_alert_label'] == '正常'

    def test_search(self, op_client, seed):
        data = op_client.get('/api/spare-parts', query_string={'search': '风扇'}).get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['name'] == '风扇模块'

    def test_filter_category(self, op_client, seed):
        data = op_client.get('/api/spare-parts', query_string={'category': '存储'}).get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['name'] == '硬盘'

    def test_pagination(self, op_client, seed):
        data = op_client.get('/api/spare-parts', query_string={'page': 1, 'page_size': 1}).get_json()['data']
        assert data['total'] == 2
        assert len(data['items']) == 1

    def test_requires_login(self, client, seed):
        assert client.get('/api/spare-parts').status_code == 401


class TestSparePartDetail:
    def test_detail_with_related_lists(self, op_client, seed, app):
        with app.app_context():
            db.session.add(PurchaseOrder(spare_part_id=seed['p1'], quantity=2,
                                         unit_price=90, total=180, operator='op'))
            db.session.add(SalesOrder(spare_part_id=seed['p1'], customer_id=seed['c1'],
                                      quantity=1, unit_price=150, total=150, operator='op'))
            db.session.commit()
        d = op_client.get(f"/api/spare-parts/{seed['p1']}").get_json()['data']
        assert d['name'] == '风扇模块'
        assert d['total_stock'] == 3
        assert len(d['stocks']) == 1
        assert d['stocks'][0]['location'] == 'A1'
        assert d['stocks'][0]['quantity'] == 3
        assert len(d['purchases']) == 1
        assert d['purchases'][0]['quantity'] == 2
        assert len(d['sales']) == 1
        assert d['sales'][0]['customer_name'] == '销售客户A'

    def test_detail_not_found(self, op_client, seed):
        assert op_client.get('/api/spare-parts/99999').status_code == 404


class TestSparePartCrud:
    def test_create(self, op_client, seed, app):
        r = op_client.post('/api/spare-parts', json={
            'name': '电源模块', 'code': 'SP-PWR-01', 'category': '电源', 'brand': '华为',
            'model': 'PWR-X', 'specification': '800W', 'unit': '个', 'min_stock': 2,
            'reference_price': 500, 'remark': '测试',
        })
        assert r.status_code == 200
        with app.app_context():
            p = SparePart.query.filter_by(name='电源模块').first()
            assert p is not None
            assert p.brand == '华为'
            assert p.min_stock == 2

    def test_create_duplicate_name(self, op_client, seed):
        r = op_client.post('/api/spare-parts', json={'name': '风扇模块'})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1

    def test_create_empty_name(self, op_client, seed):
        r = op_client.post('/api/spare-parts', json={'name': '  '})
        assert r.status_code == 400

    def test_update(self, op_client, seed, app):
        r = op_client.put(f"/api/spare-parts/{seed['p2']}", json={
            'name': '硬盘-改名', 'category': '存储', 'min_stock': 3, 'reference_price': 900,
        })
        assert r.status_code == 200
        with app.app_context():
            p = SparePart.query.get(seed['p2'])
            assert p.name == '硬盘-改名'
            assert p.min_stock == 3

    def test_delete_ok_without_stocks(self, admin_client, seed, app):
        r = admin_client.delete(f"/api/spare-parts/{seed['p2']}")
        assert r.status_code == 200
        with app.app_context():
            assert SparePart.query.get(seed['p2']) is None

    def test_delete_blocked_with_stocks(self, admin_client, seed, app):
        r = admin_client.delete(f"/api/spare-parts/{seed['p1']}")
        assert r.status_code == 400
        assert '库存' in r.get_json()['message']
        with app.app_context():
            assert SparePart.query.get(seed['p1']) is not None

    def test_delete_forbidden_for_operator(self, op_client, seed):
        """operator 有 spare:add/edit 但无 spare:delete"""
        assert op_client.delete(f"/api/spare-parts/{seed['p2']}").status_code == 403

    def test_create_forbidden_for_sales(self, sales_client, seed):
        """sales 只有 spare:view"""
        assert sales_client.post('/api/spare-parts', json={'name': 'X'}).status_code == 403


# ==================== 库存 ====================
class TestSpareStock:
    def test_list_joins_part_name(self, op_client, seed):
        data = op_client.get('/api/spare-stocks').get_json()['data']
        assert data['total'] == 1
        item = data['items'][0]
        assert item['spare_part_name'] == '风扇模块'
        assert item['quantity'] == 3

    def test_list_filter_by_part(self, op_client, seed):
        data = op_client.get('/api/spare-stocks',
                             query_string={'spare_part_id': seed['p2']}).get_json()['data']
        assert data['total'] == 0

    def test_create(self, op_client, seed, app):
        r = op_client.post('/api/spare-stocks', json={
            'spare_part_id': seed['p2'], 'location': 'B2', 'quantity': 10, 'unit_price': 780,
        })
        assert r.status_code == 200
        with app.app_context():
            s = SpareStock.query.filter_by(spare_part_id=seed['p2']).first()
            assert s.quantity == 10
            assert s.location == 'B2'

    def test_create_negative_rejected(self, op_client, seed):
        r = op_client.post('/api/spare-stocks', json={
            'spare_part_id': seed['p1'], 'quantity': -5,
        })
        assert r.status_code == 400
        assert '负数' in r.get_json()['message']

    def test_create_without_part(self, op_client, seed):
        r = op_client.post('/api/spare-stocks', json={'quantity': 1})
        assert r.status_code == 400

    def test_update(self, op_client, seed, app):
        r = op_client.put(f"/api/spare-stocks/{seed['s1']}", json={
            'spare_part_id': seed['p1'], 'location': 'A2', 'quantity': 8, 'unit_price': 100,
        })
        assert r.status_code == 200
        with app.app_context():
            s = SpareStock.query.get(seed['s1'])
            assert s.quantity == 8
            assert s.location == 'A2'

    def test_update_negative_rejected(self, op_client, seed):
        r = op_client.put(f"/api/spare-stocks/{seed['s1']}", json={'quantity': -1})
        assert r.status_code == 400

    def test_delete(self, admin_client, seed, app):
        r = admin_client.delete(f"/api/spare-stocks/{seed['s1']}")
        assert r.status_code == 200
        with app.app_context():
            assert SpareStock.query.get(seed['s1']) is None


# ==================== 采购 / 销售订单 ====================
class TestPurchaseOrder:
    def test_create_adds_stock(self, op_client, seed, app):
        r = op_client.post('/api/purchase-orders', json={
            'spare_part_id': seed['p1'], 'quantity': 2, 'unit_price': 90,
            'supplier': '华为代理', 'purchase_date': '2026-07-01',
        })
        assert r.status_code == 200
        with app.app_context():
            po = PurchaseOrder.query.first()
            assert po is not None
            assert po.supplier_name == '华为代理'
            assert po.total == 180
            assert po.operator == 'op'
            s = SpareStock.query.filter_by(spare_part_id=seed['p1']).first()
            assert s.quantity == 5  # 3 + 2 自动入库

    def test_create_zero_quantity_rejected(self, op_client, seed):
        r = op_client.post('/api/purchase-orders', json={'spare_part_id': seed['p1'], 'quantity': 0})
        assert r.status_code == 400

    def test_create_without_part(self, op_client, seed):
        r = op_client.post('/api/purchase-orders', json={'quantity': 3})
        assert r.status_code == 400

    def test_list_shape(self, op_client, seed, app):
        with app.app_context():
            db.session.add(PurchaseOrder(spare_part_id=seed['p1'], quantity=2, unit_price=90,
                                         total=180, supplier_name='华为代理', operator='op'))
            db.session.commit()
        data = op_client.get('/api/purchase-orders').get_json()['data']
        assert data['total'] == 1
        item = data['items'][0]
        assert item['spare_part_name'] == '风扇模块'
        assert item['supplier_name'] == '华为代理'

    def test_delete_reverses_stock(self, admin_client, seed, app):
        with app.app_context():
            po = PurchaseOrder(spare_part_id=seed['p1'], quantity=2, unit_price=90,
                               total=180, operator='admin')
            db.session.add(po)
            db.session.commit()
            po_id = po.id
        r = admin_client.delete(f'/api/purchase-orders/{po_id}')
        assert r.status_code == 200
        with app.app_context():
            assert PurchaseOrder.query.get(po_id) is None
            s = SpareStock.query.filter_by(spare_part_id=seed['p1']).first()
            assert s.quantity == 1  # 3 - 2

    def test_delete_forbidden_for_operator(self, op_client, seed, app):
        with app.app_context():
            po = PurchaseOrder(spare_part_id=seed['p1'], quantity=1, operator='op')
            db.session.add(po)
            db.session.commit()
            po_id = po.id
        assert op_client.delete(f'/api/purchase-orders/{po_id}').status_code == 403


class TestSalesOrder:
    def test_create_fifo_deducts_stock(self, op_client, seed, app):
        with app.app_context():
            db.session.add(SpareStock(spare_part_id=seed['p1'], location='A1', quantity=10))
            db.session.commit()
        r = op_client.post('/api/sales-orders', json={
            'spare_part_id': seed['p1'], 'customer_id': seed['c1'], 'quantity': 4,
            'unit_price': 150, 'sales_date': '2026-07-02',
        })
        assert r.status_code == 200
        with app.app_context():
            so = SalesOrder.query.first()
            assert so is not None
            assert so.customer_id == seed['c1']
            assert so.total == 600
            stocks = SpareStock.query.filter_by(spare_part_id=seed['p1']).order_by(SpareStock.id).all()
            assert sum(s.quantity for s in stocks) == 9  # 3 + 10 - 4

    def test_create_insufficient_stock_rejected(self, op_client, seed):
        r = op_client.post('/api/sales-orders', json={
            'spare_part_id': seed['p1'], 'customer_id': seed['c1'], 'quantity': 100,
        })
        assert r.status_code == 400
        assert '库存不足' in r.get_json()['message']

    def test_list_joins_names(self, op_client, seed, app):
        with app.app_context():
            db.session.add(SalesOrder(spare_part_id=seed['p1'], customer_id=seed['c1'],
                                      quantity=1, unit_price=150, total=150, operator='op'))
            db.session.commit()
        data = op_client.get('/api/sales-orders').get_json()['data']
        assert data['total'] == 1
        item = data['items'][0]
        assert item['spare_part_name'] == '风扇模块'
        assert item['customer_name'] == '销售客户A'

    def test_delete_restores_stock(self, admin_client, seed, app):
        with app.app_context():
            so = SalesOrder(spare_part_id=seed['p1'], customer_id=seed['c1'],
                            quantity=2, unit_price=150, total=300, operator='admin')
            db.session.add(so)
            db.session.commit()
            so_id = so.id
        r = admin_client.delete(f'/api/sales-orders/{so_id}')
        assert r.status_code == 200
        with app.app_context():
            assert SalesOrder.query.get(so_id) is None
            s = SpareStock.query.filter_by(spare_part_id=seed['p1']).first()
            assert s.quantity == 5  # 3 + 2 回补

    def test_requires_sales_perm(self, viewer_client, seed):
        """viewer 有 spare:view 但无 spare:add"""
        assert viewer_client.post('/api/sales-orders', json={
            'spare_part_id': seed['p1'], 'quantity': 1,
        }).status_code == 403


class TestSpareDicts:
    def test_dicts_shape(self, op_client, seed):
        data = op_client.get('/api/dicts/spare').get_json()['data']
        assert {p['id'] for p in data['spare_parts']} == {seed['p1'], seed['p2']}
        assert {c['id'] for c in data['customers']} == {seed['c1'], seed['c2']}
        assert set(data['categories']) == {'散热', '存储'}


# ==================== 销售管线：商机 ====================
class TestOpportunity:
    def test_list_with_stage_filter_and_search(self, sales_client, seed, app):
        with app.app_context():
            db.session.add(Opportunity(title='采购防火墙', customer_id=seed['c1'],
                                       stage='需求确认', expected_amount=50000))
            db.session.add(Opportunity(title='机房搬迁', customer_id=seed['c2'],
                                       stage='成交', expected_amount=200000))
            db.session.commit()
        data = sales_client.get('/api/opportunities').get_json()['data']
        assert data['total'] == 2
        data = sales_client.get('/api/opportunities',
                                query_string={'stage': '成交'}).get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['title'] == '机房搬迁'
        data = sales_client.get('/api/opportunities',
                                query_string={'search': '防火墙'}).get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['customer_name'] == '销售客户A'

    def test_create(self, sales_client, seed, app):
        r = sales_client.post('/api/opportunities', json={
            'title': '新商机', 'customer_id': seed['c1'], 'stage': '初步接触',
            'expected_amount': 10000, 'expected_close_date': '2026-12-31', 'remark': 'r',
        })
        assert r.status_code == 200
        with app.app_context():
            o = Opportunity.query.filter_by(title='新商机').first()
            assert o is not None
            assert o.stage == '初步接触'
            assert o.owner == 'sales'

    def test_create_empty_title(self, sales_client, seed):
        r = sales_client.post('/api/opportunities', json={'title': ''})
        assert r.status_code == 400

    def test_create_invalid_stage(self, sales_client, seed):
        r = sales_client.post('/api/opportunities', json={'title': 'X', 'stage': '乱写'})
        assert r.status_code == 400
        assert '阶段' in r.get_json()['message']

    def test_update(self, sales_client, seed, app):
        with app.app_context():
            o = Opportunity(title='旧商机', stage='初步接触')
            db.session.add(o)
            db.session.commit()
            oid = o.id
        r = sales_client.put(f'/api/opportunities/{oid}', json={
            'title': '旧商机-改', 'stage': '商务谈判', 'expected_amount': 888,
        })
        assert r.status_code == 200
        with app.app_context():
            o = Opportunity.query.get(oid)
            assert o.title == '旧商机-改'
            assert o.stage == '商务谈判'

    def test_delete(self, sales_client, seed, app):
        with app.app_context():
            o = Opportunity(title='待删商机')
            db.session.add(o)
            db.session.commit()
            oid = o.id
        assert sales_client.delete(f'/api/opportunities/{oid}').status_code == 200
        with app.app_context():
            assert Opportunity.query.get(oid) is None

    def test_forbidden_for_operator(self, op_client, seed):
        """operator 只有 sales:view"""
        assert op_client.post('/api/opportunities', json={'title': 'X'}).status_code == 403

    def test_detail(self, sales_client, seed, app):
        with app.app_context():
            o = Opportunity(title='详情商机', customer_id=seed['c1'], stage='成交')
            db.session.add(o)
            db.session.commit()
            oid = o.id
        d = sales_client.get(f'/api/opportunities/{oid}').get_json()['data']
        assert d['title'] == '详情商机'
        assert d['customer_name'] == '销售客户A'
        assert d['stage'] == '成交'


# ==================== 销售管线：报价 ====================
class TestQuotation:
    def test_list_and_create(self, sales_client, seed, app):
        r = sales_client.post('/api/quotations', json={
            'number': 'Q-2026-001', 'customer_id': seed['c1'], 'total_amount': 5000,
            'status': '已发送', 'valid_until': '2026-12-31',
        })
        assert r.status_code == 200
        with app.app_context():
            q = Quotation.query.filter_by(number='Q-2026-001').first()
            assert q is not None
            assert q.status == '已发送'
            assert q.total_amount == 5000
        data = sales_client.get('/api/quotations').get_json()['data']
        assert data['total'] == 1
        item = data['items'][0]
        assert item['customer_name'] == '销售客户A'

    def test_list_filter_status(self, sales_client, seed, app):
        with app.app_context():
            db.session.add_all([
                Quotation(number='Q-1', status='草稿', total_amount=100),
                Quotation(number='Q-2', status='已接受', total_amount=200),
            ])
            db.session.commit()
        data = sales_client.get('/api/quotations',
                                query_string={'status': '已接受'}).get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['number'] == 'Q-2'

    def test_update_and_delete(self, sales_client, seed, app):
        with app.app_context():
            q = Quotation(number='Q-OLD', status='草稿', total_amount=100)
            db.session.add(q)
            db.session.commit()
            qid = q.id
        r = sales_client.put(f'/api/quotations/{qid}', json={
            'number': 'Q-NEW', 'status': '已接受', 'total_amount': 999,
        })
        assert r.status_code == 200
        with app.app_context():
            q = Quotation.query.get(qid)
            assert q.number == 'Q-NEW'
            assert q.status == '已接受'
        assert sales_client.delete(f'/api/quotations/{qid}').status_code == 200
        with app.app_context():
            assert Quotation.query.get(qid) is None

    def test_invalid_status_rejected(self, sales_client, seed):
        r = sales_client.post('/api/quotations', json={'number': 'Q-X', 'status': '乱写'})
        assert r.status_code == 400


# ==================== 销售管线：合同（含自动任务生成） ====================
class TestContract:
    @pytest.fixture()
    def template(self, app):
        with app.app_context():
            t = InspectionTaskTemplate(name='月度巡检模板', is_active=True)
            db.session.add(t)
            db.session.commit()
            return t.id

    def test_create_and_list(self, sales_client, seed, app, template):
        r = sales_client.post('/api/contracts', json={
            'number': 'CT-2026-001', 'title': '维保合同', 'customer_id': seed['c1'],
            'amount': 100000, 'status': '执行中',
            'start_date': '2026-01-01', 'end_date': '2026-12-31',
            'inspection_frequency': '', 'task_template_id': None, 'auto_generate_tasks': False,
        })
        assert r.status_code == 200
        with app.app_context():
            c = Contract.query.filter_by(number='CT-2026-001').first()
            assert c is not None
            assert c.amount == 100000
        data = sales_client.get('/api/contracts').get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['customer_name'] == '销售客户A'

    def test_create_auto_generates_tasks(self, sales_client, seed, app, template):
        """执行中 + 巡检频率 + 模板 + 自动生成 → 响应返回 generated 且任务入库"""
        today = date.today()
        start = (today - timedelta(days=75)).strftime('%Y-%m-%d')
        end = (today + timedelta(days=300)).strftime('%Y-%m-%d')
        r = sales_client.post('/api/contracts', json={
            'title': '自动巡检合同', 'customer_id': seed['c1'], 'status': '执行中',
            'start_date': start, 'end_date': end,
            'inspection_frequency': '每月', 'task_template_id': template,
            'auto_generate_tasks': True,
        })
        assert r.status_code == 200
        res = r.get_json()['data']
        assert res['generated'] >= 1
        with app.app_context():
            c = Contract.query.get(res['id'])
            assert c.last_generated_date is not None
            tasks = InspectionTask.query.filter_by(contract_id=res['id'],
                                                   source='合同自动生成').all()
            assert len(tasks) == res['generated']
            assert tasks[0].task_template_id == template

    def test_create_skips_without_frequency(self, sales_client, seed, app, template):
        r = sales_client.post('/api/contracts', json={
            'title': '无频率合同', 'customer_id': seed['c1'], 'status': '执行中',
            'inspection_frequency': '', 'task_template_id': template,
            'auto_generate_tasks': True,
        })
        assert r.status_code == 200
        assert r.get_json()['data']['generated'] == 0

    def test_update_resets_auto_config(self, sales_client, seed, app, template):
        with app.app_context():
            c = Contract(title='旧合同', status='执行中', inspection_frequency='每月',
                         task_template_id=template, auto_generate_tasks=True)
            db.session.add(c)
            db.session.commit()
            cid = c.id
        r = sales_client.put(f'/api/contracts/{cid}', json={
            'title': '旧合同-改', 'inspection_frequency': '每季度',
            'task_template_id': template, 'auto_generate_tasks': False,
        })
        assert r.status_code == 200
        with app.app_context():
            c = Contract.query.get(cid)
            assert c.title == '旧合同-改'
            assert c.inspection_frequency == '每季度'
            assert c.auto_generate_tasks is False

    def test_delete(self, sales_client, seed, app):
        with app.app_context():
            c = Contract(title='待删合同')
            db.session.add(c)
            db.session.commit()
            cid = c.id
        assert sales_client.delete(f'/api/contracts/{cid}').status_code == 200
        with app.app_context():
            assert Contract.query.get(cid) is None


# ==================== 销售管线：项目 ====================
class TestProject:
    def test_list_and_create(self, sales_client, seed, app):
        with app.app_context():
            c = Contract(title='关联合同', status='执行中')
            db.session.add(c)
            db.session.commit()
            cid = c.id
        r = sales_client.post('/api/projects', json={
            'name': '机房改造项目', 'contract_id': cid, 'customer_id': seed['c1'],
            'manager': '张三', 'status': '进行中', 'progress': 40, 'budget': 80000,
            'start_date': '2026-05-01', 'end_date': '2026-10-01',
        })
        assert r.status_code == 200
        with app.app_context():
            p = Project.query.filter_by(name='机房改造项目').first()
            assert p is not None
            assert p.manager == '张三'
            assert p.progress == 40
        data = sales_client.get('/api/projects').get_json()['data']
        assert data['total'] == 1
        item = data['items'][0]
        assert item['contract_title'] == '关联合同'
        assert item['customer_name'] == '销售客户A'

    def test_create_empty_name(self, sales_client, seed):
        r = sales_client.post('/api/projects', json={'name': ''})
        assert r.status_code == 400

    def test_filter_status(self, sales_client, seed, app):
        with app.app_context():
            db.session.add_all([
                Project(name='P-进行中', status='进行中'),
                Project(name='P-未启动', status='未启动'),
            ])
            db.session.commit()
        data = sales_client.get('/api/projects',
                                query_string={'status': '未启动'}).get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['name'] == 'P-未启动'

    def test_update_and_delete(self, sales_client, seed, app):
        with app.app_context():
            p = Project(name='旧项目', status='未启动', progress=0)
            db.session.add(p)
            db.session.commit()
            pid = p.id
        r = sales_client.put(f'/api/projects/{pid}', json={
            'name': '旧项目-改', 'status': '已完成', 'progress': 100,
        })
        assert r.status_code == 200
        with app.app_context():
            p = Project.query.get(pid)
            assert p.status == '已完成'
            assert p.progress == 100
        assert sales_client.delete(f'/api/projects/{pid}').status_code == 200
        with app.app_context():
            assert Project.query.get(pid) is None

    def test_invalid_status_rejected(self, sales_client, seed):
        r = sales_client.post('/api/projects', json={'name': 'X', 'status': '乱写'})
        assert r.status_code == 400


class TestSalesDicts:
    def test_dicts_shape(self, sales_client, seed, app):
        with app.app_context():
            db.session.add_all([
                Opportunity(title='商机1'),
                Contract(title='合同1'),
                InspectionTaskTemplate(name='模板1', is_active=True),
            ])
            db.session.commit()
        data = sales_client.get('/api/dicts/sales').get_json()['data']
        assert data['opp_stages'] == ['初步接触', '需求确认', '方案报价', '商务谈判', '成交', '失败']
        assert data['quotation_statuses'] == ['草稿', '已发送', '已接受', '已拒绝']
        assert data['contract_statuses'] == ['草签', '已签', '执行中', '已完成', '已终止']
        assert data['project_statuses'] == ['未启动', '进行中', '已完成', '已暂停']
        assert data['frequencies'] == ['每月', '每季度', '每半年', '每年']
        assert any(t['name'] == '模板1' for t in data['templates'])
        assert {c['id'] for c in data['customers']} == {seed['c1'], seed['c2']}
        assert any(o['title'] == '商机1' for o in data['opportunities'])
        assert any(c['title'] == '合同1' for c in data['contracts'])

    def test_requires_sales_perm(self, op_client, seed):
        """operator 只有 sales:view，可访问字典"""
        assert op_client.get('/api/dicts/sales').status_code == 200
