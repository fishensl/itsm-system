"""Scoped multi-channel destinations; request handlers never send HTTP."""
import hashlib
from urllib.parse import parse_qs, urlsplit
from sqlalchemy import select
from models import db, Customer, CustomerNotifyBinding, NotifyChannelConfig, NotificationDelivery
from services.base import ServiceError, transaction
from services.notification_outbox import CUSTOMER_EVENTS as EVENT_LABELS, allowed, insert_event, CANCELLED, PENDING, RETRY
from utils.crypto import encrypt_password, decrypt_password
from utils.json_fields import parse_json, dumps_json
from utils.notify_channels.customer_robots import validate_robot

PURPOSE = 'customer.notify.credential.update'


def require_notify_customer_access(user, customer_id):
    from utils.customer_scope import _configured_customer_ids
    from werkzeug.exceptions import NotFound
    ids = _configured_customer_ids(user)
    if (ids is not None and customer_id not in ids) or not db.session.get(Customer, customer_id):
        raise NotFound()


def fingerprint(url, channel_type='wecom'):
    p = urlsplit(validate_robot(channel_type, url))
    value = parse_qs(p.query)['key'][0] if channel_type == 'wecom' else channel_type + ':' + (parse_qs(p.query)['access_token'][0] if channel_type == 'dingtalk' else p.path)
    return hashlib.sha256(value.encode()).hexdigest()


def ensure_destination_available(url, customer_id=None, *, channel_type='wecom', binding_id=None):
    fp = fingerprint(url, channel_type)
    conflict = CustomerNotifyBinding.query.filter_by(fingerprint=fp).first()
    if conflict and conflict.id != binding_id and (binding_id is not None or conflict.customer_id != customer_id):
        raise ServiceError('该机器人已用于其他通知目的地')
    if customer_id is not None and channel_type == 'wecom':
        row = NotifyChannelConfig.query.filter_by(channel_type='wecom').first()
        cfg = parse_json(row.config_json, default={}) if row else {}
        if cfg.get('webhook_url_encrypted'):
            try:
                other = fingerprint(decrypt_password(cfg['webhook_url_encrypted']))
            except Exception:
                raise ServiceError('内部渠道凭据异常，请先修复') from None
            if other == fp:
                raise ServiceError('客户群不能使用内部通知机器人')
    return fp


def binding_payload(r):
    return dict(id=r.id, name=r.name, channel_type=r.channel_type, notify_enabled=r.enabled,
        has_wecom_webhook=bool(r.webhook_encrypted), has_signing_secret=bool(r.signing_secret_encrypted),
        inherit_to_children=bool(r.inherit_to_children),
        subscriptions=parse_json(r.subscriptions_json, default={}), quiet_start=r.quiet_start,
        quiet_end=r.quiet_end, digest_minutes=r.digest_minutes)


def _ancestor_ids(connection, customer_id, limit=10):
    """自下而上返回父级客户 id（防环、限深）。"""
    chain, seen, current = [], {int(customer_id)}, int(customer_id)
    for _ in range(limit):
        parent_id = connection.execute(
            select(Customer.parent_id).where(Customer.id == current)).scalar()
        if not parent_id or parent_id in seen:
            break
        seen.add(parent_id)
        chain.append(parent_id)
        current = parent_id
    return chain


def resolve_bindings(connection, customer_id, kind=None):
    """解析客户事件应使用的绑定。

    - 已配置独立 webhook（无论启停）= 独立模式：只用本客户启用且订阅命中的绑定，不继承；
    - 无独立 webhook 且子级开关开启：向上取最近一级"启用 + 允许下级共用 + 订阅命中"的绑定。

    返回 (bindings, inherited)；kind=None 表示不按订阅过滤（供展示使用）。
    """
    rows = connection.execute(select(CustomerNotifyBinding.__table__).where(
        CustomerNotifyBinding.customer_id == customer_id)).mappings().all()
    own = [r for r in rows if r['webhook_encrypted']]
    if own:
        return [r for r in own
                if r['enabled'] and (kind is None or allowed(r, kind))], False
    flag = connection.execute(select(Customer.notify_inherit_parent).where(
        Customer.id == customer_id)).scalar()
    if flag is False:
        return [], True
    for ancestor_id in _ancestor_ids(connection, customer_id):
        rows = connection.execute(select(CustomerNotifyBinding.__table__).where(
            CustomerNotifyBinding.customer_id == ancestor_id,
            CustomerNotifyBinding.enabled.is_(True),
            CustomerNotifyBinding.inherit_to_children.is_(True))).mappings().all()
        matched = [r for r in rows
                   if r['webhook_encrypted'] and (kind is None or allowed(r, kind))]
        if matched:
            return matched, True
    return [], True


def inherited_binding_info(customer_id):
    """展示用：无独立群时返回最近可继承的上级绑定摘要，否则 None。"""
    bindings, inherited = resolve_bindings(db.session.connection(), customer_id, kind=None)
    if not inherited or not bindings:
        return None
    row = bindings[0]
    owner = db.session.get(Customer, row['customer_id'])
    return {
        'binding_id': row['id'],
        'name': row['name'],
        'customer_id': row['customer_id'],
        'customer_name': owner.name if owner else '',
        'digest': parse_json(row['subscriptions_json'], default={}).get('customer_digest') is True,
    }


