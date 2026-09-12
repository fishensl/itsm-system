"""Notification operations and authenticated customer acknowledgements."""
from flask import request
from flask_login import current_user, login_required
from blueprints.vue_api import vue_api_bp, ok, fail
from blueprints.vue_api_sys import audit_log
from services import notification_management as service
from services.base import ServiceError
from utils.permission import require_permission
from utils.operation_token import require_op_token


@vue_api_bp.route('/api/notify-templates')
@login_required
@require_permission('notify:view')
def notification_templates():
    from services.notification_templates import current
    from services.notification_outbox import CUSTOMER_EVENTS
    return ok({'items': [{'event_type': k, 'label': v, **current(k)} for k, v in CUSTOMER_EVENTS.items()]})


@vue_api_bp.route('/api/notify-templates/<kind>', methods=['PUT'])
@login_required
@require_permission('notify:edit')
@require_op_token(external_required=True)
def notification_template_save(kind):
    from services.notification_templates import save
    from utils.permission import get_user_scope
    if get_user_scope(current_user) != 'all':
        return fail('全局模板管理需要全量数据范围', 403)
    try:
        cfg = save(kind, (request.get_json(silent=True) or {}).get('body'))
    except ServiceError as exc:
        return fail(str(exc), 400)
    audit_log('notify:template', 'notification_template', kind, f'发布模板版本 {cfg["version"]}')
    return ok(cfg)


@vue_api_bp.route('/api/notify-center')
@login_required
@require_permission('notify:view')
def notification_center():
    page = min(max(request.args.get('page', 1, type=int), 1), 10000)
    data = service.history(current_user, page, request.args.get('status', ''), request.args.get('customer_id', type=int), request.args.get('event_type', ''), request.args.get('page_size', 50, type=int), request.args.get('entity_type', ''), request.args.get('entity_id', type=int))
    data['metrics'] = service.metrics(current_user)
    return ok(data)


@vue_api_bp.route('/api/notify-center/<int:delivery_id>/attempts')
@login_required
@require_permission('notify:view')
def notification_attempts(delivery_id):
    service.get_delivery(current_user, delivery_id)
    from models import NotificationAttempt
    return ok({'items': [dict(number=r.number, result=r.result, error_code=r.error_code,
        created_at=r.created_at.isoformat() + 'Z') for r in NotificationAttempt.query.filter_by(delivery_id=delivery_id).order_by(NotificationAttempt.id).all()]})


@vue_api_bp.route('/api/notify-center/<int:delivery_id>/retry', methods=['POST'])
@login_required
@require_permission('notify:edit')
@require_op_token(external_required=True)
def notification_retry(delivery_id):
    try:
        service.retry_delivery(current_user, delivery_id, (request.get_json(silent=True) or {}).get('acknowledge_unknown'))
    except ServiceError as exc:
        return fail(str(exc), 400)
    audit_log('notify:retry', 'notification_delivery', delivery_id, '人工补发入队，已提示重复风险')
    return ok(None)


@vue_api_bp.route('/api/notification-preferences', methods=['GET', 'PUT'])
@login_required
def notification_preferences():
    try:
        return ok(service.preferences(current_user, request.get_json(silent=True) if request.method == 'PUT' else None))
    except ServiceError as exc:
        return fail(str(exc), 400)


@vue_api_bp.route('/api/my-notifications')
@login_required
def my_notifications():
    from models import Notification
    q = Notification.query.filter_by(user_id=current_user.id)
    if request.args.get('category'):
        q = q.filter_by(category=request.args['category'])
    if request.args.get('unread') == 'true':
        q = q.filter_by(is_read=False)
    page = min(max(request.args.get('page', 1, type=int), 1), 10000)
    total = q.count()
    rows = q.order_by(Notification.id.desc()).offset((page - 1) * 50).limit(50).all()
    return ok({'total': total, 'items': [dict(id=r.id, category=r.category, title=r.title, content=r.content,
               link=r.link, is_read=r.is_read, created_at=r.created_at.isoformat() + 'Z') for r in rows]})


@vue_api_bp.route('/api/customer-progress', methods=['POST'])
@login_required
@require_permission('customer:notify')
@require_op_token(external_required=True)
def public_progress():
    data = request.get_json(silent=True) or {}
    if data.get('confirm_public') is not True:
        return fail('请确认该进展可以公开给客户', 400)
    try:
        eid = service.publish_progress(current_user, data.get('entity_type'), data.get('entity_id'), data.get('content'))
    except ServiceError as exc:
        return fail(str(exc), 400)
    audit_log('customer:progress_publish', 'notification_event', eid, '主动发布客户可见进展')
    return ok({'id': eid})


@vue_api_bp.route('/api/customer-notifications')
@login_required
@require_permission('customer:confirm')
def customer_portal():
    return ok({'items': service.portal_events(current_user, min(max(request.args.get('page', 1, type=int), 1), 10000))})


@vue_api_bp.route('/api/customer-notifications/<event_id>/confirm', methods=['POST'])
@login_required
@require_permission('customer:confirm')
@require_op_token(external_required=True)
def customer_confirm(event_id):
    try:
        service.confirm_event(current_user, event_id, (request.get_json(silent=True) or {}).get('feedback', ''))
    except ServiceError as exc:
        return fail(str(exc), 400)
    audit_log('customer:confirm', 'notification_event', event_id, '客户服务消息反馈')
    return ok(None)


@vue_api_bp.route('/api/notification-policy')
@login_required
@require_permission('notify:view')
def notification_policy_get():
    from services.notification_policy import current
    return ok(current())


@vue_api_bp.route('/api/notification-policy', methods=['PUT'])
@login_required
@require_permission('notify:edit')
@require_op_token(external_required=True)
def notification_policy_save():
    from services.notification_policy import save
    from utils.permission import get_user_scope
    if get_user_scope(current_user) != 'all':
        return fail('全局提醒规则需要全量数据范围', 403)
    try:
        result = save(request.get_json(silent=True))
    except ServiceError as exc:
        return fail(str(exc), 400)
    audit_log('notify:policy', 'notification_policy', '', '更新提醒时间与升级规则')
    return ok(result)
