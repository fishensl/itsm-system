# -*- coding: utf-8 -*-
"""P3 知识库 / 故障 / 报告 Vue API：列表/详情/增删改/字典/权限/聚合"""
from datetime import datetime

import pytest

from models import db, Customer, Fault, FaultType, KnowledgeBase, Ticket, Inspection


# ==================== 知识库 ====================
@pytest.fixture()
def kb_seed(app):
    with app.app_context():
        k1 = KnowledgeBase(title='交换机重启排查', category='故障案例', tags='网络,交换机',
                           content='<p>重启步骤</p>', is_published=True, created_by='admin')
        k2 = KnowledgeBase(title='巡检手册v2', category='设备手册', tags='手册',
                           content='巡检要点', is_published=False, created_by='op')
        db.session.add_all([k1, k2])
        db.session.commit()
        yield {'k1': k1.id, 'k2': k2.id}


class TestKbList:
    def test_list_shape(self, op_client, kb_seed):
        r = op_client.get('/api/knowledge-base')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['total'] == 2
        item = data['items'][0]
        assert item['title'] == '巡检手册v2'
        assert item['category'] == '设备手册'
        assert item['published_label'] in ('已发布', '未发布')
        assert set(('id', 'title', 'category', 'created_by', 'view_count',
                    'helpful_count', 'is_published', 'tags', 'created_at')) <= set(item)

    def test_search_title(self, op_client, kb_seed):
        r = op_client.get('/api/knowledge-base', query_string={'search': '交换机'})
        assert r.get_json()['data']['total'] == 1

    def test_search_tags(self, op_client, kb_seed):
        r = op_client.get('/api/knowledge-base', query_string={'search': '手册'})
        assert r.get_json()['data']['total'] == 1

    def test_filter_category(self, op_client, kb_seed):
        r = op_client.get('/api/knowledge-base', query_string={'category': '故障案例'})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['title'] == '交换机重启排查'

    def test_filter_published(self, op_client, kb_seed):
        r = op_client.get('/api/knowledge-base', query_string={'is_published': '0'})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['is_published'] is False

    def test_null_published_treated_as_published(self, op_client, app):
        """存量 is_published 为 NULL：视为已发布，且筛选已发布可命中"""
        with app.app_context():
            k = KnowledgeBase(title='存量无发布字段', category='内部规范',
                              content='x', is_published=None, created_by='admin')
            db.session.add(k)
            db.session.commit()
            kid = k.id
        r = op_client.get(f'/api/knowledge-base/{kid}')
        d = r.get_json()['data']
        assert d['is_published'] is True
        assert d['published_label'] == '已发布'
        r = op_client.get('/api/knowledge-base', query_string={'is_published': '1'})
        titles = [i['title'] for i in r.get_json()['data']['items']]
        assert '存量无发布字段' in titles


class TestKbDetailAndViewCount:
    def test_detail_includes_content(self, op_client, kb_seed):
        r = op_client.get(f"/api/knowledge-base/{kb_seed['k1']}")
        body = r.get_json()
        assert body['code'] == 0
        assert body['data']['content'] == '<p>重启步骤</p>'

    def test_view_count_increments_atomically(self, op_client, kb_seed, app):
        """原子自增 + 同 session 去重（与旧 SSR 详情页一致）：同人连看两次只 +1"""
        assert op_client.get(f"/api/knowledge-base/{kb_seed['k1']}").get_json()['data']['view_count'] == 1
        assert op_client.get(f"/api/knowledge-base/{kb_seed['k1']}").get_json()['data']['view_count'] == 1
        with app.app_context():
            assert KnowledgeBase.query.get(kb_seed['k1']).view_count == 1


class TestKbCreate:
    def test_create(self, op_client, kb_seed, app):
        r = op_client.post('/api/knowledge-base', json={
            'title': '新知识', 'category': '巡检经验', 'tags': '巡检',
            'content': '<p>x</p>', 'is_published': True})
        assert r.status_code == 200
        with app.app_context():
            k = KnowledgeBase.query.filter_by(title='新知识').first()
            assert k.category == '巡检经验'
            assert k.created_by == 'op'

    def test_create_empty_title(self, op_client):
        r = op_client.post('/api/knowledge-base', json={'title': '  '})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1

    def test_default_published(self, op_client, app):
        r = op_client.post('/api/knowledge-base', json={'title': '默认发布'})
        assert r.status_code == 200
        with app.app_context():
            assert KnowledgeBase.query.filter_by(title='默认发布').first().is_published is True


