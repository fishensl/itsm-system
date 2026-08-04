# -*- coding: utf-8 -*-
"""Vue API：AI 对接（CRUD / Key 加密 / 测试）"""
from models import db, AIConfig
from utils.crypto import encrypt_password, decrypt_password


class TestAiConfigApi:
    def test_crud_and_key_encrypted(self, admin_client, app):
        r = admin_client.post('/api/ai-config', json={
            'provider': 'OpenAI', 'api_endpoint': '', 'model_name': 'gpt-4',
            'api_key': 'sk-test-123', 'max_tokens': 2048, 'temperature': 0.7,
            'is_enabled': True,
        })
        assert r.get_json()['code'] == 0
        cid = r.get_json()['data']['id']
        r = admin_client.get('/api/ai-config')
        items = r.get_json()['data']
        assert len(items) == 1
        assert items[0]['has_api_key'] is True
        with app.app_context():
            cfg = db.session.get(AIConfig, cid)
            assert cfg.api_key_encrypted != 'sk-test-123'  # 加密入库
            assert decrypt_password(cfg.api_key_encrypted) == 'sk-test-123'
        # 更新（不传 key 不覆盖）
        r = admin_client.put(f'/api/ai-config/{cid}', json={'model_name': 'gpt-4o', 'is_enabled': False})
        assert r.get_json()['code'] == 0
        with app.app_context():
            cfg = db.session.get(AIConfig, cid)
            assert cfg.model_name == 'gpt-4o'
            assert decrypt_password(cfg.api_key_encrypted) == 'sk-test-123'
        # 传新 key 覆盖
        r = admin_client.put(f'/api/ai-config/{cid}', json={'api_key': 'sk-new'})
        with app.app_context():
            assert decrypt_password(db.session.get(AIConfig, cid).api_key_encrypted) == 'sk-new'
        r = admin_client.delete(f'/api/ai-config/{cid}')
        assert r.get_json()['code'] == 0
        with app.app_context():
            assert db.session.get(AIConfig, cid) is None

    def test_test_endpoint(self, admin_client, app, monkeypatch):
        with app.app_context():
            cfg = AIConfig(provider='Ollama', model_name='llama3',
                           api_key_encrypted=encrypt_password('x'))
            db.session.add(cfg)
            db.session.commit()
            cid = cfg.id

        def _fake_test(self):
            return True, 'ok'

        from utils import ai_client
        monkeypatch.setattr(ai_client.AIClient, 'test_connection', _fake_test)
        r = admin_client.post(f'/api/ai-config/{cid}/test')
        assert r.get_json()['data']['success'] is True

    def test_permissions(self, viewer_client, op_client):
        assert viewer_client.get('/api/ai-config').status_code == 403  # 无 ai:view
        assert op_client.get('/api/ai-config').status_code == 403  # operator 也无 ai:view（仅 admin）
        assert viewer_client.post('/api/ai-config', json={}).status_code == 403
