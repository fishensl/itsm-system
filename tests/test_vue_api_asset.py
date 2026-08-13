# -*- coding: utf-8 -*-
"""P4 资产域 Vue API：机柜（/api/v2/rack/*）/ 拓扑（/api/topologies）/ 网络工具（/api/tools/*）

机柜路径使用 /api/v2 前缀：SSR rack 蓝图先注册并占用 /api/rack/*（模板在用），
同 rule 会被遮蔽——与 /api/v2/devices/<id>/reveal-password 的处理一致。
"""
import io
import os

import pytest

from models import db, Customer, Device, Rack, RackInstall, Topology


@pytest.fixture()
def seed(app):
    with app.app_context():
        c1 = Customer(name='机柜API客户A')
        c2 = Customer(name='机柜API客户B')
        db.session.add_all([c1, c2])
        db.session.flush()
        d1 = Device(customer_id=c1.id, device_name='SW-A', brand='华为',
                    model='S5720', ip_address='10.0.0.1')
        d2 = Device(customer_id=c2.id, device_name='FW-B', brand='深信服',
                    model='AF-1000', ip_address='10.0.0.2')
        db.session.add_all([d1, d2])
        db.session.flush()
        r1 = Rack(customer_id=c1.id, name='A-01', total_u=42, color='#0d6efd',
                  pdu_total_w=8000, remark='主柜')
        r2 = Rack(customer_id=c2.id, name='B-02', total_u=42)
        db.session.add_all([r1, r2])
        db.session.flush()
        i1 = RackInstall(rack_id=r1.id, device_id=d1.id, start_u=1, occupy_u=2, rated_w=300)
        i2 = RackInstall(rack_id=r1.id, manual_name='手动小机', manual_brand='IBM',
                         start_u=10, occupy_u=1, rated_w=100)
        db.session.add_all([i1, i2])
        t1 = Topology(name='核心网络', customer_id=c1.id, file_type='image', upload_by='admin')
        t2 = Topology(name='核心网络', customer_id=c1.id, file_type='pdf', upload_by='admin')
        t3 = Topology(name='新建在线图', customer_id=c1.id, source='draw', file_type='other')
        db.session.add_all([t1, t2, t3])
        db.session.commit()
        yield {'c1': c1.id, 'c2': c2.id, 'd1': d1.id, 'd2': d2.id,
               'r1': r1.id, 'r2': r2.id, 'i1': i1.id, 'i2': i2.id,
               't1': t1.id, 't3': t3.id}


# ==================== 机柜 ====================
class TestRackList:
    def test_list_shape_with_aggregation(self, op_client, seed):
        r = op_client.get('/api/v2/rack/cabinets')
        assert r.status_code == 200
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        assert data['total'] == 2
        item = next(x for x in data['items'] if x['id'] == seed['r1'])
        assert item['customer_name'] == '机柜API客户A'
        assert item['used_u'] == 3
        assert item['used_label'] == '3/42'
        assert item['used_pct'] == 7.1
        assert item['used_w'] == 400
        assert item['install_count'] == 2
        assert item['pdu_total_w'] == 8000
        assert item['usage_level'] in ('低', '中', '高', '已满')

    def test_filter_by_customer(self, op_client, seed):
        r = op_client.get('/api/v2/rack/cabinets', query_string={'customer_id': seed['c2']})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['name'] == 'B-02'

    def test_search(self, op_client, seed):
        r = op_client.get('/api/v2/rack/cabinets', query_string={'search': 'A-01'})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['customer_name'] == '机柜API客户A'

    def test_pagination(self, op_client, seed):
        r = op_client.get('/api/v2/rack/cabinets', query_string={'page': 1, 'page_size': 1})
        data = r.get_json()['data']
        assert data['total'] == 2
        assert len(data['items']) == 1

    def test_requires_permission(self, sales_client, seed):
        r = sales_client.get('/api/v2/rack/cabinets')
        assert r.status_code == 403

    def test_requires_login(self, client, seed):
        assert client.get('/api/v2/rack/cabinets').status_code == 401


