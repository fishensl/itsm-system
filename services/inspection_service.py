# -*- coding: utf-8 -*-
"""Inspection 巡检业务服务（V21：审核闭环版本化）

闭环：任务执行中 → 工程师上传报告（建 SubmissionVersion）→ 任务待审核
     → 管理员审核（意见挂版本）→ 通过=任务已完成 / 退回=任务回执行中可再传
任务↔记录 1:1：同一任务复用同一记录，每次上传追加新版本。
"""
import os
from datetime import datetime
from flask import current_app
from models import db, Inspection, InspectionTask, SubmissionVersion, User
from .base import ServiceError, transaction
from .submission_version_service import add_version, review_version, latest_pending_version
from .task_schedule_service import apply_task_status
from utils.constants import (REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED,
                             TASK_PENDING, TASK_REVIEWING, TASK_RUNNING, TASK_RETURNED, TASK_DONE)
from utils.json_fields import dumps_json, parse_json


def _resolve_inspector(data, current_user_name):
    """V13: 从表单解析巡检人员，返回 (user_id, name, phone)。
    优先级：inspector_user_id (int) → inspector (字符串姓名) → current_user_name
    冻结快照写入 inspection 后，历史报告免疫 User 改名。
    """
    raw_uid = data.get('inspector_user_id')
    if raw_uid:
        try:
            uid = int(raw_uid)
        except (TypeError, ValueError):
            uid = None
        if uid:
            u = User.query.get(uid)
            if u:
                name = (u.realname or u.username or '').strip()
                return uid, name, (u.phone or '').strip()
    # fallback：仅有姓名字符串（兼容老表单/老草稿）
    name = (data.get('inspector') or current_user_name or '').strip()
    if name:
        u = User.query.filter_by(realname=name).first()
        if u:
            return u.id, name, (u.phone or '').strip()
    return None, name, ''


def inspection_reviewer_options(submitter=None, department_id=None):
    """返回可选巡检审核人，部门负责人优先、管理员兜底。

    资格始终按实际 ``inspection:review`` 权限计算，避免仅凭角色名称展示一个
    最终会被接口拒绝的用户。提交人本人不进入候选，防止自审。
    """
    from models import Department
    from utils.permission import get_user_permissions

    submitter_id = getattr(submitter, 'id', None)
    nearest_head_ids = []
    dept = db.session.get(Department, department_id) if department_id else None
    seen = set()
    while dept and dept.id not in seen:
        seen.add(dept.id)
        if dept.head_id and dept.head_id != submitter_id:
            nearest_head_ids.append(dept.head_id)
        dept = dept.parent

    headed_by_user = {
        user_id: names
        for user_id, names in _headed_department_names().items()
    }
    rows = []
    for user in User.query.filter_by(is_active=True).order_by(User.realname, User.username).all():
        if user.id == submitter_id:
            continue
        if 'inspection:review' not in get_user_permissions(user):
            continue
        department_name = user.department_rel.name if user.department_rel else ''
        headed_names = headed_by_user.get(user.id, [])
        if user.id in nearest_head_ids:
            priority = nearest_head_ids.index(user.id)
        elif user.is_admin:
            priority = 100
        else:
            priority = 200
        rows.append({
            'id': user.id,
            'name': user.realname or user.username,
            'department_name': department_name,
            'responsible_departments': headed_names,
            'is_department_head': bool(headed_names),
            '_priority': priority,
        })
    rows.sort(key=lambda item: (
        item['_priority'], item['department_name'], item['name'], item['id']))
    for item in rows:
        item.pop('_priority', None)
    return rows


def _headed_department_names():
    from models import Department
    result = {}
    for department in Department.query.filter(Department.head_id.isnot(None)).all():
        result.setdefault(department.head_id, []).append(department.name)
    return result


