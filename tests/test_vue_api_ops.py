# -*- coding: utf-8 -*-
"""P3 知识库 / 故障 / 报告 Vue API：列表/详情/增删改/字典/权限/聚合"""
import io
import os
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
                              content='x', created_by='admin')
            db.session.add(k)
            db.session.flush()
            # 模拟存量 NULL（S6 模型 default=False 后 ORM 不再落 NULL，用 SQL 置空）
            from sqlalchemy import text
            db.session.execute(
                text('UPDATE knowledge_base SET is_published = NULL WHERE id = :id'),
                {'id': k.id})
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

    def test_default_draft(self, op_client, app):
        """S6 发布审核流：新建默认草稿（未发布）；显式 is_published=true 可直发"""
        r = op_client.post('/api/knowledge-base', json={'title': '默认草稿'})
        assert r.status_code == 200
        with app.app_context():
            assert KnowledgeBase.query.filter_by(title='默认草稿').first().is_published is False
        r2 = op_client.post('/api/knowledge-base', json={'title': '直发', 'is_published': True})
        assert r2.status_code == 200
        with app.app_context():
            assert KnowledgeBase.query.filter_by(title='直发').first().is_published is True

    def test_stored_xss_is_sanitized(self, op_client, app):
        payload = ('<p onclick="alert(1)">安全<strong>正文</strong></p>'
                   '<script>alert(2)</script>'
                   '<a href="javascript:alert(3)">危险链接</a>'
                   '<a href="https://example.com" target="_blank">安全链接</a>')
        r = op_client.post('/api/knowledge-base', json={'title': '净化测试', 'content': payload})
        assert r.status_code == 200
        kb_id = r.get_json()['data']['id']
        with app.app_context():
            content = db.session.get(KnowledgeBase, kb_id).content
        assert '<script' not in content
        assert 'alert(2)' not in content
        assert 'onclick' not in content
        assert 'javascript:' not in content
        assert '<strong>正文</strong>' in content
        assert 'href="https://example.com"' in content
        assert 'rel="noopener noreferrer"' in content


class TestKbPublish:
    def test_publish_flow(self, op_client, app):
        """S6 发布审核：草稿 → publish 端点 → 已发布（记录发布人/时间）"""
        r = op_client.post('/api/knowledge-base', json={'title': '待发布'})
        kb_id = r.get_json()['data']['id']
        with app.app_context():
            assert KnowledgeBase.query.get(kb_id).is_published is False
        r2 = op_client.post(f'/api/knowledge-base/{kb_id}/publish', json={'publish': True})
        assert r2.status_code == 200
        with app.app_context():
            k = KnowledgeBase.query.get(kb_id)
            assert k.is_published is True
            assert k.published_by == 'op'
            assert k.published_at is not None
        # 下架
        r3 = op_client.post(f'/api/knowledge-base/{kb_id}/publish', json={'publish': False})
        assert r3.status_code == 200
        with app.app_context():
            k = KnowledgeBase.query.get(kb_id)
            assert k.is_published is False
            assert k.published_by == ''

    def test_publish_requires_perm(self, viewer_client, app):
        r = viewer_client.post('/api/knowledge-base/1/publish', json={'publish': True})
        assert r.status_code == 403


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

    def test_update_sanitizes_xss(self, op_client, kb_seed, app):
        r = op_client.put(f"/api/knowledge-base/{kb_seed['k1']}", json={
            'title': '更新净化', 'content': '<img src=x onerror=alert(1)><iframe>bad</iframe>'})
        assert r.status_code == 200
        with app.app_context():
            content = db.session.get(KnowledgeBase, kb_seed['k1']).content
        assert 'onerror' not in content
        assert '<iframe' not in content
        assert 'bad' not in content

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


