def test_spa_entry_is_served_directly_without_version_redirect(client, tmp_path, monkeypatch):
    import blueprints.vue_api as vue_api_module

    dist = tmp_path / 'dist'
    assets = dist / 'assets'
    assets.mkdir(parents=True)
    index = b'<!doctype html><script src="/app/assets/index-current.js"></script>'
    (dist / 'index.html').write_bytes(index)
    (assets / 'index-current.js').write_text('console.log("current")', encoding='utf-8')
    monkeypatch.setattr(vue_api_module, '_APP_DIST', str(dist))

    response = client.get('/app/login')
    assert response.status_code == 200
    assert response.data == index
    assert response.headers['Cache-Control'] == 'no-store, no-cache, must-revalidate'

    with_query = client.get('/app/login?redirect=/tickets')
    assert with_query.status_code == 200
    assert with_query.data == index
    assert 'Location' not in with_query.headers
    asset = client.get('/app/assets/index-current.js')
    assert asset.status_code == 200
    assert asset.data == b'console.log("current")'