def resolve_inspection_reviewer(reviewer_id, submitter=None, department_id=None):
    """校验/选择本轮审核人；未显式选择时默认最近一级部门负责人。"""
    options = inspection_reviewer_options(submitter, department_id)
    by_id = {item['id']: item for item in options}
    if reviewer_id not in (None, ''):
        try:
            selected_id = int(reviewer_id)
        except (TypeError, ValueError) as exc:
            raise ServiceError('审核人参数无效') from exc
        if selected_id not in by_id:
            raise ServiceError('所选审核人无巡检审核权限，或不能审核本人提交的记录')
        return selected_id
    if not options:
        raise ServiceError('当前没有可用的巡检审核人，请先设置部门负责人或授予巡检审核权限')
    return options[0]['id']


def inspection_completeness(i):
    """巡检记录资料完整性检查：返回 (complete, missing_fields)"""
    missing = []
    if not (i.title or '').strip():
        missing.append('标题')
    if not i.customer_id:
        missing.append('客户')
    if not i.inspector_user_id and not (i.inspector_name or '').strip():
        missing.append('工程师')
    if not (i.conclusion or '').strip():
        missing.append('结论')
    if not i.submitted_report:
        missing.append('现场报告')
    # 正式报告当前为可选产物；模板完善并开启自动生成后再纳入完整性门禁。
    if current_app.config.get('AUTO_GENERATE_INSPECTION_REPORT') and not i.report_file:
        missing.append('正式报告')
    if i.review_status != REVIEW_APPROVED:
        missing.append('审核通过')
    return not missing, missing


