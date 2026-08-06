# -*- coding: utf-8 -*-
"""Sales 业务服务：商机/报价/合同/项目"""
from datetime import datetime
from models import db, Opportunity, Quotation, Contract, Project
from utils import constants as _const
from .base import ServiceError, transaction


# 商机阶段（单一真源在 utils/constants.py，此处保留 list 别名兼容模板/旧引用）
OPP_STAGES = list(_const.OPP_STAGES)
# 终态：成交/失败后不可再回退（防误操作把已成交商机改回进行中）
_OPP_TERMINAL = {_const.OPP_STAGE_WON, _const.OPP_STAGE_LOST}


def _check_status(value, allowed, label):
    """写入边界校验：状态值必须在允许集合内（防拼写错误产生脏数据）"""
    if value and not _const.is_valid_status(value, allowed):
        raise ServiceError(f'非法的{label}：{value}')
    return value


def _check_opp_stage_transition(o, new_stage):
    """商机阶段转换校验：终态不可回退；成交需金额>0；失败需说明原因（remark）"""
    if not new_stage or new_stage == o.stage:
        return
    _check_status(new_stage, OPP_STAGES, '商机阶段')
    if o.stage in _OPP_TERMINAL:
        raise ServiceError(f'商机已处于「{o.stage}」终态，不能回退为「{new_stage}」')
    if new_stage == _const.OPP_STAGE_WON and float(o.expected_amount or 0) <= 0:
        raise ServiceError('商机标记「成交」前请填写预计成交金额（expected_amount）')
    if new_stage == _const.OPP_STAGE_LOST and not (o.remark or '').strip():
        raise ServiceError('商机标记「失败」前请填写失败原因（备注）')


def _sync_projects_on_contract_status(contract, old_status):
    """合同-项目联动：合同改为「已终止/已完成」时，其下未完结项目自动置「已暂停」"""
    if contract.status == old_status:
        return
    if contract.status in (_const.CONTRACT_DONE, _const.CONTRACT_TERMINATED):
        changed = (Project.query
                   .filter(Project.contract_id == contract.id,
                           Project.status.in_([_const.PROJECT_NOT_STARTED, _const.PROJECT_ACTIVE]))
                   .update({'status': _const.PROJECT_PAUSED}, synchronize_session=False))
        if changed:
            from flask import current_app
            current_app.logger.info(
                '合同状态联动: 合同#%s → %s，其下 %d 个项目置为「已暂停」',
                contract.id, contract.status, changed)


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
    if 'expected_amount' in data:
        o.expected_amount = float(data.get('expected_amount') or 0)
    if data.get('remark') is not None:
        o.remark = data.get('remark', o.remark)
    if 'stage' in data:
        _check_opp_stage_transition(o, data.get('stage'))
        o.stage = data.get('stage')
    o.owner = data.get('owner', o.owner)
    if 'expected_close_date' in data:
        o.expected_close_date = _parse_date(data.get('expected_close_date'))
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
        items_json=_serialize_items(data.get('items') or data.get('items_json')),
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
    if 'items' in data or 'items_json' in data:
        q.items_json = _serialize_items(data.get('items') or data.get('items_json'))
    return q


def _serialize_items(raw):
    """报价明细行序列化：接受 [{name, quantity, unit_price}] 或 JSON 字符串；返回 JSON 字符串"""
    import json as _json
    if not raw:
        return ''
    if isinstance(raw, str):
        return raw
    rows = []
    for item in raw:
        if isinstance(item, dict) and str(item.get('name') or '').strip():
            rows.append({
                'name': str(item.get('name')).strip(),
                'quantity': float(item.get('quantity') or 0),
                'unit_price': float(item.get('unit_price') or 0),
            })
    return _json.dumps(rows, ensure_ascii=False) if rows else ''


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
    old_status = c.status
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
    _sync_projects_on_contract_status(c, old_status)
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