class TestRackCrud:
    def test_create(self, op_client, seed, app):
        r = op_client.post('/api/v2/rack/cabinets', json={
            'name': 'C-03', 'customer_id': seed['c2'], 'total_u': 48,
            'pdu_total_w': 6000, 'color': '#ff0000', 'remark': '新柜',
        })
        assert r.status_code == 200
        assert r.get_json()['code'] == 0
        with app.app_context():
            rack = Rack.query.filter_by(name='C-03').first()
            assert rack is not None
            assert rack.customer_id == seed['c2']
            assert rack.total_u == 48
            assert rack.pdu_total_w == 6000
            assert rack.color == '#ff0000'

    def test_create_missing_name(self, op_client, seed):
        r = op_client.post('/api/v2/rack/cabinets',
                           json={'customer_id': seed['c1'], 'total_u': 42})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1
        assert '名称' in r.get_json()['message']

    def test_create_missing_customer(self, op_client, seed):
        r = op_client.post('/api/v2/rack/cabinets', json={'name': 'X', 'total_u': 42})
        assert r.status_code == 400
        assert '客户' in r.get_json()['message']

    def test_create_invalid_total_u(self, op_client, seed):
        r = op_client.post('/api/v2/rack/cabinets', json={
            'name': 'X', 'customer_id': seed['c1'], 'total_u': 'abc'})
        assert r.status_code == 400

    def test_update(self, op_client, seed, app):
        r = op_client.put(f"/api/v2/rack/cabinets/{seed['r1']}", json={
            'name': 'A-01-改', 'total_u': 48, 'pdu_total_w': 9000, 'remark': 'x'})
        assert r.status_code == 200
        with app.app_context():
            rack = Rack.query.get(seed['r1'])
            assert rack.name == 'A-01-改'
            assert rack.total_u == 48
            assert rack.pdu_total_w == 9000

    def test_update_blank_name(self, op_client, seed):
        r = op_client.put(f"/api/v2/rack/cabinets/{seed['r1']}", json={'name': '  '})
        assert r.status_code == 400

    def test_delete_cascades_installs(self, admin_client, seed, app):
        r = admin_client.delete(f"/api/v2/rack/cabinets/{seed['r1']}")
        assert r.status_code == 200
        with app.app_context():
            assert Rack.query.get(seed['r1']) is None
            assert RackInstall.query.filter_by(rack_id=seed['r1']).count() == 0

    def test_delete_forbidden_for_viewer(self, viewer_client, seed):
        r = viewer_client.delete(f"/api/v2/rack/cabinets/{seed['r1']}")
        assert r.status_code == 403