@transaction
def create_inspection(data, current_user_name):
    """新建巡检记录（V21：强制关联任务，任务↔记录 1:1）。

    - task_id 必填，任务必须存在且尚无记录；
    - 未显式传 customer_id / inspector 时从任务自动带出。
    """
    title = (data.get('title') or '').strip()
    if not title:
        raise ServiceError('巡检标题不能为空')
    task_id = data.get('task_id')
    try:
        task_id = int(task_id) if task_id else None
    except (TypeError, ValueError):
        task_id = None
    if not task_id:
        raise ServiceError('巡检记录必须关联巡检任务')
    task = InspectionTask.query.get(task_id)
    if not task:
        raise ServiceError('关联的巡检任务不存在')
    existing = Inspection.query.filter_by(task_id=task.id).first()
    if existing:
        raise ServiceError('该任务已存在巡检记录（任务↔记录 1:1），请直接在该记录上补充上传报告')

    inspection_date = data.get('inspection_date')
    if inspection_date:
        try:
            inspection_date = datetime.strptime(inspection_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            inspection_date = None
    uid, name, phone = _resolve_inspector(data, current_user_name)
    if not uid and task.assigned_to_user_id:
        assignee = User.query.get(task.assigned_to_user_id)
        if assignee:
            uid = assignee.id
            name = (assignee.realname or assignee.username or '').strip()
            phone = (assignee.phone or '').strip()
    i = Inspection(
        title=title,
        customer_id=int(data['customer_id']) if data.get('customer_id') else task.customer_id,
        task_id=task.id,
        inspection_date=inspection_date or datetime.utcnow().date(),
        inspector=name,                  # 旧字段（向后兼容）
        inspector_user_id=uid,           # V13: 关联 User 用于追溯归属
        inspector_name=name,             # V13: 冻结快照
        inspector_phone=phone,           # V13: 冻结快照
        overall_status=data.get('overall_status', REVIEW_PENDING),
        location=data.get('location', ''),
        content_json=data.get('content_json', '[]'),
        field_values_json=data.get('field_values_json', '{}'),
        sections_json=data.get('sections_json', '{}'),
        skip_reasons_json=data.get('skip_reasons_json', '{}'),
    )
    db.session.add(i)
    db.session.flush()
    return i


@transaction
def update_inspection(inspection_id, data):
    """更新巡检 — V13: inspector_user_id 改变时刷新姓名/手机快照，
    未变更则保持原快照不动（避免无意改名污染历史）"""
    i = Inspection.query.get_or_404(inspection_id)
    i.title = (data.get('title') or i.title).strip()
    if data.get('customer_id'):
        i.customer_id = int(data['customer_id'])
    if data.get('task_id'):
        i.task_id = int(data['task_id'])
    if data.get('inspection_date'):
        try:
            i.inspection_date = datetime.strptime(data['inspection_date'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    # V13: 仅当提交的 inspector_user_id 与当前不同时刷新快照
    new_uid_raw = data.get('inspector_user_id')
    if new_uid_raw is not None and str(new_uid_raw) != '':
        try:
            new_uid = int(new_uid_raw)
        except (TypeError, ValueError):
            new_uid = None
        if new_uid and new_uid != i.inspector_user_id:
            u = User.query.get(new_uid)
            if u:
                name = (u.realname or u.username or '').strip()
                i.inspector_user_id = u.id
                i.inspector_name = name
                i.inspector_phone = (u.phone or '').strip()
                i.inspector = name
    elif data.get('inspector') and not i.inspector_user_id:
        # 老表单兜底：仅当还未关联 User 时允许修改字符串姓名
        i.inspector = data['inspector'].strip()
        i.inspector_name = i.inspector
    i.overall_status = data.get('overall_status', i.overall_status)
    if 'location' in data:
        i.location = data.get('location', i.location)
    if 'content_json' in data:
        i.content_json = data.get('content_json', i.content_json)
    if 'field_values_json' in data:
        i.field_values_json = data.get('field_values_json', i.field_values_json)
    if 'sections_json' in data:
        i.sections_json = data.get('sections_json', i.sections_json)
    if 'skip_reasons_json' in data:
        i.skip_reasons_json = data.get('skip_reasons_json', i.skip_reasons_json)
    return i


def _task_from_inspection(i):
    return i.task_rel


def _sync_task_to_reviewing(i, current_user_id=None):
    """记录提交审核 → 关联任务同步为「待审核」。

    - 任务「执行中」→「待审核」；
    - 任务「待执行」→ 自动开始（写 actual_start）→「待审核」。
    """
    task = _task_from_inspection(i)
    if not task:
        return None
    if task.status in (TASK_RUNNING, TASK_RETURNED):
        apply_task_status(task, TASK_REVIEWING)
    elif task.status == TASK_PENDING:
        apply_task_status(task, TASK_RUNNING)
        apply_task_status(task, TASK_REVIEWING)
    return task


def _return_task_for_revision(i):
    """记录被退回 → 关联任务进入「退回修改」（若任务处于待审核）。"""
    task = _task_from_inspection(i)
    if task and task.status == TASK_REVIEWING:
        apply_task_status(task, TASK_RETURNED, allow_review_return=True)


@transaction
def upload_report_for_task(task_id, report_path, conclusion, current_user_id,
                           current_user_name, submit_review=True, force=False, remark='',
                           reviewer_id=None,
                           report_skip_reason='',
                           config_zip_path='', config_zip_file_name='',
                           config_zip_device_id=None, config_zip_skip_reason='',
                           config_texts=None, config_text_skip_reason='',
                           topology_file_path='', topology_file_name='', topology_skip_reason='',
                           asset_list_path='', asset_list_file_name='', asset_list_skip_reason=''):
    """工程师从任务上传现场报告（全套资料）→ 自动生成/复用巡检记录并提交审核。

    全套资料（V22）：巡检报告（必传默认，可配置豁免）+ 完整配置包 config_zip +
    核心设备文本配置 config_texts（[{name, device_id, content, file_path, file_name}]）+
    拓扑图 topology + 资产清单 asset_list（已由调用方解析导入设备）。

    规则：
    - 任务必须存在且处于「执行中」（待审核时不可重复上传）；
    - 上传者必须是任务指派者本人；force=True 时跳过归属校验（管理员代传）；
    - 任务已有「待审核」版本时拒绝重复上传（先等审核）；
    - 必传项（按任务模板 required_assets_json 配置）缺传且未填豁免原因 → 拒绝；
    - 资料同步：文本配置/配置包 → DeviceConfigBackup，拓扑图 → Topology；
    - 创建记录后任务「执行中 → 待审核」。
    返回 (inspection, version, asset_result)。
    """
    from .submission_version_service import add_asset

    task = InspectionTask.query.get_or_404(task_id)
    if task.status not in (TASK_RUNNING, TASK_RETURNED, TASK_REVIEWING, TASK_PENDING, TASK_DONE):
        raise ServiceError('任务状态「%s」不允许上传报告（仅执行中/退回修改/待审核/待执行/已完成的任务可上传）' % task.status)

    if not force and task.assigned_to_user_id and current_user_id \
            and int(task.assigned_to_user_id) != int(current_user_id):
        raise ServiceError('只有该任务指派工程师或管理员可以上传报告')
    # 未指派任务：允许上传（上传端点已有 inspection:edit 权限门，非任意登录用户）；
    # 上传者身份由调用方记录（uploader/管理员代传 force），此处不再额外拦截。

    _check_required_assets(task, report_path=report_path, report_skip_reason=report_skip_reason,
                           config_zip_path=config_zip_path,
                           config_zip_skip_reason=config_zip_skip_reason,
                           config_texts=config_texts or [],
                           config_text_skip_reason=config_text_skip_reason,
                           topology_file_path=topology_file_path,
                           topology_skip_reason=topology_skip_reason,
                           asset_list_path=asset_list_path,
                           asset_list_skip_reason=asset_list_skip_reason)

    inspection = Inspection.query.filter_by(task_id=task.id).first()
    if inspection:
        if inspection.review_status == REVIEW_PENDING:
            raise ServiceError('该任务已有「待审核」巡检记录，请等待审核结果后再上传')
        pending = latest_pending_version('inspection', inspection.id)
        if pending and pending.review_status == REVIEW_PENDING:
            raise ServiceError('该任务已有「待审核」版本（版本 %d），请等待审核结果后再上传' % pending.version_no)
    else:
        if task.status not in (TASK_RUNNING, TASK_RETURNED, TASK_PENDING, TASK_DONE):
            raise ServiceError('任务「%s」状态不能创建巡检记录' % task.status)
        # 巡检人员优先取任务指派工程师（管理员代传时记录真实执行人，上传者由版本留档）
        assignee = task.assignee_rel
        if assignee:
            inspector_name = assignee.realname or assignee.username or current_user_name
            inspector_user_id = task.assigned_to_user_id or current_user_id
        else:
            inspector_name = current_user_name
            inspector_user_id = current_user_id
        inspection = Inspection(
            title=task.title,
            customer_id=task.customer_id,
            task_id=task.id,
            inspection_date=datetime.utcnow().date(),
            inspector_name=inspector_name,
            inspector=inspector_name,
            inspector_user_id=inspector_user_id,
            overall_status=REVIEW_PENDING,
            review_status=REVIEW_PENDING,
        )
        db.session.add(inspection)
        db.session.flush()

    submitter = db.session.get(User, current_user_id) if current_user_id else None
    reviewer_department_id = getattr(submitter, 'department_id', None)
    reviewer_submitter = submitter
    if task.assigned_to_user_id:
        assignee = db.session.get(User, task.assigned_to_user_id)
        reviewer_department_id = (
            getattr(assignee, 'department_id', None) or reviewer_department_id)
        reviewer_submitter = assignee or reviewer_submitter
    assigned_reviewer_id = resolve_inspection_reviewer(
        reviewer_id, submitter=reviewer_submitter, department_id=reviewer_department_id)

    version = add_version(
        'inspection', inspection.id,
        report_file=report_path,
        content={'conclusion': conclusion or '', 'remark': remark or ''},
        submitted_by_user_id=current_user_id,
        review_status=REVIEW_PENDING if submit_review else '',
        assigned_reviewer_id=assigned_reviewer_id,
    )
    inspection.submitted_report = report_path if report_path else inspection.submitted_report
    inspection.review_status = REVIEW_PENDING
    inspection.reviewer_id = assigned_reviewer_id
    inspection.overall_status = REVIEW_PENDING
    inspection.conclusion = conclusion or ''

    asset_result = _sync_submission_assets(
        version, task, report_path, report_skip_reason,
        config_zip_path, config_zip_file_name, config_zip_device_id, config_zip_skip_reason,
        config_texts or [], config_text_skip_reason,
        topology_file_path, topology_file_name, topology_skip_reason,
        asset_list_path, asset_list_file_name, asset_list_skip_reason,
        current_user_name, add_asset)

    if submit_review:
        _sync_task_to_reviewing(inspection)
    return inspection, version, asset_result


@transaction
def supplement_report_assets_for_task(
        task_id, current_user_id, current_user_name, force=False,
        report_path='', conclusion='', remark='',
        config_zip_path='', config_zip_file_name='', config_zip_device_id=None,
        config_texts=None, topology_file_path='', topology_file_name='',
        asset_list_path='', asset_list_file_name=''):
    """向任务最近一次巡检提交版本补充资料，不重复提交审核、不改变任务状态。

    补传资料属于原提交版本的一部分：待审核期间可把漏传的配置/资产表补齐；
    已审核记录也允许补档，但所有新增附件均保留独立 ``created_at`` 并由路由写审计。
    退回修改后的重新提交仍走 :func:`upload_report_for_task`，创建新版本。
    """
    from .submission_version_service import add_asset

    task = InspectionTask.query.get_or_404(task_id)
    if task.status not in (TASK_RUNNING, TASK_RETURNED, TASK_REVIEWING, TASK_PENDING, TASK_DONE):
        raise ServiceError('任务状态「%s」不允许补传资料' % task.status)
    if not force and task.assigned_to_user_id and current_user_id \
            and int(task.assigned_to_user_id) != int(current_user_id):
        raise ServiceError('只有该任务指派工程师或管理员可以补传资料')

    inspection = Inspection.query.filter_by(task_id=task.id).first()
    if not inspection:
        raise ServiceError('该任务尚未提交巡检报告，请先完成首次提交')
    version = SubmissionVersion.query \
        .filter_by(entity_type='inspection', entity_id=inspection.id) \
        .order_by(SubmissionVersion.version_no.desc()).first()
    if not version:
        raise ServiceError('该巡检记录没有可补传的提交版本')

    config_texts = config_texts or []
    if not any((report_path, config_zip_path, config_texts,
                topology_file_path, asset_list_path)):
        raise ServiceError('请至少选择一项需要补传的文件或配置内容')

    if report_path:
        inspection.submitted_report = report_path
        if not version.report_file:
            version.report_file = report_path
    if conclusion:
        inspection.conclusion = conclusion
    if conclusion or remark:
        content = parse_json(version.content_json, {}, 'submission_versions.content_json')
        if not isinstance(content, dict):
            content = {}
        supplements = content.get('supplements')
        if not isinstance(supplements, list):
            supplements = []
        supplements.append({
            'submitted_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'submitted_by': current_user_name,
            'conclusion': conclusion or '',
            'remark': remark or '',
        })
        content['supplements'] = supplements
        version.content_json = dumps_json(content)

    asset_result = _sync_submission_assets(
        version, task, report_path, '',
        config_zip_path, config_zip_file_name, config_zip_device_id, '',
        config_texts, '',
        topology_file_path, topology_file_name, '',
        asset_list_path, asset_list_file_name, '',
        current_user_name, add_asset)
    return inspection, version, asset_result


def get_task_required_assets(task):
    """任务提交必传配置：按任务模板 required_assets_json，无模板/无效回退默认（仅报告必传）"""
    from utils.json_fields import parse_json
    defaults = {'report': True, 'config_zip': False, 'config_text': False,
                'topology': False, 'asset_list': False}
    tpl = task.task_template_rel if task.task_template_id else None
    if not tpl:
        return defaults
    cfg = parse_json(tpl.required_assets_json, {}, 'inspection_task_templates.required_assets_json')
    if not isinstance(cfg, dict):
        return defaults
    out = dict(defaults)
    for k in defaults:
        if k in cfg:
            out[k] = bool(cfg[k])
    return out


def _check_required_assets(task, **kwargs):
    """必传项校验：必传项缺文件且未填豁免原因 → 拒绝提交"""
    required = get_task_required_assets(task)
    has = {
        'report': bool(kwargs.get('report_path')) or bool(kwargs.get('report_skip_reason')),
        'config_zip': bool(kwargs.get('config_zip_path')) or bool(kwargs.get('config_zip_skip_reason')),
        'config_text': bool(kwargs.get('config_texts')) or bool(kwargs.get('config_text_skip_reason')),
        'topology': bool(kwargs.get('topology_file_path')) or bool(kwargs.get('topology_skip_reason')),
        'asset_list': bool(kwargs.get('asset_list_path')) or bool(kwargs.get('asset_list_skip_reason')),
    }
    labels = {'report': '巡检报告', 'config_zip': '完整配置备份包', 'config_text': '核心设备文本配置',
              'topology': '拓扑图', 'asset_list': '资产清单'}
    for key, must in required.items():
        if must and not has.get(key):
            raise ServiceError('必传项「%s」未上传，请上传或填写无法上传的原因' % labels.get(key, key))


def _sync_submission_assets(version, task, report_path, report_skip_reason,
                            config_zip_path, config_zip_file_name,
                            config_zip_device_id, config_zip_skip_reason,
                            config_texts, config_text_skip_reason,
                            topology_file_path, topology_file_name, topology_skip_reason,
                            asset_list_path, asset_list_file_name, asset_list_skip_reason,
                            operator_name, add_asset):
    """写 submission_assets 明细 + 同步 DeviceConfigBackup / Topology，返回汇总"""
    from models import Device, DeviceConfigBackup, Topology as _Topology
    import hashlib

    result = {'config_backups': 0, 'topologies': 0, 'assets': 0, 'skipped': []}

    # 巡检报告
    if report_path:
        add_asset(version.id, 'report', file_path=report_path)
        result['assets'] += 1
    elif report_skip_reason:
        add_asset(version.id, 'report', skip_reason=report_skip_reason)
        result['skipped'].append(('巡检报告', report_skip_reason))

    created_by = '%s / 版本%d' % (operator_name, version.version_no)

    # 完整配置备份包
    if config_zip_path:
        cid = None
        if config_zip_device_id:
            try:
                cid = int(config_zip_device_id)
            except (TypeError, ValueError):
                cid = None
        if cid:
            device = db.session.get(Device, cid)
            if not device or device.customer_id != task.customer_id:
                raise ServiceError('配置备份所选设备不属于当前巡检客户')
            backup = DeviceConfigBackup(
                device_id=cid,
                backup_type='全部配置',
                backup_method='巡检上传',
                config_content='（完整配置备份包，见附件文件）',
                file_path=config_zip_path,
                backup_date=datetime.utcnow().date(),
                created_by=created_by,
            )
            db.session.add(backup)
            db.session.flush()
            target_id = backup.id
            result['config_backups'] += 1
        else:
            target_id = None
        add_asset(version.id, 'config_zip', file_path=config_zip_path,
                  file_name=config_zip_file_name, device_id=cid, target_id=target_id)
        result['assets'] += 1
    elif config_zip_skip_reason:
        add_asset(version.id, 'config_zip', skip_reason=config_zip_skip_reason)
        result['skipped'].append(('完整配置备份包', config_zip_skip_reason))

    # 核心设备文本配置（每条同步 DeviceConfigBackup，可在线查看）
    if config_texts:
        for ct in config_texts:
            try:
                dev_id = int(ct.get('device_id')) if ct.get('device_id') else None
            except (TypeError, ValueError):
                dev_id = None
            content = ct.get('content') or ''
            fpath = ct.get('file_path') or ''
            fname = ct.get('file_name') or ''
            display_name = str(ct.get('name') or fname or '').strip()[:256]
            backup = None
            if dev_id:
                device = db.session.get(Device, dev_id)
                if not device or device.customer_id != task.customer_id:
                    raise ServiceError('文本配置所选设备不属于当前巡检客户')
                if not display_name:
                    display_name = device.device_name or ''
                backup = DeviceConfigBackup(
                    device_id=dev_id,
                    backup_type='运行配置',
                    backup_method='巡检上传',
                    config_content=content or '（文本配置见附件）',
                    file_path=fpath,
                    backup_date=datetime.utcnow().date(),
                    checksum=hashlib.md5((content or '').encode('utf-8')).hexdigest() if content else '',
                    created_by=created_by,
                )
                db.session.add(backup)
                db.session.flush()
                result['config_backups'] += 1
            if not display_name:
                raise ServiceError('核心设备文本配置必须填写配置名称或关联设备')
            add_asset(version.id, 'config_text', file_path=fpath, file_name=display_name,
                 device_id=dev_id, content_text=content,
                 target_id=backup.id if backup else None)
            result['assets'] += 1
    elif config_text_skip_reason:
        add_asset(version.id, 'config_text', skip_reason=config_text_skip_reason)
        result['skipped'].append(('核心设备文本配置', config_text_skip_reason))

    # 拓扑图 → Topology（按客户，拓扑页自动可见）
    if topology_file_path:
        from datetime import date as _date
        cust = task.customer_rel
        cust_name = cust.name if cust else '未命名客户'
        ext = (topology_file_path or '').rsplit('.', 1)[-1].lower() if '.' in (topology_file_path or '') else 'other'
        file_type = 'image' if ext in ('png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp') else (
            'pdf' if ext == 'pdf' else 'drawio' if ext in ('drawio', 'xml') else 'other')
        topo = _Topology(
            customer_id=task.customer_id,
            name='%s巡检拓扑 %s' % (cust_name, _date.today().strftime('%Y-%m-%d')),
            description='由巡检任务 #%d 提交资料同步' % task.id,
            file_path=topology_file_path,
            file_type=file_type,
            source='upload',
            upload_by=operator_name,
        )
        db.session.add(topo)
        db.session.flush()
        add_asset(version.id, 'topology', file_path=topology_file_path,
             file_name=topology_file_name, target_id=topo.id)
        result['topologies'] += 1
        result['assets'] += 1
    elif topology_skip_reason:
        add_asset(version.id, 'topology', skip_reason=topology_skip_reason)
        result['skipped'].append(('拓扑图', topology_skip_reason))

    # 资产清单（文件留档；设备解析导入已在调用方完成）
    if asset_list_path:
        add_asset(version.id, 'asset_list', file_path=asset_list_path, file_name=asset_list_file_name)
        result['assets'] += 1
    elif asset_list_skip_reason:
        add_asset(version.id, 'asset_list', skip_reason=asset_list_skip_reason)
        result['skipped'].append(('资产清单', asset_list_skip_reason))

    return result


@transaction
def submit_for_review(inspection_id, current_user_name, reviewer_id=None,
                      current_user_id=None, department_id=None):
    """提交审核 — V21: review_status='待审核' + 任务同步「待审核」"""
    from utils.json_fields import parse_json
    i = Inspection.query.get_or_404(inspection_id)
    if i.review_status == REVIEW_PENDING:
        raise ServiceError('该记录已处于待审核，请等待审核结果')
    has_content = bool(parse_json(i.content_json, [], 'inspection.content_json'))
    if not i.submitted_report and not has_content:
        raise ServiceError('请先上传巡检报告再提交审核')
    submitter = db.session.get(User, current_user_id) if current_user_id else User.query.filter(
        (User.username == current_user_name) | (User.realname == current_user_name)).first()
    effective_department_id = department_id or getattr(submitter, 'department_id', None)
    if i.inspector_user_id:
        inspector_user = db.session.get(User, i.inspector_user_id)
        effective_department_id = (
            getattr(inspector_user, 'department_id', None) or effective_department_id)
        submitter = inspector_user or submitter
    i.reviewer_id = resolve_inspection_reviewer(
        reviewer_id, submitter=submitter, department_id=effective_department_id)
    pending = latest_pending_version('inspection', i.id)
    if pending:
        pending.assigned_reviewer_id = i.reviewer_id
    i.overall_status = REVIEW_PENDING
    i.review_status = REVIEW_PENDING
    _sync_task_to_reviewing(i)
    return i


@transaction
def review_inspection(inspection_id, approved, current_user_name, remark='', requirements='',
                      checklist=None, reviewer_user_id=None):
    """审核巡检 — V21/V23: 审核结果/意见/修改要求/检查项勾选写回最新待审核版本 + 任务联动。

    审核通过 (approved=True):
        - review_status = '已通过'，overall_status = '正常'
        - 仅在 ITSM_AUTO_GENERATE_INSPECTION_REPORT 开启时生成正式 Word 报告
        - 关联任务「待审核 → 已完成」（保留提交时冻结的 actual_end）
    审核退回修改 (approved=False):
        - review_status = '已退回'，overall_status = '异常'
        - 退回原因 remark + 需要修改的内容 requirements 写回版本；
          requirements 为空时由「需修改」检查项自动拼装（"请完善：×××、×××"）
        - 关联任务「待审核 → 退回修改」，工程师按修改要求重传
    """
    from models import User as _User
    i = Inspection.query.get_or_404(inspection_id)
    if i.review_status != REVIEW_PENDING:
        raise ServiceError('该记录不处于待审核状态，无法审核')

    reviewer = (db.session.get(_User, reviewer_user_id) if reviewer_user_id else
                _User.query.filter(
                    (_User.username == current_user_name) |
                    (_User.realname == current_user_name)).first())
    if i.reviewer_id and (
            not reviewer or (reviewer.id != i.reviewer_id and not reviewer.is_admin)):
        raise ServiceError('该巡检记录已指派给其他审核人')

    if not approved and not requirements and checklist:
        need_fix = [name for name, st in checklist.items() if st == '需修改']
        if need_fix:
            requirements = '请完善：%s' % '、'.join(need_fix)
    if not approved and not str(remark or '').strip() and not str(requirements or '').strip():
        raise ServiceError('审核退回必须填写退回原因或修改要求')

    pending = latest_pending_version('inspection', i.id)
    if pending:
        review_version(pending.id, approved,
                       reviewer_user_id=reviewer.id if reviewer else None,
                       comment=remark, requirements=requirements, checklist=checklist)

    i.review_status = REVIEW_APPROVED if approved else REVIEW_REJECTED
    i.overall_status = '正常' if approved else '异常'
    i.reviewed_by = reviewer.id if reviewer else None
    i.reviewed_at = datetime.utcnow()
    if remark:
        i.review_comment = remark

    task = _task_from_inspection(i)
    if approved:
        if task and task.status == TASK_REVIEWING:
            apply_task_status(task, TASK_DONE, allow_review_complete=True)
        if current_app.config.get('AUTO_GENERATE_INSPECTION_REPORT'):
            try:
                _generate_report_for_inspection(i)
                if not i.report_file:
                    raise RuntimeError('报告生成器返回为空路径')
            except Exception as e:
                # 报告生成失败不阻塞审核通过，但必须可发现；路由层补审计/通知。
                try:
                    current_app.logger.exception(
                        '生成巡检报告失败 inspection_id=%s: %s', i.id, e)
                except Exception:
                    pass
    else:
        _return_task_for_revision(i)
    return i


def _generate_report_for_inspection(inspection):
    """V11: 调用 generate_inspection_report_v4 生成 Word 文档（函数内部已保存到 reports/ 目录），把文件名写入 inspection.report_file"""
    from utils.report_generator import generate_inspection_report_v4
    from models import Customer

    cust = Customer.query.get(inspection.customer_id) if inspection.customer_id else None
    customer_name = cust.name if cust else '未知客户'

    # 解析 sections_json
    sections = parse_json(
        inspection.sections_json,
        default={},
        field_name='inspection.sections_json',
    )
    if not isinstance(sections, dict):
        sections = {}

    # 调用生成器，它会保存到 reports/<filename>.docx 并返回完整路径
    fpath = generate_inspection_report_v4(inspection, customer_name, device_results=None, sections=sections)
    if not fpath:
        return None
    fname = os.path.basename(fpath) if isinstance(fpath, str) else None
    if fname:
        inspection.report_file = fname
    return fname


@transaction
def delete_inspection(inspection_id):
    """删除巡检记录；关联任务仍「待审核」且无其他待审核记录时任务回「执行中」。"""
    from models import SubmissionVersion
    i = Inspection.query.get_or_404(inspection_id)
    task = _task_from_inspection(i)
    if task and task.status == TASK_REVIEWING:
        apply_task_status(task, TASK_RUNNING)
    SubmissionVersion.query.filter_by(entity_type='inspection', entity_id=i.id).delete()
    db.session.delete(i)
