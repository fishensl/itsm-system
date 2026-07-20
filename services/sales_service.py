# -*- coding: utf-8 -*-
"""Sales 业务服务：商机/报价/合同/项目"""
from datetime import datetime
from models import db, Opportunity, Quotation, Contract, Project
from utils import constants as _const
from .base import ServiceError, transaction


# 商机阶段（单一真源在 utils/constants.py，此处保留 list 别名兼容模板/旧引用）
OPP_STAGES = list(_const.OPP_STAGES)


def _check_status(value, allowed, label):
    """写入边界校验：状态值必须在允许集合内（防拼写错误产生脏数据）"""
    if value and not _const.is_valid_status(value, allowed):
        raise ServiceError(f'非法的{label}：{value}')
    return value


@transaction
def create_opportunity(data, current_user_name):
    title = (data.get('title') or '').strip()
    if not title:
        raise ServiceError('商机标题不能为空')
    o = Opportunity(
        title=title,
        customer_id=int(data['customer_id']) if data.get('customer_id') else None,
        stage=_check_status(data.get('stage', '初步接触'), OPP_STAGES, '商机阶段'),
        expected_amount=float(data.get('expected_amount') or 0),
        owner=data.get('owner') or current_user_name,
        expected_close_date=_parse_date(data.get('expected_close_date')),
        remark=data.get('remark', ''),
    )
    db.session.add(o)
    return o


@transaction
def update_opportunity(opp_id, data):
    o = Opportunity.query.get_or_404(opp_id)
    o.title = (data.get('title') or o.title).strip()
    o.customer_id = int(data['customer_id']) if data.get('customer_id') else o.customer_id
    if 'stage' in data:
        o.stage = _check_status(data.get('stage'), OPP_STAGES, '商机阶段')
    o.expected_amount = float(data.get('expected_amount') or 0)
    o.owner = data.get('owner', o.owner)
    if 'expected_close_date' in data:
        o.expected_close_date = _parse_date(data.get('expected_close_date'))
    o.remark = data.get('remark', o.remark)
    return o


@transaction
def delete_opportunity(opp_id):
    o = Opportunity.query.get_or_404(opp_id)
    db.session.delete(o)


@transaction
def create_quotation(data, current_user_name):
    q = Quotation(
        number=data.get('number', ''),
        opportunity_id=int(data['opportunity_id']) if data.get('opportunity_id') else None,
        customer_id=int(data['customer_id']) if data.get('customer_id') else None,
        total_amount=float(data.get('total_amount') or 0),
        status=_check_status(data.get('status', '草稿'), _const.QUOTATION_STATUSES, '报价单状态'),
        valid_until=_parse_date(data.get('valid_until')) if data.get('valid_until') else None,
    )
    db.session.add(q)
    return q


@transaction
def update_quotation(quot_id, data):
    q = Quotation.query.get_or_404(quot_id)
    q.number = data.get('number', q.number)
    if data.get('opportunity_id'):
        q.opportunity_id = int(data['opportunity_id'])
    if data.get('customer_id'):
        q.customer_id = int(data['customer_id'])
    q.total_amount = float(data.get('total_amount') or 0)
    if 'status' in data:
        q.status = _check_status(data.get('status'), _const.QUOTATION_STATUSES, '报价单状态')
    if 'valid_until' in data:
        q.valid_until = _parse_date(data.get('valid_until'))
    return q


@transaction
def delete_quotation(quot_id):
    q = Quotation.query.get_or_404(quot_id)
    db.session.delete(q)


@transaction
def create_contract(data, current_user_name):
    title = (data.get('title') or '').strip()
    if not title:
        raise ServiceError('合同标题不能为空')
    c = Contract(
        number=data.get('number', ''),
        title=title,
        customer_id=int(data['customer_id']) if data.get('customer_id') else None,
        opportunity_id=int(data['opportunity_id']) if data.get('opportunity_id') else None,
        amount=float(data.get('amount') or 0),
        status=_check_status(data.get('status', '执行中'), _const.CONTRACT_STATUSES, '合同状态'),
        start_date=_parse_date(data.get('start_date')) if data.get('start_date') else None,
        end_date=_parse_date(data.get('end_date')) if data.get('end_date') else None,
        # 自动巡检配置（此前表单无字段、service 不持久化，属死逻辑——已补齐）
        inspection_frequency=data.get('inspection_frequency') or '',
        task_template_id=int(data['task_template_id']) if data.get('task_template_id') else None,
        auto_generate_tasks=bool(data.get('auto_generate_tasks')),
    )
    db.session.add(c)
    return c


@transaction
def update_contract(contract_id, data):
    c = Contract.query.get_or_404(contract_id)
    c.number = data.get('number', c.number)
    c.title = (data.get('title') or c.title).strip()
    if data.get('customer_id'):
        c.customer_id = int(data['customer_id'])
    if data.get('opportunity_id'):
        c.opportunity_id = int(data['opportunity_id'])
    c.amount = float(data.get('amount') or 0)
    if 'status' in data:
        c.status = _check_status(data.get('status'), _const.CONTRACT_STATUSES, '合同状态')
    if 'start_date' in data:
        c.start_date = _parse_date(data.get('start_date'))
    if 'end_date' in data:
        c.end_date = _parse_date(data.get('end_date'))
    # 自动巡检配置（频率/模板下拉总会提交，空串=清除；
    # checkbox 只有表单显式带 inspection_config_present 标记时才重置，保留局部更新语义）
    if 'inspection_frequency' in data:
        c.inspection_frequency = data.get('inspection_frequency') or ''
    if 'task_template_id' in data:
        c.task_template_id = int(data['task_template_id']) if data['task_template_id'] else None
    if data.get('inspection_config_present'):
        c.auto_generate_tasks = bool(data.get('auto_generate_tasks'))
    return c


@transaction
def delete_contract(contract_id):
    c = Contract.query.get_or_404(contract_id)
    db.session.delete(c)


@transaction
def create_project(data, current_user_name):
    name = (data.get('name') or '').strip()
    if not name:
        raise ServiceError('项目名称不能为空')
    p = Project(
        name=name,
        contract_id=int(data['contract_id']) if data.get('contract_id') else None,
        customer_id=int(data['customer_id']) if data.get('customer_id') else None,
        manager=data.get('manager') or current_user_name,
        status=_check_status(data.get('status', '进行中'), _const.PROJECT_STATUSES, '项目状态'),
        start_date=_parse_date(data.get('start_date')) if data.get('start_date') else None,
        end_date=_parse_date(data.get('end_date')) if data.get('end_date') else None,
        progress=int(data.get('progress') or 0),
        budget=float(data.get('budget') or 0),
    )
    db.session.add(p)
    return p


@transaction
def update_project(project_id, data):
    p = Project.query.get_or_404(project_id)
    p.name = (data.get('name') or p.name).strip()
    if data.get('contract_id'):
        p.contract_id = int(data['contract_id'])
    if data.get('customer_id'):
        p.customer_id = int(data['customer_id'])
    p.manager = data.get('manager', p.manager)
    if 'status' in data:
        p.status = _check_status(data.get('status'), _const.PROJECT_STATUSES, '项目状态')
    if 'start_date' in data:
        p.start_date = _parse_date(data.get('start_date'))
    if 'end_date' in data:
        p.end_date = _parse_date(data.get('end_date'))
    if 'progress' in data:
        p.progress = int(data.get('progress') or 0)
    if 'budget' in data:
        p.budget = float(data.get('budget') or 0)
    return p


@transaction
def delete_project(project_id):
    p = Project.query.get_or_404(project_id)
    db.session.delete(p)


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s).strip(), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None