class TestRackInstall:
    def test_create_managed(self, op_client, seed, app):
        r = op_client.post('/api/v2/rack/installs', json={
            'rack_id': seed['r1'], 'device_id': seed['d2'], 'start_u': 20,
            'occupy_u': 2, 'rated_w': 200})
        assert r.status_code == 200
        assert r.get_json()['data']['id']
        with app.app_context():
            inst = RackInstall.query.get(r.get_json()['data']['id'])
            assert inst.device_id == seed['d2']
            assert inst.start_u == 20

    def test_create_manual(self, op_client, seed, app):
        r = op_client.post('/api/v2/rack/installs', json={
            'rack_id': seed['r1'], 'manual_name': '手动设备', 'manual_brand': 'IBM',
            'manual_model': 'X3650', 'start_u': 30, 'occupy_u': 3, 'rated_w': 500})
        assert r.status_code == 200
        with app.app_context():
            inst = RackInstall.query.get(r.get_json()['data']['id'])
            assert inst.manual_name == '手动设备'
            assert inst.device_id is None

    def test_create_requires_device_or_manual(self, op_client, seed):
        r = op_client.post('/api/v2/rack/installs',
                           json={'rack_id': seed['r1'], 'start_u': 5, 'occupy_u': 1})
        assert r.status_code == 400

    def test_create_out_of_range(self, op_client, seed):
        r = op_client.post('/api/v2/rack/installs', json={
            'rack_id': seed['r1'], 'manual_name': 'x', 'start_u': 50, 'occupy_u': 1})
        assert r.status_code == 400
        assert '超出范围' in r.get_json()['message']

    def test_create_u_conflict(self, op_client, seed):
        r = op_client.post('/api/v2/rack/installs', json={
            'rack_id': seed['r1'], 'manual_name': 'x', 'start_u': 1, 'occupy_u': 2})
        assert r.status_code == 400
        assert '冲突' in r.get_json()['message']

    def test_update_move(self, op_client, seed, app):
        r = op_client.put(f"/api/v2/rack/installs/{seed['i1']}", json={
            'start_u': 5, 'occupy_u': 1, 'rated_w': 400})
        assert r.status_code == 200
        with app.app_context():
            inst = RackInstall.query.get(seed['i1'])
            assert inst.start_u == 5
            assert inst.occupy_u == 1
            assert inst.rated_w == 400

    def test_update_conflict_excludes_self(self, op_client, seed):
        """移动到原位置重叠区间：排除自身后不冲突"""
        r = op_client.put(f"/api/v2/rack/installs/{seed['i1']}", json={
            'start_u': 2, 'occupy_u': 2})
        assert r.status_code == 200

    def test_update_conflict_with_other(self, op_client, seed):
        r = op_client.put(f"/api/v2/rack/installs/{seed['i1']}", json={
            'start_u': 10, 'occupy_u': 1})
        assert r.status_code == 400
        assert '冲突' in r.get_json()['message']

    def test_delete(self, admin_client, seed, app):
        r = admin_client.delete(f"/api/v2/rack/installs/{seed['i2']}")
        assert r.status_code == 200
        with app.app_context():
            assert RackInstall.query.get(seed['i2']) is None

    def test_delete_forbidden_for_viewer(self, viewer_client, seed):
        r = viewer_client.delete(f"/api/v2/rack/installs/{seed['i2']}")
        assert r.status_code == 403


class TestRackDevices:
    def test_devices_by_rack(self, op_client, seed):
        r = op_client.get('/api/v2/rack/devices', query_string={'rack_id': seed['r1']})
        assert r.status_code == 200
        items = r.get_json()['data']['items']
        # 仅本客户设备
        assert len(items) == 1
        assert items[0]['name'] == 'SW-A'
        assert items[0]['installed'] is True

    def test_devices_by_customer(self, op_client, seed):
        r = op_client.get('/api/v2/rack/devices', query_string={'customer_id': seed['c2']})
        items = r.get_json()['data']['items']
        assert len(items) == 1
        assert items[0]['name'] == 'FW-B'
        assert items[0]['installed'] is False

    def test_no_customer_returns_empty(self, op_client, seed):
        r = op_client.get('/api/v2/rack/devices')
        assert r.get_json()['data']['items'] == []


class TestRackDicts:
    def test_customers(self, admin_client, seed):
        """机柜客户下拉（admin 全量；工程师仅关联客户）"""
        r = admin_client.get('/api/dicts/rack')
        assert r.status_code == 200
        data = r.get_json()['data']
        names = [c['name'] for c in data['customers']]
        assert '机柜API客户A' in names
        assert '机柜API客户B' in names


class TestRackTree:
    def test_group_by_city_customer(self, op_client, seed):
        r = op_client.get('/api/v2/rack/tree')
        assert r.status_code == 200
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        # 客户均未配置地区 → 全部归入「未分配地市」
        assert len(data) == 1
        city = data[0]
        assert city['city'] == '未分配地市'
        by_id = {c['id']: c for c in city['customers']}
        assert set(by_id) == {seed['c1'], seed['c2']}
        a01 = next(r for r in by_id[seed['c1']]['racks'] if r['name'] == 'A-01')
        assert a01['total_u'] == 42
        assert a01['color'] == '#0d6efd'
        assert a01['install_count'] == 2
        b02 = next(r for r in by_id[seed['c2']]['racks'] if r['name'] == 'B-02')
        assert b02['install_count'] == 0

    def test_requires_permission(self, sales_client, seed):
        assert sales_client.get('/api/v2/rack/tree').status_code == 403

    def test_requires_login(self, client, seed):
        assert client.get('/api/v2/rack/tree').status_code == 401


