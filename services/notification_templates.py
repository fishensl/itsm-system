"""Versioned text templates with two explicit public variables, no executable syntax."""
from string import Formatter
from models import db, SystemSetting
from services.base import ServiceError, transaction
from utils.json_fields import parse_json, dumps_json

PREFIX = 'notification.template.'


def validate(value):
    if not isinstance(value, str) or len(value) > 1200:
        raise ServiceError('模板必须是最多 1200 字的文本')
    try:
        for _, field, spec, conversion in Formatter().parse(value):
            if field is not None and (field not in {'title', 'content'} or spec or conversion):
                raise ValueError()
        value.format(title='服务状态', content='客户可见内容')
    except (ValueError, KeyError, IndexError):
        raise ServiceError('只允许 {title} 和 {content} 两个变量') from None


def current(kind):
    row = db.session.get(SystemSetting, PREFIX + kind)
    return parse_json(row.value, default={}) if row else {'body': '{content}', 'version': 1}


@transaction
def save(kind, body):
    from services.notification_outbox import CUSTOMER_EVENTS
    if kind not in CUSTOMER_EVENTS:
        raise ServiceError('不允许的客户事件')
    validate(body)
    row = SystemSetting.query.filter_by(key=PREFIX + kind).with_for_update().first()
    old = parse_json(row.value, default={}) if row else {}
    if not row:
        row = SystemSetting(key=PREFIX + kind)
        db.session.add(row)
    cfg = {'body': body, 'version': int(old.get('version', 1)) + 1}
    row.value = dumps_json(cfg)
    return cfg


def render(connection, kind, payload):
    from sqlalchemy import select
    raw = connection.execute(select(SystemSetting.value).where(SystemSetting.key == PREFIX + kind)).scalar()
    cfg = parse_json(raw, default={}) if raw else {}
    body = cfg.get('body', '{content}')
    try:
        validate(body)
    except ServiceError:
        body = '{content}'
    from utils.notification_content import compact_content, single_line
    title = single_line(payload['title'])
    content = compact_content(title, body.format(title=title, content=payload.get('content', '')))
    return ({'title': title, 'content': content}, int(cfg.get('version', 1)))
