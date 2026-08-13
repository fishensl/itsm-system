def test_no_duplicate_method_and_rule_contracts(app):
    """同一 method+rule 只能有一个处理器，防止注册顺序遮蔽契约版 API。"""
    routes = {}
    for rule in app.url_map.iter_rules():
        for method in rule.methods - {'HEAD', 'OPTIONS'}:
            routes.setdefault((method, rule.rule), []).append(rule.endpoint)

    duplicates = {key: endpoints for key, endpoints in routes.items() if len(endpoints) > 1}
    assert duplicates == {}