# ==================== 拓扑 ====================
class TestTopologyList:
    def test_grouped_list(self, op_client, seed):
        r = op_client.get('/api/topologies')
        assert r.status_code == 200
        body = r.get_json()
        assert body['code'] == 0
        data = body['data']
        # 同 客户+名称 的 image/pdf 合并为一行
        assert data['total'] == 2
        item = next(x for x in data['items'] if x['name'] == '核心网络')
        assert item['customer_name'] == '机柜API客户A'
        assert item['file_count'] == 2
        assert item['type'] == 'image'
        assert set(item['types']) == {'image', 'pdf'}
        assert item['source'] == 'upload'
        assert 'updated_at' in item

    def test_list_files_detail(self, op_client, seed):
        """列表行 files 明细与详情接口逐项一致（前端图标矩阵依赖）"""
        r = op_client.get('/api/topologies')
        item = next(x for x in r.get_json()['data']['items'] if x['name'] == '核心网络')
        assert len(item['files']) == 2
        types = [f['file_type'] for f in item['files']]
        assert types == ['image', 'pdf']
        for f in item['files']:
            assert set(f) == {'id', 'file_type', 'source', 'file_path', 'url',
                              'thumbnail', 'pdf', 'vsdx', 'svg', 'upload_by',
                              'created_at'}
        detail = op_client.get(f"/api/topologies/{seed['t1']}").get_json()['data']
        assert detail['files'] == item['files']

    def test_search(self, op_client, seed):
        r = op_client.get('/api/topologies', query_string={'search': '在线'})
        data = r.get_json()['data']
        assert data['total'] == 1
        assert data['items'][0]['name'] == '新建在线图'

    def test_pagination(self, op_client, seed):
        r = op_client.get('/api/topologies', query_string={'page': 1, 'page_size': 1})
        data = r.get_json()['data']
        assert data['total'] == 2
        assert len(data['items']) == 1

    def test_requires_permission(self, sales_client, seed):
        r = sales_client.get('/api/topologies')
        assert r.status_code == 403

    def test_requires_login(self, client, seed):
        assert client.get('/api/topologies').status_code == 401


class TestTopologyDetail:
    def test_detail_upload_group(self, op_client, seed):
        r = op_client.get(f"/api/topologies/{seed['t1']}")
        assert r.status_code == 200
        data = r.get_json()['data']
        assert data['name'] == '核心网络'
        assert data['customer_name'] == '机柜API客户A'
        assert data['file_count'] == 2
        assert len(data['files']) == 2
        types = [f['file_type'] for f in data['files']]
        assert types == ['image', 'pdf']
        assert data['files'][0]['upload_by'] == 'admin'
        assert 'url' in data['files'][0]
        assert data['has_editor'] is False

    def test_detail_draw_has_editor(self, op_client, seed):
        r = op_client.get(f"/api/topologies/{seed['t3']}")
        data = r.get_json()['data']
        assert data['source'] == 'draw'
        assert data['has_editor'] is True
        assert data['editor_id'] == seed['t3']

    def test_404(self, op_client, seed):
        assert op_client.get('/api/topologies/99999').status_code == 404


