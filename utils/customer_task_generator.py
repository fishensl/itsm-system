# -*- coding: utf-8 -*-
"""客户巡检频率 → 任务懒生成（V17）

区别于 utils/auto_task_generator.py（基于合同的自动生成），本模块基于
Customer.inspection_frequency 字段，在每次打开任务安排看板时补齐
"当年应有但尚未生成"的巡检计划任务。

策略：
  - 触发：task_schedule.index() 入口调用 generate_for_all_customers()
  - 同日短路：customer.last_generated_date == today 则跳过该客户
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


def _period_label(d, months):
    """期次标签：每月→'3月'，每季度→'第1季度'，每半年→'上半年'，每年→'年度'"""
    if months == 1:
        return f'{d.month}月'
    if months == 3:
        return f'第{(d.month - 1) // 3 + 1}季度'
    if months == 6:
        return '上半年' if d.month <= 6 else '下半年'
    return '年度'


def generate_for_all_customers(today=None):
    """页面入口懒触发；返回新建任务数。同日已生成过的客户短路。

    失败不抛异常（调用方已用 try/except 包裹，但内部 commit 也单独兜底），
    避免影响看板渲染。
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
    touched = False
    for c in customers:
        # 同日已处理过的客户短路（避免每次刷新都遍历全部期次）
        if c.last_generated_date == today:
            continue
        months = _get_frequency_delta(c.inspection_frequency)
        if not months:
            # 频率值无法识别：标记今日已处理，避免反复告警
            c.last_generated_date = today
            touched = True
            continue

        # 从年初开始按频率步进；当年已过去的期次也补齐（回填历史，幂等）
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

        # 记录最后一个已生成期次起点；若没有期次落在本年则记今日
        c.last_generated_date = last_period or today
        touched = True

    if not touched:
        return 0
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('客户频率懒生成 commit 失败')
        return 0
    return created
