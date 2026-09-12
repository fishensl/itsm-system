"""Validated global reminder policy; scope is controlled by management routes."""
from models import db, SystemSetting
from services.base import transaction, ServiceError
from utils.json_fields import parse_json, dumps_json

KEY = 'notification.reminder_policy'
DEFAULTS = {'hour': 8, 'minute': 30, 'review_days': 3, 'escalation_days': 3,
            'escalate_supervisor': True, 'escalate_admin': True, 'extra_user_ids': []}


def current():
    row = db.session.get(SystemSetting, KEY)
    return DEFAULTS | (parse_json(row.value, default={}) if row else {})


@transaction
def save(data):
    from models import User
    if not isinstance(data, dict) or set(data) != set(DEFAULTS):
        raise ServiceError('提醒规则字段不完整')
    for key, low, high in [('hour', 0, 23), ('minute', 0, 59), ('review_days', 1, 90), ('escalation_days', 1, 90)]:
        if type(data[key]) is not int or not low <= data[key] <= high:
            raise ServiceError('提醒时间或等待天数不正确')
    if any(type(data[key]) is not bool for key in ('escalate_supervisor', 'escalate_admin')):
        raise ServiceError('升级开关必须为布尔值')
    ids = data['extra_user_ids']
    if not isinstance(ids, list) or len(ids) > 30 or any(type(i) is not int or i < 1 for i in ids):
        raise ServiceError('额外升级对象不正确')
    if len(set(ids)) != User.query.filter(User.id.in_(ids), User.is_active.is_(True)).count():
        raise ServiceError('升级对象不存在或已停用')
    row = db.session.get(SystemSetting, KEY)
    if not row:
        row = SystemSetting(key=KEY); db.session.add(row)
    row.value = dumps_json(data)
    return data


def escalation_users(user, active, policy):
    from models import Department
    result = {u.id for u in active.values() if u.is_admin} if policy['escalate_admin'] else set()
    if policy['escalate_supervisor']:
        dept = db.session.get(Department, user.department_id) if user.department_id else None
        seen = set()
        while dept and dept.id not in seen:
            seen.add(dept.id)
            if dept.head_id in active:
                result.add(dept.head_id); break
            dept = dept.parent
    result.update(i for i in policy['extra_user_ids'] if i in active)
    result.discard(user.id)
    return result
