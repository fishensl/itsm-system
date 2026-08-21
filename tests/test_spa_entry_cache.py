import hashlib
from urllib.parse import parse_qs, urlparse


def test_spa_entry_redirects_to_content_version(client, tmp_path, monkeypatch):
    import blueprints.vue_api as vue_api_module

    dist = tmp_path / 'dist'
    assets = dist / 'assets'
    assets.mkdir(parents=True)
    index = b'<!doctype html><script src="/app/assets/index-current.js"></script>'
    (dist / 'index.html').write_bytes(index)
    (assets / 'index-current.js').write_text('console.log("current")', encoding='utf-8')
    monkeypatch.setattr(vue_api_module, '_APP_DIST', str(dist))

    response = client.get('/app/login?redirect=/tickets')
    assert response.status_code == 302
    location = response.headers['Location']
    parsed = urlparse(location)
    assert parsed.path == '/app/login'
    query = parse_qs(parsed.query)
    assert query['redirect'] == ['/tickets']
    assert query['v'] == [hashlib.sha256(index).hexdigest()[:12]]

    current = client.get(location)
    assert current.status_code == 200
    assert current.data == index
    asset = client.get('/app/assets/index-current.js')
    assert asset.status_code == 200
    assert asset.data == b'console.log("current")'
