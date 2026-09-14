"""Scoped customer notification configuration and history."""
from flask import request
from flask_login import current_user, login_required
from blueprints.vue_api import vue_api_bp, ok, fail
from blueprints.vue_api_sys import audit_log
from utils.permission import require_permission
from utils.operation_token import require_op_token
from services import customer_notify_service as service
from services.base import ServiceError
from app import limiter


@vue_api_bp.route('/api/customers/<int:customer_id>/notify-settings')
@login_required
@require_permission('customer:view')
def customer_notify_settings(customer_id):
    service.require_notify_customer_access(current_user, customer_id)
    return ok(service.settings(customer_id))


@vue_api_bp.route('/api/customers/<int:customer_id>/notify-webhook', methods=['PUT'])
@login_required
@require_permission('customer:notify')
@require_op_token(external_required=True)
def customer_notify_save(customer_id):
    service.require_notify_customer_access(current_user, customer_id)
    from services.credential_envelope_service import consume_request_envelope, purpose_required, note_raw_credential_compat
    data = request.get_json(silent=True) or {}
    options = {'binding_id', 'create', 'channel_type', 'name', 'subscriptions', 'quiet_start', 'quiet_end',
               'digest_minutes', 'inherit_to_children'}
    if not isinstance(data, dict) or set(data) - ({'wecom_webhook', 'notify_enabled', 'credential_envelope', 'signing_secret'} | options):
        return fail('通知配置字段不正确', 400)
    secret = data.get('wecom_webhook', '')
    signing_secret = data.get('signing_secret', '')
    envelope = data.get('credential_envelope')
    try:
        if envelope:
            if secret or signing_secret:
                return fail('不得同时提交明文和信封', 400)
            consumed = consume_request_envelope(service.PURPOSE, envelope,
                target_id=str(customer_id), operation_token=request.headers.get('X-Operation-Token', ''))
            secret = consumed.payload.get('secret')
            signing_secret = consumed.payload.get('signing_secret', '')
            if consumed.payload.get('binding_id') != data.get('binding_id'):
                return fail('凭据信封目的地不匹配', 400)
        elif secret or signing_secret:
            if purpose_required(service.PURPOSE):
                return fail('敏感字段必须使用凭据传输信封', 400)
            note_raw_credential_compat(service.PURPOSE)
        service.save_binding(customer_id, secret, data.get('notify_enabled', False), signing_secret=signing_secret,
                             **{key: data[key] for key in options if key in data})
    except ServiceError as exc:
        return fail(str(exc), 400)
    audit_log('customer:notify_update', 'customer', customer_id, '更新客户通知绑定与启用状态')
    return ok(service.settings(customer_id))


@vue_api_bp.route('/api/customers/<int:customer_id>/notify-inherit', methods=['PUT'])
@login_required
@require_permission('customer:notify')
@require_op_token(external_required=True)
def customer_notify_inherit_save(customer_id):
    """子级开关：无独立群时是否接收上级客户的共享群通知。"""
    service.require_notify_customer_access(current_user, customer_id)
    data = request.get_json(silent=True) or {}
    if set(data) != {'inherit_parent'} or type(data['inherit_parent']) is not bool:
        return fail('继承设置参数不正确', 400)
    try:
        service.save_inherit_parent(customer_id, data['inherit_parent'])
    except ServiceError as exc:
        return fail(str(exc), 400)
    audit_log('customer:notify_inherit', 'customer', customer_id,
              f'接收上级群通知={data["inherit_parent"]}')
    return ok(service.settings(customer_id))


@vue_api_bp.route('/api/customers/<int:customer_id>/notify-webhook', methods=['DELETE'])
@login_required
@require_permission('customer:notify')
@require_op_token(external_required=True)
def customer_notify_clear(customer_id):
    service.require_notify_customer_access(current_user, customer_id)
    try:
        service.clear_binding(customer_id, (request.get_json(silent=True) or {}).get('binding_id'))
    except ServiceError as exc:
        return fail(str(exc), 400)
    audit_log('customer:notify_clear', 'customer', customer_id, '解绑并停用客户通知')
    return ok(service.settings(customer_id))


@vue_api_bp.route('/api/customers/<int:customer_id>/notify-webhook/test', methods=['POST'])
@login_required
@require_permission('customer:notify')
@require_op_token(external_required=True)
@limiter.limit('5 per minute')
def customer_notify_test(customer_id):
    service.require_notify_customer_access(current_user, customer_id)
    try:
        event_id = service.test_binding(customer_id, (request.get_json(silent=True) or {}).get('binding_id'))
    except ServiceError as exc:
        return fail(str(exc), 400)
    audit_log('customer:notify_test', 'customer', customer_id, '测试消息已入队')
    return ok({'queued': True, 'event_id': event_id})


@vue_api_bp.route('/api/customers/<int:customer_id>/notify-deliveries')
@login_required
@require_permission('customer:notify')
def customer_notify_deliveries(customer_id):
    service.require_notify_customer_access(current_user, customer_id)
    from services.notification_management import history
    return ok(history(current_user, customer_id=customer_id))
