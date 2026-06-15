# -*- coding: utf-8 -*-
"""Fault 故障业务服务"""
from datetime import datetime
from models import db, Fault
from .base import ServiceError, transaction


@transaction
def create_fault(data, current_user_name):
    """新建故障"""
    title = (data.get('title') or '').strip()
    if not title:
        raise ServiceError('故障标题不能为空')
    fault_time = data.get('fault_time')
    if fault_time:
        try:
            fault_time = datetime.strptime(fault_time, '%Y-%m-%d %H:%M')
        except (ValueError, TypeError):
            fault_time = datetime.utcnow()
    f = Fault(
        title=title,
        customer_id=int(data['customer_id']) if data.get('customer_id') else None,
        device_id=int(data['device_id']) if data.get('device_id') else None,
        fault_type=data.get('fault_type', ''),
        fault_level=data.get('fault_level', '一般'),
        fault_time=fault_time or datetime.utcnow(),
        result=data.get('result', '处理中'),
        description=data.get('description', ''),
        solution=data.get('solution', ''),
        reporter=current_user_name,
        handler=data.get('handler', ''),
        remark=data.get('remark', ''),
    )
    db.session.add(f)
    return f


@transaction
def update_fault(fault_id, data):
    f = Fault.query.get_or_404(fault_id)
    f.title = (data.get('title') or f.title).strip()
    f.customer_id = int(data['customer_id']) if data.get('customer_id') else f.customer_id
    f.device_id = int(data['device_id']) if data.get('device_id') else f.device_id
    f.fault_type = data.get('fault_type', f.fault_type)
    f.fault_level = data.get('fault_level', f.fault_level)
    if data.get('fault_time'):
        try:
            f.fault_time = datetime.strptime(data['fault_time'], '%Y-%m-%d %H:%M')
        except (ValueError, TypeError):
            pass
    f.result = data.get('result', f.result)
    f.description = data.get('description', f.description)
    f.solution = data.get('solution', f.solution)
    f.handler = data.get('handler', f.handler)
    f.remark = data.get('remark', f.remark)
    return f


@transaction
def delete_fault(fault_id):
    f = Fault.query.get_or_404(fault_id)
    db.session.delete(f)
