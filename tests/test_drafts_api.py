# -*- coding: utf-8 -*-
"""W0-S5 草稿 related_id 类型统一验证"""
import json

from models import FormDraft


class TestDraftLifecycle:
    def test_save_load_delete(self, op_client, app):
        r = op_client.post('/api/drafts/save', json={
            'form_type': 'inspection', 'related_id': 7,
            'form_data_json': {'title': 'Q2巡检草稿'}})
        assert r.get_json()['success'] is True

        r = op_client.get('/api/drafts/load?form_type=inspection&related_id=7')
        body = r.get_json()
        assert body['success'] is True
        assert json.loads(body['form_data_json'])['title'] == 'Q2巡检草稿'

        r = op_client.post('/api/drafts/delete',
                           json={'form_type': 'inspection', 'related_id': 7})
        assert r.get_json()['success'] is True
        r = op_client.get('/api/drafts/load?form_type=inspection&related_id=7')
        assert r.get_json()['form_data_json'] == '{}'

    def test_string_related_id_normalized_to_int(self, op_client, app):
        """前端传字符串 '7'：save 归一化为 int 入库，load 用 int 也能命中"""
        op_client.post('/api/drafts/save', json={
            'form_type': 'ticket', 'related_id': '7',
            'form_data_json': {'x': 1}})
        with app.app_context():
            draft = FormDraft.query.filter_by(form_type='ticket').first()
            assert draft.related_id == 7
            assert isinstance(draft.related_id, int)

        r = op_client.get('/api/drafts/load?form_type=ticket&related_id=7')
        assert json.loads(r.get_json()['form_data_json']) == {'x': 1}

    def test_empty_related_id_becomes_none(self, op_client):
        op_client.post('/api/drafts/save', json={
            'form_type': 'fault', 'related_id': '', 'form_data_json': {}})
        r = op_client.get('/api/drafts/load?form_type=fault')
        assert r.get_json()['success'] is True

    def test_draft_isolated_per_user(self, op_client, viewer_client):
        op_client.post('/api/drafts/save', json={
            'form_type': 'ticket', 'related_id': 1, 'form_data_json': {'mine': True}})
        r = viewer_client.get('/api/drafts/load?form_type=ticket&related_id=1')
        assert r.get_json()['form_data_json'] == '{}'  # viewer 看不到 op 的草稿

    def test_save_requires_login(self, client):
        assert client.post('/api/drafts/save', json={'form_type': 'x'}).status_code == 401
