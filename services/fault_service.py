# -*- coding: utf-8 -*-
"""Fault 故障业务服务"""
from datetime import datetime
from models import db, Fault
from .base import ServiceError, transaction


def _parse_dt(value):
    """解析 datetime-local 表单值（%Y-%m-%dT%H:%M），失败返回 None"""
    if not value:
        return None
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


@transaction
def create_fault(data, current_user_name):
    """新建故障"""
    title = (data.get('title') or '').strip()
    if not title:
        raise ServiceError('故障标题不能为空')
    f = Fault(
        title=title,
        customer_id=int(data['customer_id']) if data.get('customer_id') else None,
        fault_type=data.get('fault_type', ''),
        fault_time=_parse_dt(data.get('fault_time')) or datetime.utcnow(),
        recovery_time=_parse_dt(data.get('recovery_time')),
        result=data.get('result', '已解决'),
        fault_description=data.get('fault_description', ''),
        fault_cause=data.get('fault_cause', ''),
        impact_range=data.get('impact_range', ''),
        solution=data.get('solution', ''),
        handler=data.get('handler', '') or current_user_name,
    )
    db.session.add(f)
    return f


@transaction
def update_fault(fault_id, data):
    f = Fault.query.get_or_404(fault_id)
    f.title = (data.get('title') or f.title).strip()
    f.customer_id = int(data['customer_id']) if data.get('customer_id') else f.customer_id
    f.fault_type = data.get('fault_type', f.fault_type)
    if data.get('fault_time'):
        f.fault_time = _parse_dt(data['fault_time']) or f.fault_time
    if 'recovery_time' in data:
        f.recovery_time = _parse_dt(data.get('recovery_time'))
    f.result = data.get('result', f.result)
    f.fault_description = data.get('fault_description', f.fault_description)
    f.fault_cause = data.get('fault_cause', f.fault_cause)
    f.impact_range = data.get('impact_range', f.impact_range)
    f.solution = data.get('solution', f.solution)
    f.handler = data.get('handler', f.handler)
    return f


@transaction
def delete_fault(fault_id):
    f = Fault.query.get_or_404(fault_id)
    # 清理知识库对该故障的引用，避免悬挂外键
    from models import KnowledgeBase
    KnowledgeBase.query.filter_by(related_fault_id=fault_id).update({'related_fault_id': None})
    db.session.delete(f)
