"""Password bootstrap, forced-change, and policy regression tests."""
from models import User, db


STRONG_PASSWORD = 'StrongPassword123!'


def test_user_create_requires_explicit_strong_password(admin_client, app):
    assert admin_client.post('/api/users', json={'username': 'no-password'}).status_code == 400
    assert admin_client.post('/api/users', json={
        'username': 'short-password', 'password': 'Pass1234567',
    }).status_code == 400
    response = admin_client.post('/api/users', json={
        'username': 'temporary-user', 'password': STRONG_PASSWORD,
    })
    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(username='temporary-user').one()
        assert user.must_change_password is True


def test_temporary_password_user_is_restricted_until_change(
        op_client, app, tmp_path, monkeypatch):
    dist = tmp_path / 'app'
    dist.mkdir()
    (dist / 'index.html').write_text('<div id="app"></div>', encoding='utf-8')
    monkeypatch.setattr('blueprints.vue_api._app_dist_dir', lambda: str(dist))
    with app.app_context():
        user = User.query.filter_by(username='op').one()
        user.must_change_password = True
        db.session.commit()

    assert op_client.get('/api/auth/me').status_code == 200
    blocked = op_client.get('/api/tickets')
    assert blocked.status_code == 403
    assert '修改密码' in blocked.get_json()['message']
    # 遗留非 /api 写路由也不能绕过首次改密守卫。
    legacy = op_client.post('/task-schedule/1/status-form', data={'status': '执行中'})
    assert legacy.status_code == 403
    assert '修改密码' in legacy.get_json()['message']
    assert op_client.get('/app/task-schedule').status_code in (200, 302)

    changed = op_client.post('/api/auth/change-password', json={
        'old_password': 'test123456',
        'new_password': STRONG_PASSWORD,
    })
    assert changed.status_code == 200
    with app.app_context():
        user = User.query.filter_by(username='op').one()
        assert user.must_change_password is False
        assert user.check_password(STRONG_PASSWORD)


def test_admin_reset_marks_password_temporary(admin_client, app):
    with app.app_context():
        user_id = User.query.filter_by(username='viewer').one().id
    response = admin_client.put(f'/api/users/{user_id}/password', json={
        'new_password': STRONG_PASSWORD,
    })
    assert response.status_code == 200
    with app.app_context():
        assert User.query.get(user_id).must_change_password is True


def test_init_admin_cli_creates_key_and_one_time_admin(tmp_path, monkeypatch):
    import utils.crypto as crypto
    from app import create_app

    monkeypatch.setattr(crypto, 'KEY_FILE', str(tmp_path / '.secret.key'))
    monkeypatch.setattr(crypto, 'WRAPPED_KEY_FILE', str(tmp_path / '.secret.key.locked'))
    monkeypatch.setattr(crypto, '_memory_key', None)
    application = create_app({
        'TESTING': True,
        'SECRET_KEY': 'bootstrap-test-key',
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'WTF_CSRF_ENABLED': False,
        'RATELIMIT_ENABLED': False,
    })
    with application.app_context():
        db.create_all()
    runner = application.test_cli_runner()
    result = runner.invoke(args=[
        'init-admin', '--username', 'first-admin', '--password', STRONG_PASSWORD,
    ])
    assert result.exit_code == 0, result.output
    assert (tmp_path / '.secret.key').exists()
    with application.app_context():
        user = User.query.filter_by(username='first-admin').one()
        assert user.must_change_password is True
    second = runner.invoke(args=[
        'init-admin', '--username', 'second-admin', '--password', STRONG_PASSWORD,
    ])
    assert second.exit_code != 0