class TestKbUpdateDelete:
    def test_update(self, op_client, kb_seed, app):
        r = op_client.put(f"/api/knowledge-base/{kb_seed['k1']}", json={
            'title': '改标题', 'category': '内部规范', 'content': '新内容',
            'tags': 'a,b', 'is_published': False})
        assert r.status_code == 200
        with app.app_context():
            k = KnowledgeBase.query.get(kb_seed['k1'])
            assert k.title == '改标题'
            assert k.category == '内部规范'
            assert k.content == '新内容'
            assert k.is_published is False

    def test_update_empty_title(self, op_client, kb_seed):
        r = op_client.put(f"/api/knowledge-base/{kb_seed['k1']}", json={'title': ''})
        assert r.status_code == 400

    def test_delete_by_admin(self, admin_client, kb_seed, app):
        r = admin_client.delete(f"/api/knowledge-base/{kb_seed['k1']}")
        assert r.status_code == 200
        with app.app_context():
            assert KnowledgeBase.query.get(kb_seed['k1']) is None

    def test_operator_cannot_delete(self, op_client, kb_seed, app):
        """operator 无 kb:delete → 403"""
        r = op_client.delete(f"/api/knowledge-base/{kb_seed['k1']}")
        assert r.status_code == 403
        with app.app_context():
            assert KnowledgeBase.query.get(kb_seed['k1']) is not None


class TestKbDicts:
    def test_categories(self, op_client):
        r = op_client.get('/api/dicts/knowledge')
        body = r.get_json()
        assert body['code'] == 0
        assert '故障案例' in body['data']['categories']
        assert '巡检经验' in body['data']['categories']


# ==================== 故障记录 ====================
@pytest.fixture()
def fault_seed(app):
    with app.app_context():
        c = Customer(name='故障客户')
        db.session.add(c)
        db.session.flush()
        f = Fault(title='存储阵列故障', customer_id=c.id, handler='op',
                  fault_type='硬件故障', result='已解决',
                  fault_time=datetime(2026, 1, 15, 10, 0),
                  fault_description='控制器闪存损坏', fault_cause='电池耗尽',
                  solution='更换闪存', impact_range='存储性能下降')
        db.session.add(f)
        db.session.commit()
        yield {'c': c.id, 'f': f.id}


class TestFaultList:
    def test_list_shape(self, op_client, fault_seed):
        r = op_client.get('/api/faults')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['total'] == 1
        item = data['items'][0]
        assert item['customer_name'] == '故障客户'
        assert item['result'] == '已解决'
        assert item['fault_time'] == '2026-01-15 10:00'
        assert set(('id', 'title', 'customer_name', 'handler', 'fault_time',
                    'fault_type', 'result', 'impact_range')) <= set(item)

    def test_filter_type_and_result(self, op_client, fault_seed):
        assert op_client.get('/api/faults', query_string={'fault_type': '硬件故障'}).get_json()['data']['total'] == 1
        assert op_client.get('/api/faults', query_string={'fault_type': '网络故障'}).get_json()['data']['total'] == 0
        assert op_client.get('/api/faults', query_string={'result': '待观察'}).get_json()['data']['total'] == 0
        assert op_client.get('/api/faults', query_string={'result': '已解决'}).get_json()['data']['total'] == 1

    def test_search(self, op_client, fault_seed):
        r = op_client.get('/api/faults', query_string={'search': '存储'})
        assert r.get_json()['data']['total'] == 1


class TestFaultDetail:
    def test_detail_full(self, op_client, fault_seed):
        r = op_client.get(f"/api/faults/{fault_seed['f']}")
        body = r.get_json()
        assert body['code'] == 0
        d = body['data']
        assert d['fault_description'] == '控制器闪存损坏'
        assert d['fault_cause'] == '电池耗尽'
        assert d['solution'] == '更换闪存'
        assert d['impact_range'] == '存储性能下降'


class TestFaultCreateUpdate:
    def test_create_default_handler(self, op_client, fault_seed, app):
        r = op_client.post('/api/faults', json={
            'title': '新故障', 'customer_id': fault_seed['c'], 'fault_type': '网络故障',
            'fault_time': '2026-02-01T09:30', 'result': '待观察',
            'fault_description': '链路抖动', 'impact_range': '办公网'})
        assert r.status_code == 200
        with app.app_context():
            f = Fault.query.filter_by(title='新故障').first()
            assert f.handler == 'op'  # 默认当前用户
            assert f.fault_time.strftime('%Y-%m-%d %H:%M') == '2026-02-01 09:30'
            assert f.result == '待观察'

    def test_create_empty_title(self, op_client):
        r = op_client.post('/api/faults', json={'title': ''})
        assert r.status_code == 400

    def test_update(self, op_client, fault_seed, app):
        r = op_client.put(f"/api/faults/{fault_seed['f']}", json={
            'title': '改故障', 'result': '未解决', 'solution': '返厂维修'})
        assert r.status_code == 200
        with app.app_context():
            f = Fault.query.get(fault_seed['f'])
            assert f.title == '改故障'
            assert f.result == '未解决'
            assert f.solution == '返厂维修'


