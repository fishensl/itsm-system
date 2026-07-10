# -*- coding: utf-8 -*-
"""客户巡检频率 → 任务生成（V17 → 2026-06-26 改为新增客户时触发）

区别于 utils/auto_task_generator.py（基于合同的自动生成），本模块基于
Customer.inspection_frequency 字段，在新增客户时一次性生成本年度的全部巡检计划任务。

策略：
  - 触发：blueprints.customer.customer_add() 创建客户后立即调用 generate_for_customer(c.id)
  - 范围：从当年 1/1 到 12/31，按频率步进；已过期期次也补齐（回填历史，幂等）
  - 防重：(customer_id, source, planned_start) 已存在则跳过
  - 产物：source='客户频率自动'、template_category='巡检'、status='待执行'、未指派

复用 utils.auto_task_generator 的 _get_frequency_delta / _add_months。
"""
from datetime import date, timedelta

from flask import current_app

from models import db, Customer, InspectionTask
from utils.auto_task_generator import _get_frequency_delta, _add_months


SOURCE_TAG = '客户频率自动'

# 季度阿拉伯数字 → 中文，用于标题「第二季度」而非「第2季度」
QUARTER_CN = {1: '一', 2: '二', 3: '三', 4: '四'}


def _period_label(d, months):
    """期次标签：每月→'3月'，每季度→'第二季度'，每半年→'上半年'，每年→'年度'"""
    if months == 1:
        return f'{d.month}月'
    if months == 3:
        return f'第{QUARTER_CN[(d.month - 1) // 3 + 1]}季度'
    if months == 6:
        return '上半年' if d.month <= 6 else '下半年'
    return '年度'


def _generate_for_customer_in_session(c, today, year_start, year_end, existing):
    """为单个客户生成本年度任务（不 commit；调用方负责事务）。

    existing: {(customer_id, planned_start)} 集合，会被原地更新。
    Returns: 新建任务数。
    """
    if not c.inspection_frequency:
        return 0
    months = _get_frequency_delta(c.inspection_frequency)
    if not months:
        # 频率值无法识别：标记今日已处理，避免反复告警
        c.last_generated_date = today
        return 0

    created = 0
    cursor = year_start
    last_period = None
    while cursor <= year_end:
        if (c.id, cursor) not in existing:
            task_end = _add_months(cursor, months) - timedelta(days=1)
            if task_end > year_end:
                task_end = year_end
            db.session.add(InspectionTask(
                title=f'{c.name}{cursor.year}年{_period_label(cursor, months)}巡检',
                task_type='计划',
                status='待执行',
                customer_id=c.id,
                planned_start=cursor,
                planned_end=task_end,
                priority='中',
                source=SOURCE_TAG,
                template_category='巡检',
                created_by='系统-客户频率',
                remark=f'根据客户巡检频率「{c.inspection_frequency}」自动生成',
            ))
            existing.add((c.id, cursor))
            created += 1
        last_period = cursor
        cursor = _add_months(cursor, months)
    c.last_generated_date = last_period or today
    return created


def generate_for_customer(customer_id, today=None):
    """新增客户时调用：仅为该客户生成本年度的全部期次任务。

    返回新建任务数；commit 在此函数内完成。失败抛异常由调用方处理。
    """
    today = today or date.today()
    year_start = date(today.year, 1, 1)
    year_end = date(today.year, 12, 31)
    c = Customer.query.get(customer_id)
    if not c or not c.inspection_frequency:
        return 0
    existing = {(t.customer_id, t.planned_start) for t in
                InspectionTask.query
                .filter(InspectionTask.source == SOURCE_TAG,
                        InspectionTask.customer_id == c.id,
                        InspectionTask.planned_start >= year_start,
                        InspectionTask.planned_start <= year_end)
                .all()}
    created = _generate_for_customer_in_session(c, today, year_start, year_end, existing)
    try:
        db.session.commit()
        return created
    except Exception:
        db.session.rollback()
        current_app.logger.exception('客户 %s 频率任务生成 commit 失败', customer_id)
        return 0


def generate_for_all_customers(today=None):
    """为全部带巡检频率的客户回填本年度任务（管理后台「重新生成」用）。

    返回新建任务数。失败不抛异常（避免阻塞调用方）。
    """
    today = today or date.today()
    year_start = date(today.year, 1, 1)
    year_end = date(today.year, 12, 31)

    customers = (Customer.query
                 .filter(Customer.inspection_frequency.isnot(None),
                         Customer.inspection_frequency != '')
                 .all())
    if not customers:
        return 0

    # 一次性预取本年所有客户频率自动任务，避免 N+1 循环查询
    existing = {(t.customer_id, t.planned_start) for t in
                InspectionTask.query
                .filter(InspectionTask.source == SOURCE_TAG,
                        InspectionTask.planned_start >= year_start,
                        InspectionTask.planned_start <= year_end)
                .all()}

    created = 0
    for c in customers:
        created += _generate_for_customer_in_session(c, today, year_start, year_end, existing)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('客户频率任务回填 commit 失败')
        return 0
    return created