class TestTopologyCrud:
    def test_create_draw(self, admin_client, seed, app):
        r = admin_client.post('/api/topologies', json={
            'name': '新建在线图2', 'customer_id': seed['c2'], 'source': 'draw'})
        assert r.status_code == 200
        assert r.get_json()['code'] == 0
        with app.app_context():
            t = Topology.query.get(r.get_json()['data']['id'])
            assert t.name == '新建在线图2'
            assert t.source == 'draw'
            assert t.customer_id == seed['c2']

    def test_create_missing_name(self, admin_client, seed):
        r = admin_client.post('/api/topologies', json={'customer_id': seed['c1']})
        assert r.status_code == 400

    def test_update(self, admin_client, seed, app):
        r = admin_client.put(f"/api/topologies/{seed['t1']}", json={
            'name': '核心网络V2', 'description': '改', 'customer_id': seed['c2']})
        assert r.status_code == 200
        with app.app_context():
            t = Topology.query.get(seed['t1'])
            assert t.name == '核心网络V2'
            assert t.description == '改'
            assert t.customer_id == seed['c2']

    def test_delete(self, admin_client, seed, app):
        r = admin_client.delete(f"/api/topologies/{seed['t3']}")
        assert r.status_code == 200
        with app.app_context():
            assert Topology.query.get(seed['t3']) is None

    def test_permissions(self, viewer_client, op_client, seed):
        # viewer 有 topology:view 可查看，但无 topology:add
        assert op_client.get('/api/topologies').status_code == 200
        r = viewer_client.post('/api/topologies', json={'name': 'x'})
        assert r.status_code == 403
        # operator 无 topology:delete
        r = op_client.delete(f"/api/topologies/{seed['t3']}")
        assert r.status_code == 403


class TestTopologyDicts:
    def test_customers_and_regions(self, admin_client, seed):
        r = admin_client.get('/api/topologies/dicts')
        assert r.status_code == 200
        data = r.get_json()['data']
        names = [c['name'] for c in data['customers']]
        assert '机柜API客户A' in names
        assert isinstance(data['regions'], list)

    def test_requires_permission(self, sales_client, seed):
        assert sales_client.get('/api/topologies/dicts').status_code == 403


class TestTopologyTemplates:
    def test_chinese_logical_and_physical_templates(self, admin_client, app):
        response = admin_client.get('/api/topologies/templates')
        assert response.status_code == 200
        body = response.get_json()
        assert body['ok'] is True
        assert body['code'] == 0
        assert body['data']['items'] == body['items']
        assert [item['name'] for item in body['items'][:2]] == [
            '网络逻辑拓扑图', '网络物理连接拓扑图']
        by_name = {item['name']: item for item in body['data']['items']}
        assert {'网络逻辑拓扑图', '网络物理连接拓扑图'} <= set(by_name)
        assert by_name['网络逻辑拓扑图']['category'] == 'logical'
        assert by_name['网络物理连接拓扑图']['category'] == 'physical'

        template_dir = os.path.join(app.root_path, 'static', 'templates')
        with open(os.path.join(template_dir, by_name['网络逻辑拓扑图']['file']),
                  encoding='utf-8') as source:
            logical_xml = source.read()
        assert all(label in logical_xml for label in ('外网边界', '上联边界', '接入层', '下联边界'))
        assert 'id="access-a"' in logical_xml and 'parent="zone-access"' in logical_xml
        assert 'id="branch"' in logical_xml and 'parent="zone-downlink"' in logical_xml

        with open(os.path.join(template_dir, by_name['网络物理连接拓扑图']['file']),
                  encoding='utf-8') as source:
            physical_xml = source.read()
        assert all(label in physical_xml for label in ('网络物理连接拓扑图', '机柜', '端口'))

    def test_template_list_requires_login(self, client):
        assert client.get('/api/topologies/templates').status_code == 401


