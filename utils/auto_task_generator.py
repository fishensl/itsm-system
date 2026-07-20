"""合同自动巡检任务生成器"""
from datetime import date, timedelta
from flask import current_app
from models import db, Contract, InspectionTask, InspectionTemplate


def _get_frequency_delta(frequency):
    """获取频率对应的日期间隔"""
    # 使用简单的月份/天数计算，避免 dateutil 依赖
    deltas = {
        '每月': 1,      # 月数
        '每季度': 3,
        '每半年': 6,
        '每年': 12,
    }
    return deltas.get(frequency)


def _add_months(d, months):
    """给日期加上N个月"""
    new_month = d.month + months
    new_year = d.year + (new_month - 1) // 12
    new_month = (new_month - 1) % 12 + 1
    # 处理月末日期（如1月31日+1月=2月28日）
    import calendar
    max_day = calendar.monthrange(new_year, new_month)[1]
    new_day = min(d.day, max_day)
    return d.replace(year=new_year, month=new_month, day=new_day)


def generate_contract_tasks(contract_id=None, to_date=None, dry_run=False):
    """
    从启用自动巡检的合同中生成巡检任务。

    Args:
        contract_id: 指定合同ID，None则处理所有符合条件的合同
        to_date: 生成到该日期，None则到今天
        dry_run: True时只预览不入库

    Returns:
        生成的任务信息列表
    """
    if to_date is None:
        to_date = date.today()

    query = Contract.query.filter(
        Contract.inspection_frequency != '',
        Contract.inspection_frequency.isnot(None),
        Contract.auto_generate_tasks == True,
        Contract.status.in_(['执行中', '已签']),
    )
    if contract_id:
        query = query.filter(Contract.id == contract_id)

    contracts = query.all()
    generated = []

    for contract in contracts:
        # 模板解析：优先新任务模板 task_template_id，回退旧 inspection_template_id（迁移期兼容）
        template_name = None
        new_template_id = None
        if contract.task_template_id:
            from models import InspectionTaskTemplate
            tt = InspectionTaskTemplate.query.get(contract.task_template_id)
            if tt:
                template_name = tt.name
                new_template_id = tt.id
        if template_name is None:
            if not contract.inspection_template_id:
                continue
            template = InspectionTemplate.query.get(contract.inspection_template_id)
            if not template:
                continue
            template_name = template.name

        frequency = contract.inspection_frequency
        months = _get_frequency_delta(frequency)
        if not months:
            current_app.logger.warning(
                '合同 %s 巡检频率「%s」无法识别，跳过自动任务生成',
                contract.number or contract.id, frequency,
            )
            continue

        # 从上次生成日期或合同开始日期开始
        cursor = contract.last_generated_date or contract.start_date or date.today()

        # 如果游标在当前日期之前，需要生成
        if cursor >= to_date:
            continue

        # 确保游标不早于合同开始日期
        if contract.start_date and cursor < contract.start_date:
            cursor = contract.start_date

        last_period_start = None  # 最后一个已生成期次的起点，作为下次的游标
        while cursor <= to_date:
            # 不超过合同结束日期
            if contract.end_date and cursor > contract.end_date:
                break

            task_end = _add_months(cursor, months) - timedelta(days=1)

            # 不超过合同结束日期
            if contract.end_date and task_end > contract.end_date:
                task_end = contract.end_date

            # 检查是否已存在此期间的任务（防重复）
            existing = InspectionTask.query.filter(
                InspectionTask.contract_id == contract.id,
                InspectionTask.source == '合同自动生成',
                InspectionTask.planned_start == cursor,
            ).first()

            if not existing:
                task_title = f"{contract.title or contract.number} - {template_name} ({cursor.strftime('%Y-%m')})"

                task_info = {
                    'contract_id': contract.id,
                    'contract_title': contract.title or contract.number,
                    'task_start': cursor.isoformat(),
                    'task_end': task_end.isoformat(),
                    'frequency': frequency,
                    'customer_id': contract.customer_id,
                    'template_id': new_template_id or contract.inspection_template_id,
                    'title': task_title,
                }

                if not dry_run:
                    task = InspectionTask(
                        title=task_title,
                        task_type='计划',
                        status='待执行',
                        customer_id=contract.customer_id,
                        # 新链路写 task_template_id；未迁移的旧合同回退 legacy template_id
                        task_template_id=new_template_id,
                        template_id=None if new_template_id else contract.inspection_template_id,
                        planned_start=cursor,
                        planned_end=task_end,
                        priority='中',
                        created_by='系统自动生成',
                        contract_id=contract.id,
                        source='合同自动生成',
                        template_category='巡检',
                        remark=f'根据合同 {contract.number or contract.id} 自动生成，巡检频率：{frequency}',
                    )
                    db.session.add(task)

                generated.append(task_info)

            last_period_start = cursor
            cursor = _add_months(cursor, months)

        if not dry_run:
            # 记录为最后一个已生成期次的起点（而非 to_date），避免下次跳过尚未覆盖的周期
            if last_period_start is not None:
                contract.last_generated_date = last_period_start
            db.session.commit()

    return generated