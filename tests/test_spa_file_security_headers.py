"""Exercise real SPA send_from_directory responses without a database."""
import io

import pytest
from flask import Flask, send_file
from flask_login import LoginManager, UserMixin

from config import setup_security_headers
from utils.file_access_security import register_file_access_security


@pytest.mark.parametrize('authenticated', [False, True])
def test_application_resources_keep_site_csp(tmp_path, monkeypatch, authenticated):
    from blueprints import vue_api

    dist = tmp_path / 'app'
    (dist / 'assets').mkdir(parents=True)
    for name, content in [('index.html', '<html>SPA</html>'),
                          ('favicon.svg', '<svg/>'),
                          ('assets/test.js', 'window.loaded = true;'),
                          ('assets/test.css', 'body { color: black; }')]:
        (dist / name).write_text(content)
    monkeypatch.setattr(vue_api, '_APP_DIST', str(dist))
    monkeypatch.setattr('utils.file_access_security.is_internal_request', lambda: False)
    app = Flask(__name__, static_folder=str(tmp_path), static_url_path='/static')
    app.config.update(TESTING=True, SECRET_KEY='test', CSP_ENABLED=True)
    login = LoginManager(app)

    @login.request_loader
    def load_user(request):
        return UserMixin() if authenticated else None

    setup_security_headers(app)
    register_file_access_security(app)
    app.add_url_rule('/app/', 'vue_api.vue_spa', vue_api.vue_spa, defaults={'path': ''})
    app.add_url_rule('/app/<path:path>', 'vue_api.vue_spa', vue_api.vue_spa)

    @app.get('/document')
    def document():
        return send_file(io.BytesIO(b'%PDF-1.4\n%%EOF'), mimetype='application/pdf',
                         download_name='report.pdf')

    client = app.test_client()
    for path in ['/app/', '/app/login', '/app/devices', '/app/favicon.svg',
                 '/app/assets/test.js', '/app/assets/test.css', '/static/app/index.html']:
        for method in ('GET', 'HEAD'):
            with client.open(path, method=method) as response:
                assert response.status_code == 200, path
                assert 'Content-Disposition' in response.headers
                csp = response.headers['Content-Security-Policy']
                assert "script-src 'self'" in csp
                assert 'sandbox' not in csp
                assert "default-src 'none'" not in csp
    with client.get('/document') as response:
        assert response.headers['Content-Security-Policy'] == "sandbox; default-src 'none'"
        assert 'no-store' in response.headers['Cache-Control']
    # Anonymous uploaded files must not inherit the public static exemption.
    if not authenticated:
        for path in ['/static/uploads/configs/secret.cfg',
                     '/static/vendor/../uploads/configs/secret.cfg']:
            with client.get(path) as response:
                assert response.status_code == 404
