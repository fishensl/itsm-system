# -*- coding: utf-8 -*-
"""任务安排批量导入（SSR 与 Vue 共用）

从 blueprints/task_schedule.import_excel 抽取为公共服务函数；
SSR 视图与 Vue API 均调用本函数，保证行为一致。
"""
import re
from datetime import datetime, timezone, timedelta, date

from flask import current_app

from models import db, User, Customer, InspectionTask
from utils.constants import (
    REVIEW_APPROVED,
    TASK_CANCELLED,
    TASK_CONTRACT_REVIEW,
    TASK_DONE,
    TASK_PENDING,
    TASK_RUNNING,
    TASK_STATUSES,
    TASK_TRANSITIONS,
)

_BEIJING = timezone(timedelta(hours=8))


def local_now():
    """当前北京本地时间（naive）。"""
    return datetime.now(_BEIJING).replace(tzinfo=None)


STATUS_FROM_EXCEL = {
    '未开始': TASK_PENDING, TASK_PENDING: TASK_PENDING,
    '进行中': TASK_RUNNING, TASK_RUNNING: TASK_RUNNING,
    TASK_DONE: TASK_DONE, '完成': TASK_DONE,
    TASK_CANCELLED: TASK_CANCELLED, '取消': TASK_CANCELLED,
}
PRIORITY_VALUES = {'低', '中', '高', '紧急'}
ALLOWED_EXCEL_EXT = {'.xlsx', '.xls'}

_CUSTOMER_SUFFIX_RE = re.compile(r'\s*[\d]{4}年.*$')


def extract_customer_name(title):
    """从任务标题里提取客户名（去掉 yyyy年... 后缀）"""
    if not title:
        return ''
    return _CUSTOMER_SUFFIX_RE.sub('', str(title).strip()).strip()


def parse_excel_date(v):
    """Excel cell value -> date | None"""
    if v is None or v == '':
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y年%m月%d日'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_excel_datetime(v):
    """Excel cell value -> datetime | None"""
    if v is None or v == '':
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime.combine(v, datetime.min.time())
    d = parse_excel_date(v)
    return datetime.combine(d, datetime.min.time()) if d else None


def _parse_effort(v):
    """预估工作量 cell -> float(人天) | None"""
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return float(v) if v >= 0 else None
    s = str(v).strip()
    if not s:
        return None
    s = re.sub(r'(人天|天|日|days?|d)\s*$', '', s, flags=re.IGNORECASE).strip()
    try:
        return float(s) if float(s) >= 0 else None
    except ValueError:
        return None


def import_task_excel(file_storage, user):
    """批量导入"成员分工安排表"（upsert by (title, customer_id)）

    Args:
        file_storage: Flask request.files 文件对象
        user: 操作人（current_user）
    Returns:
        {created, updated, skipped, skip_reasons, new_customer_names}
    Raises:
        ValueError: 文件/表头/数据校验失败
    """
    from utils.upload import (validate_upload, save_temp_upload,
                              open_excel, cleanup_temp_file)

    ok_flag, err, _ = validate_upload(file_storage, ALLOWED_EXCEL_EXT, max_size_mb=5)
    if not ok_flag:
        raise ValueError(err)

    tmp = save_temp_upload(file_storage, suffix='.xlsx')
    try:
        wb, ws, err = open_excel(tmp, app=current_app)
        if err:
            raise ValueError(err[0] if isinstance(err, (list, tuple)) else str(err))

        header = [c.value for c in ws[1]]
        col = {}
        for i, h in enumerate(header):
            if h:
                col[str(h).strip()] = i

        required = ['任务描述', '负责人']
        miss = [h for h in required if h not in col]
        if miss:
            raise ValueError('Excel 缺少必需列：' + '、'.join(miss))

        created = 0
        updated = 0
        skipped = 0
        skip_reasons = []
        new_customer_names = []

        user_by_name = {}
        for u in User.query.filter(User.is_active == True).all():  # noqa: E712
            key = (u.realname or '').strip() or u.username
            if key:
                user_by_name[key] = u

        for r in range(2, ws.max_row + 1):
            def cell(name):
                idx = col.get(name)
                if idx is None:
                    return None
                return ws.cell(r, idx + 1).value

            title = str(cell('任务描述') or '').strip()
            if not title:
                continue

            owner_name = str(cell('负责人') or '').strip()
            if not owner_name:
                skipped += 1
                skip_reasons.append(f'第{r}行：负责人为空')
                continue
            assignee = user_by_name.get(owner_name)
            if not assignee:
                skipped += 1
                skip_reasons.append(f'第{r}行：找不到负责人 "{owner_name}"')
                continue

            customer_name = str(cell('客户名称') or '').strip() or extract_customer_name(title)
            if not customer_name:
                skipped += 1
                skip_reasons.append(f'第{r}行：无法从「客户名称」列或标题中识别客户')
                continue
            customer = Customer.query.filter_by(name=customer_name).first()
            if not customer:
                customer = Customer(name=customer_name)
                db.session.add(customer)
                db.session.flush()
                new_customer_names.append(customer_name)

            raw_status = str(cell('完成状态') or '').strip()
            status = STATUS_FROM_EXCEL.get(raw_status, TASK_PENDING)
            raw_priority = str(cell('优先级') or '').strip()
            priority = raw_priority if raw_priority in PRIORITY_VALUES else '中'

            planned_start = parse_excel_date(cell('开始日期'))
            planned_end = parse_excel_date(cell('完成日期'))
            actual_end = parse_excel_datetime(cell('完成时间'))
            effort = _parse_effort(cell('预估工作量'))
            actual_effort = _parse_effort(cell('实际工作量'))

            existing = (InspectionTask.query
                        .filter_by(title=title, customer_id=customer.id)
                        .first())
            if existing:
                existing.status = status
                existing.priority = priority
                existing.assigned_to_user_id = assignee.id
                existing.planned_start = planned_start or existing.planned_start
                existing.planned_end = planned_end or existing.planned_end
                if actual_end:
                    existing.actual_end = actual_end
                if status == TASK_DONE and not existing.actual_end:
                    existing.actual_end = local_now()
                if effort is not None:
                    existing.estimated_effort = effort
                if actual_effort is not None:
                    existing.actual_effort = actual_effort
                existing.dispatched_by = existing.dispatched_by or user.id
                existing.dispatched_at = existing.dispatched_at or datetime.utcnow()
                updated += 1
            else:
                task = InspectionTask(
                    title=title,
                    task_type='计划',
                    status=status,
                    priority=priority,
                    customer_id=customer.id,
                    planned_start=planned_start,
                    planned_end=planned_end,
                    actual_end=actual_end,
                    estimated_effort=effort,
                    actual_effort=actual_effort,
                    assigned_to_user_id=assignee.id,
                    dispatched_by=user.id,
                    dispatched_at=datetime.utcnow(),
                    source='Excel导入',
                    template_category='巡检',
                    created_by=(user.realname or user.username),
                )
                db.session.add(task)
                created += 1

        db.session.commit()
        return {
            'created': created, 'updated': updated, 'skipped': skipped,
            'skip_reasons': skip_reasons, 'new_customer_names': new_customer_names,
        }
    finally:
        cleanup_temp_file(tmp)