class TestKbAttachments:
    def _upload(self, client, kb_id):
        return client.post(f'/api/knowledge-base/{kb_id}/attachments',
                           data={'files': [
                               (io.BytesIO(b'%PDF-1.4 fake pdf'), '指南.pdf'),
                               (io.BytesIO(b'PNG fake'), '拓扑图.png'),
                               (io.BytesIO(b'not allowed'), '脚本.sh'),
                           ]},
                           content_type='multipart/form-data')

    def test_upload_and_list_in_payload(self, op_client, kb_seed, app):
        r = self._upload(op_client, kb_seed['k1'])
        assert r.status_code == 200
        body = r.get_json()
        assert body['code'] == 0
        assert body['data']['added'] == 2  # .sh 被白名单拒绝
        with app.app_context():
            from models import KnowledgeAttachment
            atts = KnowledgeAttachment.query.filter_by(knowledge_id=kb_seed['k1']).all()
            assert len(atts) == 2
            # 磁盘文件已落盘
            assert all(os.path.isfile(os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'static', a.file_path)) for a in atts)
        # 详情 payload 含附件
        r = op_client.get(f"/api/knowledge-base/{kb_seed['k1']}")
        atts = r.get_json()['data']['attachments']
        assert len(atts) == 2
        assert {a['file_name'] for a in atts} == {'指南.pdf', '拓扑图.png'}

    def test_preview_and_download(self, op_client, kb_seed, app):
        self._upload(op_client, kb_seed['k1'])
        with app.app_context():
            from models import KnowledgeAttachment
            att = KnowledgeAttachment.query.filter_by(knowledge_id=kb_seed['k1']).first()
            att_id = att.id
        r = op_client.get(f"/api/knowledge-base/{kb_seed['k1']}/attachments/{att_id}/preview")
        assert r.status_code == 200
        assert r.data == b'%PDF-1.4 fake pdf'
        r = op_client.get(f"/api/knowledge-base/{kb_seed['k1']}/attachments/{att_id}/download")
        assert r.status_code == 200
        assert r.data == b'%PDF-1.4 fake pdf'

    def test_cross_entry_attachment_404(self, op_client, kb_seed, app):
        """A 条目的附件不能通过 B 条目访问"""
        self._upload(op_client, kb_seed['k1'])
        with app.app_context():
            from models import KnowledgeAttachment
            att_id = KnowledgeAttachment.query.filter_by(knowledge_id=kb_seed['k1']).first().id
        r = op_client.get(f"/api/knowledge-base/{kb_seed['k2']}/attachments/{att_id}/preview")
        assert r.status_code == 404

    def test_upload_requires_edit_perm(self, viewer_client, kb_seed):
        r = viewer_client.post(f"/api/knowledge-base/{kb_seed['k1']}/attachments",
                               data={'files': [(io.BytesIO(b'x'), 'a.pdf')]},
                               content_type='multipart/form-data')
        assert r.status_code == 403

    def test_delete_attachment_removes_file(self, op_client, kb_seed, app):
        self._upload(op_client, kb_seed['k1'])
        with app.app_context():
            from models import KnowledgeAttachment
            att = KnowledgeAttachment.query.filter_by(knowledge_id=kb_seed['k1']).first()
            att_id, full = att.id, att.file_path
        r = op_client.delete(f"/api/knowledge-base/{kb_seed['k1']}/attachments/{att_id}")
        assert r.status_code == 200
        with app.app_context():
            from models import KnowledgeAttachment
            assert KnowledgeAttachment.query.get(att_id) is None
        assert not os.path.isfile(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', full))

    def test_delete_kb_cleans_physical_files(self, admin_client, kb_seed, app):
        self._upload(admin_client, kb_seed['k1'])
        with app.app_context():
            from models import KnowledgeAttachment
            paths = [a.file_path for a in
                     KnowledgeAttachment.query.filter_by(knowledge_id=kb_seed['k1']).all()]
            assert paths
        r = admin_client.delete(f"/api/knowledge-base/{kb_seed['k1']}")
        assert r.status_code == 200
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
        assert all(not os.path.isfile(os.path.join(base, p)) for p in paths)


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
        from scripts.seed_fault_categories import seed_fault_categories

        seed_fault_categories(app)
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

    def test_create_with_category_levels(self, op_client, fault_seed, app):
        """三级分类写入 fault_category_level1/2/3（新数据只写三级列）"""
        r = op_client.post('/api/faults', json={
            'title': '摄像头故障', 'customer_id': fault_seed['c'],
            'category_l1': '监控系统故障', 'category_l2': '摄像头故障',
            'category_l3': '单个摄像头无画面（黑屏）', 'result': '已解决'})
        assert r.status_code == 200
        with app.app_context():
            f = Fault.query.filter_by(title='摄像头故障').first()
            assert f.fault_category_level1 == '监控系统故障'
            assert f.fault_category_level2 == '摄像头故障'
            assert f.fault_category_level3 == '单个摄像头无画面（黑屏）'
        r = op_client.get('/api/faults')
        item = r.get_json()['data']['items'][0]
        assert item['fault_category'] == '监控系统故障/摄像头故障/单个摄像头无画面（黑屏）'

    def test_rejects_incomplete_fault_category(self, op_client, fault_seed):
        r = op_client.post('/api/faults', json={
            'title': '残缺分类故障', 'customer_id': fault_seed['c'],
            'category_l1': '监控系统故障', 'category_l2': '摄像头故障'})
        assert r.status_code == 400
        assert '完整' in r.get_json()['message']

    def test_filter_by_category_l1(self, op_client, fault_seed, app):
        with app.app_context():
            f = Fault.query.get(fault_seed['f'])
            f.fault_category_level1 = '网络与通信故障'
            f.fault_category_level2 = '内网故障'
            f.fault_category_level3 = '单个电脑无法访问内网'
            db.session.commit()
        r = op_client.get('/api/faults', query_string={'category_l1': '网络与通信故障'})
        assert r.get_json()['data']['total'] == 1
        r = op_client.get('/api/faults', query_string={'category_l1': '监控系统故障'})
        assert r.get_json()['data']['total'] == 0

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
    def test_dicts_tree(self, op_client, app):
        """/api/dicts/faults 返回三级分类树"""
        with app.app_context():
            l1 = FaultType(name='网络故障', level=1)
            db.session.add(l1)
            db.session.flush()
            db.session.add(FaultType(name='内网故障', parent_id=l1.id, level=2))
            db.session.commit()
        r = op_client.get('/api/dicts/faults')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        roots = data['fault_types']
        assert '网络故障' in [t['name'] for t in roots]
        net = next(t for t in roots if t['name'] == '网络故障')
        assert '内网故障' in [c['name'] for c in net['children']]
        assert '已解决' in data['results']


class TestFaultCategories:
    def test_crud_level_autocompute(self, admin_client, app):
        """分类 CRUD + 层级自动推导 + 有子级不可删 + 被故障引用不可删"""
        r = admin_client.post('/api/fault-categories', json={'name': '网络与通信故障'})
        assert r.status_code == 200
        l1_id = r.get_json()['data']['id']
        r = admin_client.post('/api/fault-categories', json={'name': '内网故障', 'parent_id': l1_id})
        assert r.status_code == 200
        l2_id = r.get_json()['data']['id']
        r = admin_client.post('/api/fault-categories', json={'name': '单个电脑无法访问内网', 'parent_id': l2_id})
        assert r.status_code == 200
        l3_id = r.get_json()['data']['id']
        with app.app_context():
            l2 = FaultType.query.get(l2_id)
            assert l2.level == 2
            l3 = FaultType.query.get(l3_id)
            assert l3.level == 3
        # 树接口含三级嵌套
        r = admin_client.get('/api/fault-categories')
        tree = r.get_json()['data']
        net = next(t for t in tree if t['name'] == '网络与通信故障')
        inner = next(c for c in net['children'] if c['name'] == '内网故障')
        assert '单个电脑无法访问内网' in [c['name'] for c in inner['children']]
        # 重名同级 400
        r = admin_client.post('/api/fault-categories', json={'name': '内网故障', 'parent_id': l1_id})
        assert r.status_code == 400
        # 有子级不可删
        r = admin_client.delete(f'/api/fault-categories/{l1_id}')
        assert r.status_code == 400
        # 更新名称
        r = admin_client.put(f'/api/fault-categories/{l3_id}', json={'name': '单电脑无法访问内网'})
        assert r.status_code == 200
        # 被故障引用不可删
        with app.app_context():
            c = Customer(name='分类客户')
            db.session.add(c)
            db.session.flush()
            db.session.add(Fault(title='引用故障', customer_id=c.id,
                                 fault_category_level3='单电脑无法访问内网'))
            db.session.commit()
        r = admin_client.delete(f'/api/fault-categories/{l3_id}')
        assert r.status_code == 400


class TestFaultCategoryClean:
    def test_clean_renames_prefix_and_deletes_flat(self, app):
        """clean_fault_categories：一级去序号前缀、删旧扁平类型、同步 level1 字符串"""
        from scripts.seed_fault_categories import clean_fault_categories, seed_fault_categories
        with app.app_context():
            # 造旧数据：带前缀一级 + 旧扁平 + 引用
            l1 = FaultType(name='一、网络与通信故障', level=1)
            db.session.add(l1)
            db.session.flush()
            old_flat = FaultType(name='网络中断', level=1)
            db.session.add(old_flat)
            db.session.flush()
            c = Customer(name='清理客户')
            db.session.add(c)
            db.session.flush()
            db.session.add(Fault(title='旧前缀故障', customer_id=c.id,
                                 fault_category_level1='一、网络与通信故障'))
            db.session.add(Ticket(number='WO-CLEAN-001', title='旧前缀工单', customer_id=c.id,
                                  fault_category_level1='网络中断', fault_category_id=old_flat.id,
                                  status='待派单', created_by='admin'))
            db.session.commit()
        with app.app_context():
            renamed, deleted_flat, _vpn = clean_fault_categories()
            seed_fault_categories(app=None)
            db.session.commit()
            assert renamed == 1
            assert deleted_flat == 1
            # 一级已改名、旧扁平已删
            assert FaultType.query.filter_by(name='一、网络与通信故障').first() is None
            assert FaultType.query.filter_by(name='网络与通信故障', parent_id=None).first() is not None
            assert FaultType.query.filter_by(name='网络中断').first() is None
            # level1 字符串同步 + fault_category_id 外键置空
            from models import Fault as _F, Ticket as _T
            f = _F.query.filter_by(title='旧前缀故障').first()
            assert f.fault_category_level1 == '网络与通信故障'
            t = _T.query.filter_by(number='WO-CLEAN-001').first()
            assert t.fault_category_level1 == ''
            assert t.fault_category_id is None


# ==================== 报告中心 ====================
@pytest.fixture()
def report_seed(app):
    """注意：yield 必须在 app_context 外——否则旧上下文/会话贯穿整个用例，
    请求会复用同一会话命中过期的 identity map（读到提交前的旧值）"""
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
        seed = {'c1': c1.id, 'c2': c2.id, 'insp': insp.id, 'fault': flt.id, 'ticket': tkt.id}
    yield seed


class TestReports:
    def test_shape(self, op_client, report_seed, report_dirs):
        """统一列表契约：{items, total, stats}；12 个月窗口内三类记录聚合"""
        r = op_client.get('/api/reports')
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['total'] >= 3  # 近期巡检 + 近期故障 + 近期工单（两年前被窗口排除）
        names = {i['customer_name'] for i in data['items']}
        assert '报告客户A' in names and '报告客户B' in names
        assert data['stats']['total'] == data['total']
        assert data['stats']['customers'] >= 2
        insp = [i for i in data['items'] if i['type'] == 'inspection']
        assert [i['title'] for i in insp] == ['近期巡检']
        assert all(i['has_report'] is False for i in insp)

    def test_old_record_excluded_by_default_window(self, op_client, report_seed, report_dirs):
        data = op_client.get('/api/reports').get_json()['data']
        titles = [i['title'] for i in data['items'] if i['type'] == 'inspection']
        assert '两年前巡检' not in titles

    def test_explicit_date_range_includes_old(self, op_client, report_seed, report_dirs):
        data = op_client.get('/api/reports', query_string={
            'date_from': '2019-01-01', 'date_to': '2021-12-31'}).get_json()['data']
        titles = [i['title'] for i in data['items'] if i['type'] == 'inspection']
        assert '两年前巡检' in titles

    def test_tab_filter(self, op_client, report_seed, report_dirs):
        data = op_client.get('/api/reports', query_string={'tab': 'ticket'}).get_json()['data']
        assert [i['type'] for i in data['items']] == ['ticket']
        assert [i['title'] for i in data['items']] == ['WO-REP-001 · 近期工单']
        assert data['total'] == 1
        assert data['stats']['total'] == 1

    def test_customer_filter(self, op_client, report_seed, report_dirs):
        """客户筛选统一作用于巡检/故障/工单/报告文件"""
        data = op_client.get('/api/reports', query_string={
            'customer_id': report_seed['c1']}).get_json()['data']
        names = {i['customer_name'] for i in data['items']}
        assert names == {'报告客户A'}

    def test_search(self, op_client, report_seed, report_dirs):
        data = op_client.get('/api/reports', query_string={'search': '近期故障'}).get_json()['data']
        assert [i['title'] for i in data['items']] == ['近期故障']

    def test_pagination(self, op_client, app, report_dirs):
        with app.app_context():
            c = Customer(name='海量客户')
            db.session.add(c)
            db.session.flush()
            db.session.add_all([
                Fault(title=f'故障{i}', customer_id=c.id, fault_time=datetime.utcnow())
                for i in range(110)
            ])
            db.session.commit()
        data = op_client.get('/api/reports', query_string={'page_size': 20, 'page': 1}).get_json()['data']
        assert data['total'] == 110
        assert len(data['items']) == 20
        assert data['items'][0]['title'] == '故障109'  # 时间倒序
        last = op_client.get('/api/reports', query_string={'page_size': 20, 'page': 6}).get_json()['data']
        assert len(last['items']) == 10

    def test_submitted_report_included(self, op_client, report_seed, app, report_dirs):
        """工程师上传的现场报告（submitted_report + 提交版本）参与反查：
        记录行 has_report=true，文件 tab 出现该文件并归属客户"""
        from models import SubmissionVersion as _SV
        rel = 'uploads/inspection_reports/rep1/site.docx'
        full = os.path.join(report_dirs['uploads'], 'inspection_reports', 'rep1', 'site.docx')
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as fp:
            fp.write(b'site report')
        try:
            with app.app_context():
                insp = Inspection.query.get(report_seed['insp'])
                insp.submitted_report = rel
                db.session.add(_SV(entity_type='inspection', entity_id=insp.id,
                                   version_no=1, report_file=rel))
                db.session.commit()
            data = op_client.get('/api/reports', query_string={'tab': 'inspection'}).get_json()['data']
            row = next(i for i in data['items'] if i['id'] == report_seed['insp'])
            assert row['has_report'] is True
            assert row['report_name'] == 'site.docx'
            assert row['report_url'].startswith('/api/reports/file/')
            fdata = op_client.get('/api/reports', query_string={'tab': 'file'}).get_json()['data']
            frow = next(i for i in fdata['items'] if i['report_name'] == 'site.docx')
            assert frow['customer_name'] == '报告客户A'
        finally:
            if os.path.exists(full):
                os.remove(full)

    def test_formal_report_file_row(self, op_client, report_seed, app, report_dirs):
        """正式报告（reports/ 根目录 + report_file）→ 文件行归属客户、URL 指向 /reports/、可删除"""
        fname = '巡检报告_报告客户A_20260802_151402.docx'
        full = os.path.join(report_dirs['reports'], fname)
        with open(full, 'wb') as fp:
            fp.write(b'formal report')
        try:
            with app.app_context():
                insp = Inspection.query.get(report_seed['insp'])
                insp.report_file = fname
                db.session.commit()
            data = op_client.get('/api/reports', query_string={'tab': 'file'}).get_json()['data']
            row = next(i for i in data['items'] if i['report_name'] == fname)
            assert row['customer_name'] == '报告客户A'
            assert row['deletable'] is True
            assert row['report_url'].startswith('/reports/')
        finally:
            if os.path.exists(full):
                os.remove(full)

    def test_download_ok(self, op_client, report_dirs):
        full = os.path.join(report_dirs['uploads'], 'inspection_reports', 'down', 'ok.docx')
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as fp:
            fp.write(b'hello report')
        r = None
        try:
            r = op_client.get('/api/reports/file/inspection_reports/down/ok.docx')
            assert r.status_code == 200
            assert r.data == b'hello report'
        finally:
            if r is not None:
                r.close()  # Windows 下文件句柄未释放会导致删除失败
            if os.path.exists(full):
                os.remove(full)

    def test_download_traversal_rejected(self, op_client, report_dirs):
        assert op_client.get('/api/reports/file/..%2F..%2Fapp.py').status_code == 404
        assert op_client.get('/api/reports/file/inspection_reports/nope.docx').status_code == 404

    def test_requires_login(self, client):
        assert client.get('/api/reports').status_code == 401