def settings(customer_id):
    rows = CustomerNotifyBinding.query.filter_by(customer_id=customer_id).order_by(CustomerNotifyBinding.id).all()
    customer = db.session.get(Customer, customer_id)
    has_own_webhook = any(r.webhook_encrypted for r in rows)
    return dict(notify_enabled=any(r.enabled for r in rows),
                has_wecom_webhook=has_own_webhook,
                has_own_binding=bool(rows),
                notify_inherit_parent=bool(customer.notify_inherit_parent) if customer else True,
                inherited_from=None if has_own_webhook else inherited_binding_info(customer_id),
                bindings=[binding_payload(r) for r in rows], events=EVENT_LABELS)


@transaction
def save_inherit_parent(customer_id, enabled):
    """子级开关：无独立群时是否接收上级客户的共享群通知。"""
    if type(enabled) is not bool:
        raise ServiceError('继承设置格式不正确')
    customer = db.session.get(Customer, customer_id)
    if not customer:
        raise ServiceError('客户不存在')
    customer.notify_inherit_parent = enabled
    return customer


def _binding(customer_id, binding_id):
    q = CustomerNotifyBinding.query.filter_by(customer_id=customer_id)
    if binding_id is not None:
        r = q.filter_by(id=binding_id).with_for_update().first()
        if not r:
            raise ServiceError('通知目的地不存在')
        return r
    return q.order_by(CustomerNotifyBinding.id).with_for_update().first()


@transaction
def save_binding(customer_id, secret, enabled, *, binding_id=None, create=False, channel_type='wecom',
                 name='客户群', signing_secret='', subscriptions=None, quiet_start=0, quiet_end=0,
                 digest_minutes=0, inherit_to_children=False):
    if not isinstance(secret, str) or not isinstance(enabled, bool) or not isinstance(signing_secret, str):
        raise ServiceError('通知配置格式不正确')
    if type(inherit_to_children) is not bool:
        raise ServiceError('下级共用设置格式不正确')
    if type(create) is not bool or (binding_id is not None and (type(binding_id) is not int or binding_id < 1)):
        raise ServiceError('通知目的地参数不正确')
    if channel_type not in {'wecom', 'dingtalk', 'feishu'} or not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ServiceError('渠道或名称不正确')
    if any(type(v) is not int or not 0 <= v <= 23 for v in (quiet_start, quiet_end)) or digest_minutes not in (0, 5, 15, 30, 60):
        raise ServiceError('静默时间或汇总间隔不正确')
    subscriptions = subscriptions if subscriptions is not None else {}
    if not isinstance(subscriptions, dict) or set(subscriptions) - set(EVENT_LABELS) or any(type(v) is not bool for v in subscriptions.values()):
        raise ServiceError('客户订阅包含不允许的事件')
    r = None if create else _binding(customer_id, binding_id)
    if not r:
        r = CustomerNotifyBinding(customer_id=customer_id, version=0, webhook_encrypted='', signing_secret_encrypted='')
        db.session.add(r)
    elif r.channel_type != channel_type:
        if not secret:
            raise ServiceError('变更渠道需要重新填写机器人地址')
        r.signing_secret_encrypted = ''
    if secret.strip():
        try:
            r.fingerprint = ensure_destination_available(secret.strip(), customer_id, channel_type=channel_type, binding_id=r.id or -1)
        except ServiceError:
            raise
        except Exception:
            raise ServiceError('请输入有效的官方 HTTPS 机器人地址') from None
        r.webhook_encrypted = encrypt_password(secret.strip())
    if signing_secret:
        r.signing_secret_encrypted = encrypt_password(signing_secret)
    if enabled and not r.webhook_encrypted:
        raise ServiceError('请先绑定机器人再启用')
    r.enabled, r.channel_type, r.name = enabled, channel_type, name.strip()
    r.quiet_start, r.quiet_end, r.digest_minutes = quiet_start, quiet_end, digest_minutes
    r.inherit_to_children = inherit_to_children
    r.subscriptions_json = dumps_json(subscriptions)
    r.version += 1
    if r.id:
        NotificationDelivery.query.filter(NotificationDelivery.binding_id == r.id, NotificationDelivery.status.in_([PENDING, RETRY])).update({'status': CANCELLED, 'error_code': 'binding_changed'})
    return r


@transaction
def clear_binding(customer_id, binding_id=None):
    r = _binding(customer_id, binding_id)
    if r:
        r.webhook_encrypted, r.signing_secret_encrypted, r.fingerprint = '', '', None
        r.enabled = False
        r.version += 1
        NotificationDelivery.query.filter(NotificationDelivery.binding_id == r.id, NotificationDelivery.status.in_([PENDING, RETRY])).update({'status': CANCELLED, 'error_code': 'unbound'})


def notify_ticket(ticket, event_type):
    """Compatibility no-op: mapper events are the sole customer event producer."""
    return False


def notify_task(task, event_type):
    return False


@transaction
def test_binding(customer_id, binding_id=None):
    r = _binding(customer_id, binding_id)
    if not r or not r.enabled or not r.webhook_encrypted:
        raise ServiceError('请先保存并启用该目的地')
    eid = insert_event(db.session.connection(), 'test', {'title': '通知渠道测试', 'content': 'ITSM 测试，无业务数据。'}, customer_id=customer_id)
    NotificationDelivery.query.filter(NotificationDelivery.event_id == eid, NotificationDelivery.binding_id != r.id).delete()
    return eid
