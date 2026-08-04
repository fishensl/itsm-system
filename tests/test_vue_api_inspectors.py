# -*- coding: utf-8 -*-
"""Vue API：巡检人员（列表/候选/增改删）"""
from models import db, User, Inspector


def _mk_user(username, role='operator', realname=''):
    u = User.create_with_password(username=username, password='test-pw-123',
                                  role=role, realname=realname)
    db.session.add(u)
    db.session.flush()
    return u


class TestInspectorApi:
    def test_list_shape(self, admin_client, app):
        with app.app_context():
            op = _mk_user('inspop1', 'operator', '巡检员甲')
            _mk_user('inspop2', 'operator', '巡检员乙')
            _mk_user('admin2', 'admin', '管理员乙')
            db.session.add(Inspector(user_id=op.id, remark='备注'))
            db.session.commit()
        r = admin_client.get('/api/inspectors')
        assert r.status_code == 200
        body = r.get_json()
        assert body['code'] == 0
        d = body['data']
        assert len(d['inspectors']) == 1
        assert d['inspectors'][0]['name'] == '巡检员甲'
        assert d['inspectors'][0]['remark'] == '备注'
        # 候选：另一 operator 可用；admin 也在候选内（角色 admin 可勾选）
        names = {u['name'] for u in d['available_users']}
        assert '巡检员乙' in names
        assert '管理员乙' in names
        # 已关联的不在候选
        assert '巡检员甲' not in names

    def test_add_duplicate_rejected(self, admin_client, app):
        with app.app_context():
            op = _mk_user('dupuser')
            db.session.add(Inspector(user_id=op.id))
            db.session.commit()
            uid = op.id
        r = admin_client.post('/api/inspectors', json={'user_id': uid})
        assert r.status_code == 400
        assert r.get_json()['code'] == 1

    def test_add_and_update_and_delete(self, admin_client, app):
        with app.app_context():
            op = _mk_user('flowuser')
            db.session.commit()
            uid = op.id
        r = admin_client.post('/api/inspectors', json={'user_id': uid, 'remark': 'r1'})
        assert r.get_json()['code'] == 0
        with app.app_context():
            i = Inspector.query.filter_by(user_id=uid).first()
            iid = i.id
        r = admin_client.put(f'/api/inspectors/{iid}', json={'is_active': False, 'remark': 'r2'})
        assert r.get_json()['code'] == 0
        with app.app_context():
            i = db.session.get(Inspector, iid)
            assert i.is_active is False
            assert i.remark == 'r2'
        r = admin_client.delete(f'/api/inspectors/{iid}')
        assert r.get_json()['code'] == 0
        with app.app_context():
            assert db.session.get(Inspector, iid) is None

    def test_permissions(self, viewer_client, op_client):
        assert viewer_client.get('/api/inspectors').status_code == 200  # view 权限
        assert viewer_client.post('/api/inspectors', json={'user_id': 1}).status_code == 403
        assert op_client.delete('/api/inspectors/1').status_code == 403  # 需 delete 权限

    def test_add_requires_user(self, admin_client):
        r = admin_client.post('/api/inspectors', json={'user_id': None})
        assert r.status_code == 400
        r = admin_client.post('/api/inspectors', json={'user_id': 999999})
        assert r.status_code == 400