class TestTopologyUpload:
    def _remove_uploaded(self, app, tid):
        with app.app_context():
            t = Topology.query.get(tid)
            assert t is not None
            full = os.path.join(app.root_path, 'static', t.file_path)
            if os.path.exists(full):
                os.remove(full)
            return t

    def test_upload_image_auto_name(self, admin_client, seed, app):
        r = admin_client.post('/api/topologies/upload',
                              data={'topo_file': (io.BytesIO(b'pngdata'), 'net.png'),
                                    'topo_type': '网络拓扑图',
                                    'customer_id': str(seed['c1'])},
                              content_type='multipart/form-data')
        assert r.status_code == 200
        body = r.get_json()
        assert body['code'] == 0
        t = self._remove_uploaded(app, body['data']['id'])
        assert t.file_type == 'image'
        assert t.customer_id == seed['c1']
        assert t.file_path.startswith('uploads/topologies/')
        assert t.file_path.endswith('.png')
        # 自动命名：客户名 + 类型 + 日期
        from datetime import date
        assert t.name == f"机柜API客户A网络拓扑图{date.today().strftime('%Y%m%d')}"

    def test_upload_drawio_type(self, admin_client, seed, app):
        r = admin_client.post('/api/topologies/upload',
                              data={'topo_file': (io.BytesIO(b'<mxfile/>'), 'topo.drawio')},
                              content_type='multipart/form-data')
        assert r.status_code == 200
        t = self._remove_uploaded(app, r.get_json()['data']['id'])
        assert t.file_type == 'drawio'

    def test_upload_custom_name_pdf(self, admin_client, seed, app):
        r = admin_client.post('/api/topologies/upload',
                              data={'topo_file': (io.BytesIO(b'%PDF'), 'a.pdf'),
                                    'name': '自定义名', 'description': '备注'},
                              content_type='multipart/form-data')
        assert r.status_code == 200
        t = self._remove_uploaded(app, r.get_json()['data']['id'])
        assert t.name == '自定义名'
        assert t.description == '备注'
        assert t.file_type == 'pdf'

    def test_upload_missing_file(self, admin_client, seed):
        r = admin_client.post('/api/topologies/upload', data={'topo_type': '网络拓扑图'})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1
        assert '文件' in r.get_json()['message']

    def test_upload_rejects_unknown_extension_without_writing(self, admin_client, seed, app):
        upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'topologies')
        before = set(os.listdir(upload_dir)) if os.path.isdir(upload_dir) else set()
        r = admin_client.post('/api/topologies/upload',
                              data={'topo_file': (io.BytesIO(b'<script>x</script>'), 'evil.html')},
                              content_type='multipart/form-data')
        after = set(os.listdir(upload_dir)) if os.path.isdir(upload_dir) else set()
        assert r.status_code == 400
        assert r.get_json()['code'] == 1
        assert before == after

    def test_upload_requires_permission(self, viewer_client, seed):
        r = viewer_client.post('/api/topologies/upload',
                               data={'topo_file': (io.BytesIO(b'x'), 'a.png')},
                               content_type='multipart/form-data')
        assert r.status_code == 403


# ==================== 网络工具 ====================
class TestIpCalc:
    def test_dotted_mask(self, op_client):
        r = op_client.post('/api/tools/ip-calc', json={
            'ip': '192.168.1.10', 'mask': '255.255.255.0'})
        assert r.status_code == 200
        d = r.get_json()['data']
        assert d['network'] == '192.168.1.0'
        assert d['broadcast'] == '192.168.1.255'
        assert d['first'] == '192.168.1.1'
        assert d['last'] == '192.168.1.254'
        assert d['hosts'] == 254
        assert d['mask'] == '255.255.255.0'
        assert d['mask_bits'] == 24
        assert d['cidr'] == '192.168.1.0/24'

    def test_prefix_mask(self, op_client):
        r = op_client.post('/api/tools/ip-calc', json={'ip': '10.1.2.3', 'mask': 16})
        d = r.get_json()['data']
        assert d['network'] == '10.1.0.0'
        assert d['broadcast'] == '10.1.255.255'
        assert d['hosts'] == 65534

    def test_cidr_input(self, op_client):
        r = op_client.post('/api/tools/ip-calc', json={'cidr': '10.0.0.0/8'})
        d = r.get_json()['data']
        assert d['network'] == '10.0.0.0'
        assert d['broadcast'] == '10.255.255.255'
        assert d['hosts'] == 16777214

    def test_31_network(self, op_client):
        r = op_client.post('/api/tools/ip-calc', json={'ip': '1.2.3.4', 'mask': '31'})
        d = r.get_json()['data']
        assert d['hosts'] == 2
        assert d['first'] == '1.2.3.4'
        assert d['last'] == '1.2.3.5'

    def test_invalid_ip(self, op_client):
        r = op_client.post('/api/tools/ip-calc', json={'ip': '999.1.1.1', 'mask': 24})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1

    def test_invalid_mask(self, op_client):
        r = op_client.post('/api/tools/ip-calc', json={'ip': '10.0.0.1', 'mask': '255.0.255.0'})
        assert r.status_code == 400
        r = op_client.post('/api/tools/ip-calc', json={'ip': '10.0.0.1', 'mask': 33})
        assert r.status_code == 400

    def test_missing_input(self, op_client):
        r = op_client.post('/api/tools/ip-calc', json={'ip': '10.0.0.1'})
        assert r.status_code == 400
        r = op_client.post('/api/tools/ip-calc', json={'mask': 24})
        assert r.status_code == 400

    def test_login_only_no_permission_code(self, sales_client):
        """网络工具仅需登录，sales 无工具权限码也可用"""
        r = sales_client.post('/api/tools/ip-calc', json={'ip': '10.0.0.1', 'mask': 24})
        assert r.status_code == 200
        assert r.get_json()['code'] == 0

    def test_requires_login(self, client):
        r = client.post('/api/tools/ip-calc', json={'ip': '10.0.0.1', 'mask': 24})
        assert r.status_code == 401


