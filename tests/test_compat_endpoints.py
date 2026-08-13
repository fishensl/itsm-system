from utils.compat import mark_deprecated


def test_mark_deprecated_adds_machine_readable_headers(app):
    with app.test_request_context('/legacy', method='GET'):
        response = mark_deprecated({'ok': True}, '/api/v2/replacement')

    assert response.headers['Deprecation'] == 'true'
    assert response.headers['Link'] == '</api/v2/replacement>; rel="successor-version"'


def test_legacy_rack_api_advertises_v2_successor(viewer_client):
    response = viewer_client.get('/api/rack/cabinets')

    assert response.status_code == 200
    assert response.headers['Deprecation'] == 'true'
    assert response.headers['Link'] == '</api/v2/rack/cabinets>; rel="successor-version"'


def test_task_dispatch_redirect_advertises_spa_successor(viewer_client):
    response = viewer_client.get('/task-dispatch/', follow_redirects=False)

    assert response.status_code == 301
    assert response.headers['Deprecation'] == 'true'
    assert response.headers['Link'] == '</app/task-schedule>; rel="successor-version"'


def test_legacy_device_history_advertises_v2_successor(app, admin_client):
    from models import Device, db

    with app.app_context():
        device = Device(device_name='兼容端点测试设备')
        db.session.add(device)
        db.session.commit()
        device_id = device.id

    response = admin_client.get(f'/api/devices/{device_id}/password-history')

    assert response.status_code == 200
    assert response.headers['Deprecation'] == 'true'
    assert response.headers['Link'] == (
        f'</api/v2/devices/{device_id}/password-history>; rel="successor-version"'
    )
