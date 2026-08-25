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
    TASK_SCHEDULED,
    TASK_REVIEWING,
    TASK_RUNNING,
    TASK_STATUSES,
    TASK_TRANSITIONS,
)

_BEIJING = timezone(timedelta(hours=8))


def local_now():
    """当前北京本地时间（naive）。"""
    return datetime.now(_BEIJING).replace(tzinfo=None)


_ACTIVE_TIMING_STATUSES = frozenset({TASK_RUNNING, TASK_REVIEWING})
_SECONDS_PER_PERSON_DAY = 8 * 60 * 60


def task_actual_duration_seconds(task, now=None):
    """Return elapsed wall-clock seconds from first execution to final approval.

    Running/reviewing tasks are calculated up to ``now``. Completed tasks use
    their frozen ``actual_end``. Tasks without a reliable start/end boundary
    return ``None`` so historical manual effort can remain a fallback.
    """
    if not task.actual_start:
        return None
    end = task.actual_end
    if not end and task.status in _ACTIVE_TIMING_STATUSES:
        end = now or local_now()
    if not end:
        return None
    return max(0, int((end - task.actual_start).total_seconds()))


def format_task_duration(seconds):
    """Format elapsed seconds as an exact, human-readable hour/minute value."""
    if seconds is None:
        return ''
    if seconds < 60:
        return '<1分钟'
    total_minutes = int(seconds // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f'{hours}小时{minutes}分钟'
    if hours:
        return f'{hours}小时'
    return f'{minutes}分钟'


def task_actual_effort(task, now=None):
    """Actual person-days derived from elapsed time (8 hours/person-day)."""
    seconds = task_actual_duration_seconds(task, now=now)
    if seconds is None:
        return task.actual_effort
    return round(seconds / _SECONDS_PER_PERSON_DAY, 2)


def task_timing_payload(task, now=None):
    """Serialize the common actual-start/end/duration contract."""
    if not task:
        return {
            'actual_start': '', 'actual_end': '',
            'actual_duration_hours': None, 'actual_duration_text': '',
            'actual_effort': None,
        }
    seconds = task_actual_duration_seconds(task, now=now)
    return {
        'actual_start': (
            task.actual_start.strftime('%Y-%m-%d %H:%M')
            if task.actual_start else ''
        ),
        'actual_end': (
            task.actual_end.strftime('%Y-%m-%d %H:%M')
            if task.actual_end else ''
        ),
        'actual_duration_hours': (
            round(seconds / 3600, 2) if seconds is not None else None
        ),
        'actual_duration_text': format_task_duration(seconds),
        'actual_effort': task_actual_effort(task, now=now),
    }


def validate_task_schedule_period(task, status=None):
    """校验任务安排条件。

    普通状态允许历史数据缺少日期，但只要同时有起止日期就不能倒置；
    「已安排」语义上必须已明确负责人和完整起止日期。
    返回错误文案或 None。
    """
    target_status = status or task.status
    if task.planned_start and task.planned_end and task.planned_start > task.planned_end:
        return '安排开始日期不能晚于结束日期'
    if target_status == TASK_SCHEDULED and (
            not task.planned_start or not task.planned_end):
        return '变更为「已安排」前必须填写完整的安排开始和结束日期'
    if target_status == TASK_SCHEDULED and not task.assigned_to_user_id:
        return '变更为「已安排」前必须选择负责人'
    return None


STATUS_FROM_EXCEL = {
    '未开始': TASK_PENDING, TASK_PENDING: TASK_PENDING,
    TASK_SCHEDULED: TASK_SCHEDULED,
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

            def cell_any(*names):
                for name in names:
                    value = cell(name)
                    if value not in (None, ''):
                        return value
                return None

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

            planned_start = parse_excel_date(cell_any('计划开始日期', '开始日期'))
            planned_end = parse_excel_date(cell_any('计划完成日期', '完成日期'))
            actual_start = parse_excel_datetime(cell_any('实际开始时间', '开始时间'))
            actual_end = parse_excel_datetime(cell_any('实际完成时间', '完成时间'))
            effort = _parse_effort(cell_any('预估人天', '预估工作量'))
            actual_effort = _parse_effort(cell_any('实际人天', '实际工作量'))
            if planned_start and planned_end and planned_end < planned_start:
                raise ValueError(f'第{r}行：安排结束日期不能早于开始日期')
            if actual_start and actual_end and actual_end < actual_start:
                raise ValueError(f'第{r}行：实际完成时间不能早于实际开始时间')

            existing = (InspectionTask.query
                        .filter_by(title=title, customer_id=customer.id)
                        .first())
            if existing:
                effective_start = planned_start or existing.planned_start
                effective_end = planned_end or existing.planned_end
                if status == TASK_SCHEDULED and (not effective_start or not effective_end):
                    raise ValueError(f'第{r}行：「已安排」任务必须填写完整的安排日期')
                existing.status = status
                existing.priority = priority
                existing.assigned_to_user_id = assignee.id
                existing.planned_start = planned_start or existing.planned_start
                existing.planned_end = planned_end or existing.planned_end
                if actual_start:
                    existing.actual_start = actual_start
                if status in (TASK_RUNNING, TASK_REVIEWING) and not existing.actual_start:
                    existing.actual_start = local_now()
                if actual_end:
                    existing.actual_end = actual_end
                if status == TASK_DONE and not existing.actual_end:
                    existing.actual_end = local_now()
                if effort is not None:
                    existing.estimated_effort = effort
                if existing.actual_start and existing.actual_end:
                    existing.actual_effort = task_actual_effort(existing)
                elif actual_effort is not None:
                    existing.actual_effort = actual_effort
                existing.dispatched_by = existing.dispatched_by or user.id
                existing.dispatched_at = existing.dispatched_at or datetime.utcnow()
                updated += 1
            else:
                if status == TASK_SCHEDULED and (not planned_start or not planned_end):
                    raise ValueError(f'第{r}行：「已安排」任务必须填写完整的安排日期')
                if status in (TASK_RUNNING, TASK_REVIEWING) and not actual_start:
                    actual_start = local_now()
                if status == TASK_DONE and not actual_end:
                    actual_end = local_now()
                task = InspectionTask(
                    title=title,
                    task_type='计划',
                    status=status,
                    priority=priority,
                    customer_id=customer.id,
                    planned_start=planned_start,
                    planned_end=planned_end,
                    actual_start=actual_start,
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
                if task.actual_start and task.actual_end:
                    task.actual_effort = task_actual_effort(task)
                db.session.add(task)
                created += 1

        db.session.commit()
        return {
            'created': created, 'updated': updated, 'skipped': skipped,
            'skip_reasons': skip_reasons, 'new_customer_names': new_customer_names,
        }
    finally:
        cleanup_temp_file(tmp)


def check_task_transition(task, new_status, allow_reopen=False,
                          allow_contract_review=False, allow_review_complete=False):
    """任务状态机校验（SSR 看板 / Vue 看板共用）。

    - 合法转换见 utils.constants.TASK_TRANSITIONS；
    - 「已完成」只能由巡检记录审核通过产生，禁止手工跳过审核；
    - allow_reopen=True：已完成/已取消 → 执行中 的纠正性重开（调用端做权限+审计）。
    - allow_review_complete=True：仅供巡检审核通过的受控入口结束任务。
    返回错误文案；None 表示允许。
    """
    if new_status not in TASK_STATUSES:
        return '非法状态：%s' % new_status
    period_error = validate_task_schedule_period(task, new_status)
    if period_error:
        return period_error
    if new_status == task.status:
        return None
    if task.status == TASK_CONTRACT_REVIEW and not allow_contract_review:
        return '合同审批任务只能通过合同例外审核接口流转'
    if new_status == TASK_DONE and not allow_review_complete:
        return '已完成状态只能由巡检记录审核通过后自动生成'
    allowed = TASK_TRANSITIONS.get(task.status, set())
    if new_status in allowed:
        if new_status == TASK_DONE and not any(
                r.review_status == REVIEW_APPROVED for r in task.records):
            return '任务必须提交巡检记录并审核通过后才能完成'
        return None
    # 重开：已完成/已取消的任务允许重新置为「执行中」（误标完成/取消的纠正出口）。
    # 该转换不在 TASK_TRANSITIONS 表内，仅 allow_reopen=True 的受控入口可达。
    if allow_reopen and task.status in (TASK_DONE, TASK_CANCELLED) and new_status == TASK_RUNNING:
        return None
    # 无记录任务仍允许取消，但不允许绕过记录审核直接完成。
    if new_status == TASK_CANCELLED and not task.records:
        return None
    return '不允许从「%s」变更为「%s」' % (task.status, new_status)


def apply_task_status(task, new_status, allow_reopen=False,
                      allow_contract_review=False, allow_review_complete=False,
                      now=None):
    """改任务状态 + 状态机校验 + 自动维护 actual_start/actual_end。

    与 blueprints/task_schedule._apply_status 行为一致，供 Vue API 复用；
    校验失败抛 ValueError。各 allow_* 参数语义见 check_task_transition。
    """
    err = check_task_transition(
        task, new_status, allow_reopen=allow_reopen,
        allow_contract_review=allow_contract_review,
        allow_review_complete=allow_review_complete)
    if err:
        raise ValueError(err)
    now = now or local_now()
    previous_status = task.status
    if new_status == TASK_RUNNING:
        # 首次执行固定起点；纠正性重开保留原始起点，继续计算完整生命周期。
        if not task.actual_start:
            task.actual_start = now
        if previous_status in (TASK_DONE, TASK_CANCELLED):
            task.actual_end = None
            task.actual_effort = None
    elif new_status in (TASK_PENDING, TASK_SCHEDULED) and previous_status == TASK_RUNNING:
        # 执行中撤回到执行前阶段表示本轮重置：清空计时边界，
        # 下次再进入「执行中」时以新时间重新起算。
        task.actual_start = None
        task.actual_end = None
        task.actual_effort = None
    task.status = new_status
    if new_status == TASK_DONE:
        # 历史异常数据可能没有起点，用最早任务记录创建时间兜底；新流程
        # 始终已在进入执行中时记录 actual_start。
        if not task.actual_start:
            record_starts = [r.created_at for r in task.records if r.created_at]
            # Inspection.created_at 历史上以 UTC naive 存储；任务实际时间采用
            # 北京本地 naive，兜底时补 +08:00，避免旧数据平白多算 8 小时。
            task.actual_start = (
                min(record_starts) + timedelta(hours=8) if record_starts else now
            )
        if not task.actual_end:
            task.actual_end = now
        task.actual_effort = task_actual_effort(task, now=now)
    return task


def review_task_contract_exception(task, approved, reviewer_name, comment=''):
    """审核过期客户任务的合同例外申请。"""
    if task.status != TASK_CONTRACT_REVIEW:
        raise ValueError(f'任务当前状态「{task.status}」不能进行合同例外审核')
    target = (
        TASK_SCHEDULED
        if approved and task.assigned_to_user_id and task.planned_start and task.planned_end
        else TASK_PENDING
    ) if approved else TASK_CANCELLED
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