def check_task_transition(task, new_status, allow_reopen=False, allow_contract_review=False):
    """任务状态机校验（SSR 看板 / Vue 看板共用）。

    - 合法转换见 utils.constants.TASK_TRANSITIONS；
    - 兼容老流程：无关联巡检记录的手工任务允许直接完成/取消；
    - 已有巡检记录的任务必须存在"已通过"记录才能置为已完成
      （审核通过后才完成，对应"上传报告→审核闭环"）。
    - allow_reopen=True：已完成/已取消 → 执行中 的纠正性重开（调用端做权限+审计）。
    返回错误文案；None 表示允许。
    """
    if new_status not in TASK_STATUSES:
        return '非法状态：%s' % new_status
    if new_status == task.status:
        return None
    if task.status == TASK_CONTRACT_REVIEW and not allow_contract_review:
        return '合同审批任务只能通过合同例外审核接口流转'
    allowed = TASK_TRANSITIONS.get(task.status, set())
    if new_status in allowed:
        if new_status == TASK_DONE and task.records:
            if not any(r.review_status == REVIEW_APPROVED for r in task.records):
                return '该任务已有巡检记录，请先上传报告并通过审核后再完成任务'
        return None
    # 重开：已完成/已取消的任务允许重新置为「执行中」（误标完成/取消的纠正出口）。
    # 该转换不在 TASK_TRANSITIONS 表内，仅 allow_reopen=True 的受控入口可达。
    if allow_reopen and task.status in (TASK_DONE, TASK_CANCELLED) and new_status == TASK_RUNNING:
        return None
    # 兼容：无关联记录的手工任务允许直接完成/取消（老流程不阻断）
    if new_status in (TASK_DONE, TASK_CANCELLED) and not task.records:
        return None
    return '不允许从「%s」变更为「%s」' % (task.status, new_status)


def apply_task_status(task, new_status, allow_reopen=False, allow_contract_review=False):
    """改任务状态 + 状态机校验 + 自动维护 actual_start/actual_end。

    与 blueprints/task_schedule._apply_status 行为一致，供 Vue API 复用；
    校验失败抛 ValueError。allow_reopen 语义见 check_task_transition。
    """
    err = check_task_transition(
        task, new_status, allow_reopen=allow_reopen,
        allow_contract_review=allow_contract_review)
    if err:
        raise ValueError(err)
    now = local_now()
    task.status = new_status
    if new_status == TASK_RUNNING and not task.actual_start:
        task.actual_start = now
    if new_status == TASK_DONE and not task.actual_end:
        task.actual_end = now
    # 重开（终态→执行中）：清空完成时间戳，重新计时
    if new_status == TASK_RUNNING and task.actual_end:
        task.actual_end = None
    return task


def review_task_contract_exception(task, approved, reviewer_name, comment=''):
    """审核过期客户任务的合同例外申请。"""
    if task.status != TASK_CONTRACT_REVIEW:
        raise ValueError(f'任务当前状态「{task.status}」不能进行合同例外审核')
    target = TASK_PENDING if approved else TASK_CANCELLED
    apply_task_status(task, target, allow_contract_review=True)
    task.contract_exception_status = '通过' if approved else '拒绝'
    note = (comment or '').strip()
    if note:
        current = (task.contract_exception_reason or '').rstrip()
        task.contract_exception_reason = f'{current}\n审核意见：{note}' if current else f'审核意见：{note}'
    current_app.logger.info(
        '任务合同例外审核: task_id=%s approved=%s reviewer=%s',
        task.id, approved, reviewer_name)
    return task
