from pathlib import Path
from types import SimpleNamespace

from blueprints.vue_api import _device_payload
from blueprints.vue_api_ops import _device_template_payload, _task_template_payload
from models import Device, InspectionDeviceTemplate
from services.customer_service import parse_extra_fields, serialize_extra_fields


ROOT = Path(__file__).resolve().parents[1]


def test_customer_extra_fields_supports_legacy_dict_and_rejects_malformed_json(app):
    with app.app_context():
        legacy = SimpleNamespace(extra_fields='{"机房":"A区"}')
        broken = SimpleNamespace(extra_fields='{broken')
        assert parse_extra_fields(legacy) == [{'name': '机房', 'value': 'A区'}]
        assert parse_extra_fields(broken) == []
        assert serialize_extra_fields(['机房'], ['A区']) == '[{"name": "机房", "value": "A区"}]'


def test_device_interface_malformed_or_wrong_shape_returns_typed_default(app):
    with app.app_context():
        broken = Device(device_name='broken-json', interface='{broken')
        wrong_shape = Device(device_name='wrong-shape', interface='{"eth0":"up"}')
        assert _device_payload(broken)['interface'] == []
        assert _device_payload(wrong_shape)['interface'] == []


def test_template_payloads_reject_valid_json_with_wrong_container_type(app):
    task = SimpleNamespace(
        id=1,
        name='任务模板',
        category='',
        inspection_type='',
        frequency='',
        customer_tier='',
        sections_json='[]',
        required_assets_json='[]',
        is_active=True,
        remark='',
        get_ordered_device_templates=lambda: [],
    )
    device = SimpleNamespace(
        id=1,
        name='设备模板',
        device_category='',
        device_sub_type='',
        items_json='{}',
        is_active=True,
        remark='',
        total_sub_items=0,
    )
    with app.app_context():
        task_payload = _task_template_payload(task)
        device_payload = _device_template_payload(device)
    assert task_payload['sections'] == []
    assert task_payload['required_assets'] == {}
    assert device_payload['items'] == []


def test_model_json_reader_rejects_valid_json_with_wrong_container_type(app):
    with app.app_context():
        template = InspectionDeviceTemplate(name='wrong-shape', items_json='{}')
        assert template.get_normalized_items() == []


def test_migrated_json_text_modules_do_not_bypass_shared_boundary():
    paths = [
        'services/customer_service.py',
        'services/device_service.py',
        'services/inspection_service.py',
        'services/sales_service.py',
        'services/submission_version_service.py',
        'blueprints/drafts.py',
        'blueprints/ops/templates.py',
        'blueprints/vue_api_ops.py',
        'models/inspection.py',
        'scripts/import_asset_devices.py',
        'utils/cert_options.py',
        'utils/report_generator.py',
        'utils/sidebar_config.py',
        'views/dashboard.py',
    ]
    for relative in paths:
        source = (ROOT / relative).read_text(encoding='utf-8')
        assert 'json.loads(' not in source, relative
        assert 'json.dumps(' not in source, relative
