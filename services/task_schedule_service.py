# -*- coding: utf-8 -*-
"""任务安排批量导入（SSR 与 Vue 共用）

从 blueprints/task_schedule.import_excel 抽取为公共服务函数；
SSR 视图与 Vue API 均调用本函数，保证行为一致。
"""
import re
from datetime import datetime, timezone, timedelta, date

from flask import current_app

from models import db, User, Customer, InspectionTask

_BEIJING = timezone(timedelta(hours=8))


def local_now():
    """当前北京本地时间（naive）。"""
    return datetime.now(_BEIJING).replace(tzinfo=None)


STATUS_FROM_EXCEL = {
    '未开始': '待执行', '待执行': '待执行', '进行中': '执行中', '执行中': '执行中',
    '已完成': '已完成', '完成': '已完成', '已取消': '已取消', '取消': '已取消',
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
            status = STATUS_FROM_EXCEL.get(raw_status, '待执行')
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
                if status == '已完成' and not existing.actual_end:
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