class TestConvert:
    def test_hex_to_decimal(self, op_client):
        r = op_client.post('/api/tools/convert', json={'value': 'FF', 'from_base': 16, 'to_base': 10})
        assert r.status_code == 200
        d = r.get_json()['data']
        assert d['result'] == '255'
        assert d['binary'] == '11111111'
        assert d['hex'] == 'FF'

    def test_bin_to_octal(self, op_client):
        r = op_client.post('/api/tools/convert', json={'value': '1010', 'from_base': 2, 'to_base': 8})
        d = r.get_json()['data']
        assert d['result'] == '12'

    def test_invalid_digit(self, op_client):
        r = op_client.post('/api/tools/convert', json={'value': 'FF', 'from_base': 2, 'to_base': 10})
        assert r.status_code == 400

    def test_unsupported_base(self, op_client):
        r = op_client.post('/api/tools/convert', json={'value': '10', 'from_base': 3, 'to_base': 10})
        assert r.status_code == 400

    def test_empty_value(self, op_client):
        r = op_client.post('/api/tools/convert', json={'value': '', 'from_base': 10, 'to_base': 16})
        assert r.status_code == 400


class TestMacFormat:
    def test_dash_input(self, op_client):
        r = op_client.post('/api/tools/mac-format', json={'mac': 'AA-BB-CC-DD-EE-FF'})
        assert r.status_code == 200
        d = r.get_json()['data']
        assert d['result'] == 'AA:BB:CC:DD:EE:FF'
        assert d['plain'] == 'AABBCCDDEEFF'
        assert d['colon'] == 'AA:BB:CC:DD:EE:FF'
        assert d['dash'] == 'AA-BB-CC-DD-EE-FF'
        assert d['dot'] == 'AABB.CCDD.EEFF'

    def test_lowercase_and_dot_input(self, op_client):
        r = op_client.post('/api/tools/mac-format', json={'mac': 'aabb.ccdd.eeff'})
        d = r.get_json()['data']
        assert d['result'] == 'AA:BB:CC:DD:EE:FF'

    def test_invalid_length(self, op_client):
        r = op_client.post('/api/tools/mac-format', json={'mac': 'AA:BB:CC'})
        assert r.status_code == 400

    def test_invalid_char(self, op_client):
        r = op_client.post('/api/tools/mac-format', json={'mac': 'GG:BB:CC:DD:EE:FF'})
        assert r.status_code == 400

    def test_empty(self, op_client):
        r = op_client.post('/api/tools/mac-format', json={'mac': ''})
        assert r.status_code == 400
