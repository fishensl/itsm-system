"""Canonical field contract: list/detail/form/export share one registry."""
import re
from pathlib import Path

from domain_metadata import ENTITY_SCHEMAS, get_entity_schema


ROOT = Path(__file__).resolve().parents[1]


def _keys(schema, profile):
    return [item.key for item in schema.profile_fields(profile)]


def test_all_profiles_reference_unique_canonical_fields():
    for schema in ENTITY_SCHEMAS.values():
        canonical = {item.key for item in schema.fields}
        assert len(canonical) == len(schema.fields)
        for profile, keys in schema.profiles.items():
            assert len(keys) == len(set(keys)), f'{schema.key}.{profile} contains duplicates'
            assert set(keys) <= canonical


def test_sensitive_device_password_never_enters_list_or_detail():
    schema = get_entity_schema('device')
    password = schema.field_map['password']
    assert password.sensitive is True
    assert password.permission == 'device:reveal'
    assert 'password' not in _keys(schema, 'list')
    assert 'password' not in _keys(schema, 'detail')
    assert 'password' in _keys(schema, 'form')
    assert 'password' in _keys(schema, 'export_default')


def test_existing_export_codes_are_derived_without_contract_breakage():
    from blueprints.vue_export import (DEVICE_EXPORT_COLUMNS, DEVICE_EXPORT_AVAILABLE_COLUMNS,
                                       TICKET_EXPORT_COLUMNS, TICKET_EXPORT_AVAILABLE_COLUMNS,
                                       FAULT_EXPORT_COLUMNS, INSPECTION_EXPORT_COLUMNS,
                                       FAULT_EXPORT_AVAILABLE_COLUMNS, SPARE_EXPORT_COLUMNS,
                                       CUSTOMER_EXPORT_COLUMNS)

    assert DEVICE_EXPORT_COLUMNS == get_entity_schema('device').export_columns()
    assert TICKET_EXPORT_COLUMNS == get_entity_schema('ticket').export_columns()
    assert FAULT_EXPORT_COLUMNS == get_entity_schema('fault').export_columns()
    assert INSPECTION_EXPORT_COLUMNS == get_entity_schema('inspection').export_columns()
    assert SPARE_EXPORT_COLUMNS == get_entity_schema('spare').export_columns()
    assert CUSTOMER_EXPORT_COLUMNS == get_entity_schema('customer').export_columns('export_available')
    assert DEVICE_EXPORT_AVAILABLE_COLUMNS == get_entity_schema('device').export_columns('export_available')
    assert TICKET_EXPORT_AVAILABLE_COLUMNS == get_entity_schema('ticket').export_columns('export_available')
    assert FAULT_EXPORT_AVAILABLE_COLUMNS == get_entity_schema('fault').export_columns('export_available')
    assert dict(DEVICE_EXPORT_COLUMNS)['name'] == '名称'
    assert dict(TICKET_EXPORT_COLUMNS)['number'] == '工单号'
    assert dict(FAULT_EXPORT_COLUMNS)['fault_time'] == '故障时间'


def test_api_returns_only_permitted_entity_schemas(admin_client, viewer_client, client):
    assert client.get('/api/meta/entities').status_code == 401

    response = admin_client.get('/api/meta/entities?entities=device,ticket,fault')
    assert response.status_code == 200
    entities = response.get_json()['data']['entities']
    assert set(entities) == {'device', 'ticket', 'fault'}
    assert entities['device']['profiles']['list'][0]['exportKey'] == 'name'
    password = next(item for item in entities['device']['profiles']['form']
                    if item['key'] == 'password')
    assert password['sensitive'] is True
    assert password['permission'] == 'device:reveal'

    viewer_entities = viewer_client.get('/api/meta/entities').get_json()['data']['entities']
    for name, metadata in viewer_entities.items():
        assert ENTITY_SCHEMAS[name].view_permission in {
            'device:view', 'ticket:view', 'fault:view', 'inspection:view', 'spare:view',
            'customer:view', 'sales:view',
            'kb:view', 'category:view', 'user:view', 'permission:view',
        }
        assert metadata['profiles']['list']


def test_metadata_api_rejects_unknown_entity(admin_client):
    response = admin_client.get('/api/meta/entities?entities=device,unknown')
    assert response.status_code == 400
    assert response.get_json()['code'] == 1


