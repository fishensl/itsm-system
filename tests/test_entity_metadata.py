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


def test_device_location_power_and_export_profiles_share_one_contract():
    schema = get_entity_schema('device')
    location_block = ['rack_location', 'rack_name', 'location', 'rack_slot']

    list_keys = _keys(schema, 'list')
    start = list_keys.index('rack_location')
    assert list_keys[start:start + 4] == location_block
    assert list_keys[start + 4] == 'power_supply'

    form_keys = _keys(schema, 'form')
    start = form_keys.index('rack_location')
    assert form_keys[start:start + 4] == location_block
    assert form_keys[start + 4] == 'power_supply'

    for profile in ('export_default', 'export_available'):
        keys = _keys(schema, profile)
        start = keys.index('rack_location')
        assert keys[start:start + 4] == location_block
        assert keys[start + 4] == 'power_supply'

    for preset_name, preset in schema.export_presets.items():
        if preset_name == 'password':
            assert list(preset) == [
                'rack_location', 'device_name', 'device_type', 'brand', 'model',
                'ip_address', 'port', 'login_method', 'username', 'password',
                'is_in_use', 'pwd_changed_by', 'pwd_changed_at',
                'rack_name', 'location', 'rack_slot', 'serial_number',
            ]
            assert 'customer_name' not in preset
            assert 'power_supply' not in preset
            assert 'rated_power_w' not in preset
            assert 'remark' not in preset
            continue
        if preset_name == 'version':
            assert list(preset) == [
                'customer_name', 'rack_location', 'device_name', 'os_version',
                'rule_version', 'device_type', 'brand', 'model', 'serial_number', 'ip_address',
                'build_date', 'license_start', 'license_expiry', 'cert_expiry_date',
                'is_in_use', 'remark',
            ]
            assert not {
                'rack_name', 'location', 'rack_slot', 'power_supply', 'rated_power_w',
            } & set(preset)
            continue
        start = preset.index('rack_location')
        assert list(preset[start:start + 4]) == location_block
        assert preset[start + 4] == 'power_supply'

    # 明文密码是唯一安全例外；列表以 has_password 替代，其余导出字段均有同名列表列。
    export_fields = set(_keys(schema, 'export_available')) - {'password'}
    assert export_fields <= set(list_keys)
    assert 'has_password' in list_keys
    assert [key for key in _keys(schema, 'export_available') if key != 'password'] == [
        key for key in list_keys if key != 'has_password'
    ]


def test_device_edit_covers_every_business_field_from_list_and_export():
    """列表/导出的可维护字段必须进入编辑面；派生和审计字段必须明确只读展示。"""
    schema = get_entity_schema('device')
    list_and_export = set(_keys(schema, 'list')) | set(_keys(schema, 'export_available'))
    readonly = {
        'has_password', 'license_remaining_days', 'pwd_changed_by', 'pwd_changed_at', 'created_at',
        'id',
    }
    form_keys = set(_keys(schema, 'form'))
    assert list_and_export - readonly <= form_keys

    source = (ROOT / 'frontend' / 'src' / 'views' / 'devices' / 'index.vue').read_text(
        encoding='utf-8')
    form_binding = {
        'customer_name': 'customer_id',
        'rack_name': 'rack_id',
        'rack_slot': 'rack_start_u',
    }
    for key in form_keys:
        bound_key = form_binding.get(key, key)
        assert f'form.{bound_key}' in source, f'设备编辑框缺少字段绑定：{key}'
    for key in readonly - {'id'}:
        assert f"fieldLabel('device', '{key}'" in source, f'设备编辑框缺少只读说明：{key}'


def test_device_batch_edit_exposes_rack_number_and_u_placement():
    source = (ROOT / 'frontend' / 'src' / 'views' / 'devices' / 'index.vue').read_text(
        encoding='utf-8')
    assert 'value="rack_name"' in source
    assert 'batchForm.rackSelection' in source
    assert 'batchForm.startU' in source
    assert 'batchForm.occupyU' in source
    assert 'rack_custom_name: batchForm.rackCustomName' in source