class TestFaultDelete:
    def test_delete_clears_kb_ref(self, admin_client, fault_seed, app):
        with app.app_context():
            kb = KnowledgeBase(title='关联故障的知识', related_fault_id=fault_seed['f'])
            db.session.add(kb)
            db.session.commit()
            kid = kb.id
        r = admin_client.delete(f"/api/faults/{fault_seed['f']}")
        assert r.status_code == 200
        with app.app_context():
            assert Fault.query.get(fault_seed['f']) is None
            assert KnowledgeBase.query.get(kid).related_fault_id is None

    def test_viewer_cannot_delete(self, viewer_client, fault_seed, app):
        assert viewer_client.delete(f"/api/faults/{fault_seed['f']}").status_code == 403
        with app.app_context():
            assert Fault.query.get(fault_seed['f']) is not None


class TestFaultDicts:
    def test_dicts(self, op_client, app):
        with app.app_context():
            db.session.add(FaultType(name='网络故障', sort_order=1))
            db.session.commit()
        r = op_client.get('/api/dicts/faults')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert '网络故障' in [t['name'] for t in data['fault_types']]
        assert '已解决' in data['results']


# ==================== 报告中心 ====================
@pytest.fixture()
def report_seed(app):
    with app.app_context():
        c1 = Customer(name='报告客户A')
        c2 = Customer(name='报告客户B')
        db.session.add_all([c1, c2])
        db.session.flush()
        old = Inspection(title='两年前巡检', customer_id=c1.id, inspection_date=datetime(2020, 5, 1))
        insp = Inspection(title='近期巡检', customer_id=c1.id, inspection_date=datetime.utcnow())
        flt = Fault(title='近期故障', customer_id=c1.id, result='已解决',
                    fault_time=datetime.utcnow())
        tkt = Ticket(number='WO-REP-001', title='近期工单', customer_id=c2.id,
                      priority='高', status='处理中', created_at=datetime.utcnow())
        db.session.add_all([old, insp, flt, tkt])
        db.session.commit()
        yield {'c1': c1.id, 'c2': c2.id, 'insp': insp.id, 'fault': flt.id, 'ticket': tkt.id}


class TestReports:
    def test_shape(self, op_client, report_seed):
        r = op_client.get('/api/reports')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        names = [b['name'] for b in data['data_order']]
        assert '报告客户A' in names and '报告客户B' in names
        c1 = next(b for b in data['data_order'] if b['name'] == '报告客户A')
        assert c1['counts']['inspection'] == 1  # 两年前的被 12 个月窗口排除
        assert c1['counts']['fault'] == 1
        assert c1['items']['inspection'][0]['id'] == report_seed['insp']
        assert set(data['tab_stats']) == {'all', 'inspection', 'fault', 'ticket', 'file'}
        assert data['tab_stats']['all']['total'] >= 2

    def test_old_record_excluded_by_default_window(self, op_client, report_seed, app):
        with app.app_context():
            insp = Inspection.query.filter_by(title='两年前巡检').first()
            assert insp is not None
        data = op_client.get('/api/reports').get_json()['data']
        for b in data['data_order']:
            for item in b['items']['inspection']:
                assert item['title'] != '两年前巡检'

    def test_explicit_date_range_includes_old(self, op_client, report_seed):
        data = op_client.get('/api/reports', query_string={
            'date_from': '2019-01-01', 'date_to': '2021-12-31'}).get_json()['data']
        found = [b for b in data['data_order'] if b['name'] == '报告客户A']
        assert found and any(i['title'] == '两年前巡检' for i in found[0]['items']['inspection'])

    def test_tab_filter(self, op_client, report_seed):
        data = op_client.get('/api/reports', query_string={'tab': 'ticket'}).get_json()['data']
        names = [b['name'] for b in data['data_order']]
        assert names == ['报告客户B']
        assert data['tab_stats']['ticket']['total'] == 1
        assert data['tab_stats']['inspection']['total'] == 0

    def test_customer_filter(self, op_client, report_seed):
        """客户筛选影响巡检/故障/工单；文件桶与 SSR 一致不受客户过滤"""
        data = op_client.get('/api/reports', query_string={'customer_id': report_seed['c1']}).get_json()['data']
        names = [b['name'] for b in data['data_order']]
        assert '报告客户A' in names
        assert '报告客户B' not in names

    def test_group_capped_at_100(self, op_client, app):
        with app.app_context():
            c = Customer(name='海量客户')
            db.session.add(c)
            db.session.flush()
            db.session.add_all([
                Fault(title=f'故障{i}', customer_id=c.id, fault_time=datetime.utcnow())
                for i in range(110)
            ])
            db.session.commit()
        data = op_client.get('/api/reports').get_json()['data']
        b = next(x for x in data['data_order'] if x['name'] == '海量客户')
        assert b['counts']['fault'] == 110
        assert len(b['items']['fault']) == 100

    def test_requires_login(self, client):
        assert client.get('/api/reports').status_code == 401