def test_specialized_page_metadata_permissions_align(admin_client, sales_client, viewer_client):
    """同一业务实体用于不同页面时，用别名 schema 对齐页面/API 权限。"""
    admin_entities = admin_client.get(
        '/api/meta/entities?entities=device_export_review,review_checklist_config'
    ).get_json()['data']['entities']
    assert set(admin_entities) == {'device_export_review', 'review_checklist_config'}

    sales_entities = sales_client.get(
        '/api/meta/entities?entities=contract_inspection_task'
    ).get_json()['data']['entities']
    assert set(sales_entities) == {'contract_inspection_task'}

    viewer_entities = viewer_client.get(
        '/api/meta/entities?entities=device_export_review,review_checklist_config,contract_inspection_task'
    ).get_json()['data']['entities']
    assert viewer_entities == {}


def test_new_field_registry_entities_are_permission_scoped_and_secret_safe(
        admin_client, viewer_client):
    viewer_entities = viewer_client.get(
        '/api/meta/entities?entities=region,device_check_template,notify_channel'
    ).get_json()['data']['entities']
    assert set(viewer_entities) == {'region', 'device_check_template'}

    notify_channel = admin_client.get(
        '/api/meta/entities?entities=notify_channel'
    ).get_json()['data']['entities']['notify_channel']
    fields = {item['key'] for item in notify_channel['profiles']['detail']}
    assert 'has_secret' in fields
    assert 'secret' not in fields
    assert 'config' not in fields


def test_payload_contract_contains_fields_that_exports_already_expose(app):
    """Regression guard for the original list/detail/export field drift."""
    from blueprints.vue_api import _ticket_payload
    from blueprints.vue_api_ops import _fault_payload
    from models import Fault, Ticket

    with app.app_context():
        ticket = Ticket(number='WO-META', title='字段契约', reporter='张三',
                        reporter_phone='13800000000')
        fault = Fault(title='字段契约')
        ticket_payload = _ticket_payload(ticket)
        fault_payload = _fault_payload(fault)

    assert ticket_payload['reporter'] == '张三'
    assert ticket_payload['reporter_phone'] == '13800000000'
    assert 'recovery_time' in fault_payload
    assert 'created_at' in fault_payload


def test_frontend_metadata_requests_reference_registered_entities():
    """防止前端新增/改名实体后，页面静默回退为另一套本地字段口径。"""
    requested = set()
    for path in (ROOT / 'frontend' / 'src').rglob('*'):
        if path.suffix not in {'.ts', '.vue'}:
            continue
        source = path.read_text(encoding='utf-8')
        requested.update(re.findall(r"fetchEntityMeta\(\s*['\"]([^'\"]+)", source))
        for body in re.findall(r'fetchEntityMetas\(\s*\[([^]]*)]', source, re.S):
            requested.update(re.findall(r"['\"]([a-z][a-z0-9_]*)['\"]", body))

    assert requested
    assert requested <= set(ENTITY_SCHEMAS), \
        f'前端引用了未注册实体：{sorted(requested - set(ENTITY_SCHEMAS))}'


def test_persistent_business_tables_use_metadata_registry():
    """所有持久化业务表格必须读取字段注册表；临时抓包分析表不属于业务实体。"""
    views_root = ROOT / 'frontend' / 'src' / 'views'
    excluded = {Path('tools/PacketAnalyzer.vue')}
    missing = []
    for path in views_root.rglob('*.vue'):
        relative = path.relative_to(views_root)
        if relative in excluded:
            continue
        source = path.read_text(encoding='utf-8')
        if not re.search(r'<(?:el-table|DataTable)(?:\s|>)', source):
            continue
        if not re.search(r'(?:fetchEntityMeta|fetchEntityMetas|mergeFieldMeta|entityFieldLabel)',
                         source):
            missing.append(relative.as_posix())

    assert not missing, f'业务表格未接入字段注册表：{missing}'


def test_customer_tree_page_uses_customer_metadata_profiles():
    """客户页是树而非表格，也必须让列表、详情和表单标签共享注册表。"""
    source = (ROOT / 'frontend' / 'src' / 'views' / 'customers' / 'index.vue').read_text(
        encoding='utf-8')

    assert "fetchEntityMeta('customer')" in source
    assert "fieldLabel('level', '客户等级', 'list')" in source
    assert "fieldLabel('contact_person', '联系人')" in source
    assert "fieldLabel('name', '客户名称', 'form')" in source