def test_existing_export_codes_are_derived_without_contract_breakage():
    from blueprints.vue_export import (DEVICE_EXPORT_COLUMNS, DEVICE_EXPORT_AVAILABLE_COLUMNS,
                                       TICKET_EXPORT_COLUMNS, TICKET_EXPORT_AVAILABLE_COLUMNS,
                                       FAULT_EXPORT_COLUMNS, INSPECTION_EXPORT_COLUMNS,
                                       FAULT_EXPORT_AVAILABLE_COLUMNS, SPARE_EXPORT_COLUMNS,
                                       SPARE_EXPORT_AVAILABLE_COLUMNS,
                                       CUSTOMER_EXPORT_COLUMNS)

    assert DEVICE_EXPORT_COLUMNS == get_entity_schema('device').export_columns()
    assert TICKET_EXPORT_COLUMNS == get_entity_schema('ticket').export_columns()
    assert FAULT_EXPORT_COLUMNS == get_entity_schema('fault').export_columns()
    assert INSPECTION_EXPORT_COLUMNS == get_entity_schema('inspection').export_columns()
    assert SPARE_EXPORT_COLUMNS == get_entity_schema('spare').export_columns()
    assert SPARE_EXPORT_AVAILABLE_COLUMNS == get_entity_schema('spare').export_columns('export_available')
    assert CUSTOMER_EXPORT_COLUMNS == get_entity_schema('customer').export_columns('export_available')
    assert DEVICE_EXPORT_AVAILABLE_COLUMNS == get_entity_schema('device').export_columns('export_available')
    assert TICKET_EXPORT_AVAILABLE_COLUMNS == get_entity_schema('ticket').export_columns('export_available')
    assert FAULT_EXPORT_AVAILABLE_COLUMNS == get_entity_schema('fault').export_columns('export_available')
    assert dict(DEVICE_EXPORT_COLUMNS)['name'] == '名称'
    assert dict(DEVICE_EXPORT_COLUMNS)['device_id'] == '设备ID'
    assert dict(TICKET_EXPORT_COLUMNS)['number'] == '工单号'
    assert dict(FAULT_EXPORT_COLUMNS)['fault_time'] == '故障时间'


def test_fault_and_spare_export_available_cover_editable_fields():
    fault = get_entity_schema('fault')
    spare = get_entity_schema('spare')
    assert set(_keys(fault, 'form')) <= set(_keys(fault, 'export_available'))
    assert set(_keys(spare, 'form')) <= set(_keys(spare, 'export_available'))


def test_inspection_task_timing_is_shared_by_list_detail_and_export():
    schema = get_entity_schema('inspection')
    timing = {
        'task_contract_period', 'task_deadline_period',
        'task_actual_start', 'task_actual_end',
        'task_actual_duration', 'task_actual_effort',
    }
    assert 'task_actual_duration' in _keys(schema, 'list')
    assert timing <= set(_keys(schema, 'detail'))
    assert timing <= set(_keys(schema, 'export_default'))
    assert timing <= set(_keys(schema, 'export_available'))


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


def test_page_route_and_metadata_permissions_share_one_matrix():
    """页面入口权限必须足以读取该页面请求的全部 metadata。"""
    route_entities = {
        'customers': ('customer',),
        'regions': ('region',),
        'customer-categories': ('customer_category',),
        'devices': (
            'device', 'device_related_ticket', 'device_related_inspection',
            'device_export_request', 'config_backup', 'password_history',
        ),
        'device-dicts': ('device_dictionary',),
        'device-firmwares': ('firmware', 'device'),
        'tickets': ('ticket',),
        'inspections': ('inspection',),
        'inspectors': ('inspector',),
        'task-templates': ('task_template',),
        'device-check-templates': ('device_check_template',),
        'knowledge': ('knowledge',),
        'faults': ('fault',),
        'spare': ('spare', 'spare_stock', 'purchase_order', 'sales_order', 'spare_borrow'),
        'sales': ('opportunity', 'quotation', 'contract', 'project'),
        'contract-tasks': ('contract_auto_contract', 'contract_inspection_task'),
        'rack': ('rack', 'rack_install'),
        'topologies': ('topology',),
        'sys-users': ('user',),
        'sys-audit': ('audit_log',),
        'sys-export-reviews': ('device_export_review',),
        'permissions': ('role',),
        'sys-review-checklist': ('review_checklist_config',),
        'sys-notify-channels': ('notify_channel',),
        'sys-notify-rules': ('notify_rule',),
    }
    source = (ROOT / 'frontend' / 'src' / 'router' / 'index.ts').read_text(encoding='utf-8')
    for route_name, entities in route_entities.items():
        match = re.search(
            rf"name: '{re.escape(route_name)}'.*?meta: \{{[^}}]*perm: '([^']+)'",
            source,
            re.S,
        )
        assert match, f'路由 {route_name} 缺少显式权限'
        route_permission = match.group(1)
        assert {ENTITY_SCHEMAS[name].view_permission for name in entities} == {route_permission}, (
            route_name,
            route_permission,
            entities,
        )


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
