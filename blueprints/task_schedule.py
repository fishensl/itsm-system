# -*- coding: utf-8 -*-
"""任务安排蓝图 — 看板视图 + Excel 批量导入

围绕已有 InspectionTask 模型构建一个面向"分工管理"的看板，提供三种视图：
  ① by-engineer  按工程师分列
  ② by-status    按状态分列
  ③ matrix       工程师 × 状态矩阵

数据来源：Excel(成员分工安排表) 一次性导入 → InspectionTask（source='Excel导入'）。
后续仍可与 /inspection-tasks 老页面并行使用，新页面侧重"主管 / 全员"分工视角。
"""
import os
import re
from datetime import date, datetime, timezone, timedelta
from collections import defaultdict

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, send_from_directory, current_app)
from flask_login import login_required, current_user
from sqlalchemy import or_

from models import db, InspectionTask, Customer, User
from utils.permission import require_permission, has_permission, is_supervisor
from utils.pagination import paginate, paginate_render_args


task_schedule_bp = Blueprint('task_schedule', __name__, url_prefix='/task-schedule')


# 北京本地时间（naive datetime），用于用户可见的 actual_start/actual_end。
# 用固定 +08:00 偏移避免 zoneinfo/tzdata 跨平台问题。
_BEIJING = timezone(timedelta(hours=8))


def local_now():
    """当前北京本地时间（naive）。"""
    return datetime.now(_BEIJING).replace(tzinfo=None)


# ============================================================
# 常量 / 工具
# ============================================================

STATUS_FROM_EXCEL = {
    '未开始': '待执行',
    '待执行': '待执行',
    '进行中': '执行中',
    '执行中': '执行中',
    '已完成': '已完成',
    '完成':   '已完成',
    '已取消': '已取消',
    '取消':   '已取消',
}

ALL_STATUSES = ['待执行', '执行中', '已完成', '已取消']
ACTIVE_STATUSES = ['待执行', '执行中', '已完成']  # 看板默认展示前三种

# V17: 状态颜色统一 — 待执行红(提醒)/执行中橙(进行中)/已完成绿/已取消灰
STATUS_COLOR = {
    '待执行': 'danger',
    '执行中': 'warning',
    '已完成': 'success',
    '已取消': 'secondary',
}

# 从 Excel 任务描述里抠出客户名前缀的正则：
#   水科院共青城2026年二季度巡检   -> 水科院共青城
#   鄱阳湖水文2026年六月巡检       -> 鄱阳湖水文
#   赣江中游水文2026年6月巡检      -> 赣江中游水文
#   外洲大队2026年巡检              -> 外洲大队
#   信江饶河水文（景德镇）2026年二季度巡检 -> 信江饶河水文（景德镇）
_CUSTOMER_SUFFIX_RE = re.compile(r'\s*[\d]{4}年.*$')


def extract_customer_name(title):
    """从任务标题里提取客户名（去掉 yyyy年... 后缀）"""
    if not title:
        return ''
    name = _CUSTOMER_SUFFIX_RE.sub('', str(title).strip())
    return name.strip()


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
    """预估工作量 cell -> float(人天) | None

    接受 1 / 1.5 / "3" / "0.5天" / "3人天" 等写法；非法或空返回 None。
    """
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return float(v) if v >= 0 else None
    s = str(v).strip()
    if not s:
        return None
    # 去掉"人天/天/日/days/d"等单位后缀（人天优先匹配，避免先吃掉"天"剩"人"）
    s = re.sub(r'(人天|天|日|days?|d)\s*$', '', s, flags=re.IGNORECASE).strip()
    try:
        f = float(s)
    except ValueError:
        return None
    return f if f >= 0 else None


def _fmt_effort(v):
    """float 人天 -> 展示字符串（1.0→'1'，0.5→'0.5'，None→''）。"""
    if v is None:
        return ''
    # %g 去掉多余小数位：1.0→1, 0.5→0.5, 3.5→3.5
    return '%g' % v


def is_overdue(task, today=None):
    """计划截止过了今天且未完成 = 逾期"""
    if not task.planned_end:
        return False
    if task.status in ('已完成', '已取消'):
        return False
    today = today or date.today()
    return task.planned_end < today


# ============================================================
# 数据组装（看板）
# ============================================================

def _base_query():
    """看板只看通过本页面创建/导入的"分工"任务。"""
    # 仅取 source 为本系统已知值的 — 保留全部 source 也无妨
    return InspectionTask.query


def _effective_request_args(args):
    """默认期间口径：请求里既没带 `period`，也没手填 `start_from`/`start_to` 时，
    自动落到 `this_quarter`，使看板/列表/导出默认展示本季度。

    返回 (effective_args, effective_period)：
      - effective_args：传给 _apply_filters 的 args（包装了 period 覆盖）；
      - effective_period：回填筛选条 f_period 用于"本季"按钮高亮。
    用户点了期间按钮或手填了日期则尊重原值。
    """
    has_explicit_period = bool(args.get('period', ''))
    has_explicit_date = bool(args.get('start_from', '')) or bool(args.get('start_to', ''))
    if not has_explicit_period and not has_explicit_date:
        effective_period = 'this_quarter'
        from werkzeug.datastructures import MultiDict
        # 复制成可变 MultiDict 再注入 period，避免改动原始 request.args
        merged = MultiDict(args.to_dict(flat=True))
        merged.setlist('period', [effective_period])
        return merged, effective_period
    return args, args.get('period', '')


def _apply_filters(query, args):
    """筛选条参数 → SQL filter"""
    import calendar
    engineer_id = args.get('engineer_id', type=int)
    status = args.get('status', '')
    customer_id = args.get('customer_id', type=int)
    # V17: 期间快捷（当月/当季/当年）— 优先级低于手填日期
    period = args.get('period', '')
    start_from_raw = args.get('start_from', '')
    start_to_raw = args.get('start_to', '')
    if period and not start_from_raw and not start_to_raw:
        today = date.today()
        if period == 'this_month':
            start_from_raw = today.replace(day=1).isoformat()
            last = calendar.monthrange(today.year, today.month)[1]
            start_to_raw = today.replace(day=last).isoformat()
        elif period == 'this_quarter':
            qm = (today.month - 1) // 3
            sm, em = qm * 3 + 1, qm * 3 + 3
            start_from_raw = date(today.year, sm, 1).isoformat()
            start_to_raw = date(today.year, em,
                                calendar.monthrange(today.year, em)[1]).isoformat()
        elif period == 'this_year':
            start_from_raw = date(today.year, 1, 1).isoformat()
            start_to_raw = date(today.year, 12, 31).isoformat()
    start_from = parse_excel_date(start_from_raw)
    start_to = parse_excel_date(start_to_raw)
    q = args.get('q', '').strip()
    overdue = args.get('overdue', '')

    if engineer_id:
        query = query.filter(InspectionTask.assigned_to_user_id == engineer_id)
    if status:
        query = query.filter(InspectionTask.status == status)
    if customer_id:
        query = query.filter(InspectionTask.customer_id == customer_id)
    if start_from:
        query = query.filter(InspectionTask.planned_start >= start_from)
    if start_to:
        query = query.filter(InspectionTask.planned_start <= start_to)
    if q:
        query = query.filter(InspectionTask.title.contains(q))
    if overdue:
        today = date.today()
        query = query.filter(
            InspectionTask.planned_end < today,
            ~InspectionTask.status.in_(('已完成', '已取消')),
        )
    # V17: 主管隐式只看本部门任务（有 task:dispatch 跨部门派发权限的不受限）
    if (is_supervisor(current_user)
            and not has_permission('task:dispatch')
            and current_user.department_id):
        dept_user_ids = [u.id for u in
                         User.query.filter_by(department_id=current_user.department_id).all()]
        if dept_user_ids:
            query = query.filter(or_(
                InspectionTask.assigned_to_user_id.in_(dept_user_ids),
                InspectionTask.assigned_to_user_id.is_(None),
                InspectionTask.dispatched_by == current_user.id,
            ))
    return query


def _engineers_with_tasks():
    """列出可作为任务负责人的用户 — 限"巡检人员"名册内的活跃用户。

    任务安排的看板列 / 筛选下拉 / 指派下拉 / 矩阵行均以此为唯一数据源，
    避免 admin 等非巡检人员混入负责人候选。要新增候选人先到
    /inspectors 把用户勾选为巡检人员。
    """
    from models import Inspector
    inspector_uids = [uid for (uid,) in db.session.query(Inspector.user_id)
                      .filter(Inspector.is_active == True).all()]  # noqa: E712
    if not inspector_uids:
        return []
    assigned_ids = {tid for (tid,) in db.session.query(InspectionTask.assigned_to_user_id)
                    .filter(InspectionTask.assigned_to_user_id.isnot(None)).distinct().all()}
    users = (User.query
             .filter(User.id.in_(inspector_uids),
                     User.is_active == True)
             .order_by(User.id).all())  # noqa: E712
    # 优先把"被分配过任务"的排到前面，便于看板列稳定
    ordered = sorted(users, key=lambda u: (0 if u.id in assigned_ids else 1, u.id))
    return ordered


def _kpi_counts(tasks):
    """根据已筛选的任务列表算 KPI（前端拿来直接展示）"""
    today = date.today()
    total = len(tasks)
    todo = sum(1 for t in tasks if t.status == '待执行')
    doing = sum(1 for t in tasks if t.status == '执行中')
    done = sum(1 for t in tasks if t.status == '已完成')
    overdue = sum(1 for t in tasks if is_overdue(t, today))
    # 预估工作量合计（人天）— 未设置的当 0，便于"任务量"口径更准确
    effort_total = sum(t.estimated_effort or 0 for t in tasks)
    effort_done = sum(t.estimated_effort or 0 for t in tasks if t.status == '已完成')
    return {
        'total': total, 'todo': todo, 'doing': doing, 'done': done, 'overdue': overdue,
        'effort_total': effort_total, 'effort_done': effort_done,
    }


# ============================================================
# 路由
# ============================================================

@task_schedule_bp.route('/')
@login_required
@require_permission('task:schedule')
def index():
    """看板首页（三视图切换）

    任务自动生成不在此处触发 —— 客户/合同新增时已在各自路由里生成。
    若需为存量数据补打本年度任务，点页头「回填本年度任务」按钮，
    即 POST /task-schedule/regenerate 一次性回填。
    """
    view = request.args.get('view', 'by-engineer')
    if view not in ('by-engineer', 'by-status', 'matrix', 'by-customer'):
        view = 'by-engineer'

    # V18: 默认本季度口径（无 period、无手填日期时自动落到 this_quarter）
    eff_args, eff_period = _effective_request_args(request.args)

    query = _apply_filters(_base_query(), eff_args)
    tasks = query.order_by(InspectionTask.planned_end.asc(), InspectionTask.id.desc()).all()

    kpi = _kpi_counts(tasks)
    engineers = _engineers_with_tasks()
    customers = Customer.query.order_by(Customer.name).all()
    today = date.today()

    # 按工程师 + 状态分桶
    buckets_by_engineer = defaultdict(lambda: defaultdict(list))   # {user_id: {status: [tasks]}}
    unassigned = defaultdict(list)                                 # {status: [tasks]}  无负责人
    for t in tasks:
        st = t.status if t.status in ALL_STATUSES else '待执行'
        if t.assigned_to_user_id:
            buckets_by_engineer[t.assigned_to_user_id][st].append(t)
        else:
            unassigned[st].append(t)

    # 按状态分桶（视图②）
    buckets_by_status = defaultdict(list)
    overdue_bucket = []
    for t in tasks:
        st = t.status if t.status in ALL_STATUSES else '待执行'
        buckets_by_status[st].append(t)
        if is_overdue(t, today):
            overdue_bucket.append(t)

    # 矩阵（视图③）：engineer × status -> count
    matrix = {}
    for u in engineers:
        matrix[u.id] = {s: len(buckets_by_engineer[u.id][s]) for s in ALL_STATUSES}
    matrix_unassigned = {s: len(unassigned[s]) for s in ALL_STATUSES}

    # 按客户分桶（视图④）：{customer_id: {status: [tasks]}}
    buckets_by_customer = defaultdict(lambda: defaultdict(list))
    for t in tasks:
        if t.customer_id:
            st = t.status if t.status in ALL_STATUSES else '待执行'
            buckets_by_customer[t.customer_id][st].append(t)
    if buckets_by_customer:
        customers_with_tasks = (Customer.query
                                .filter(Customer.id.in_(list(buckets_by_customer.keys())))
                                .order_by(Customer.name).all())
    else:
        customers_with_tasks = []

    return render_template(
        'task_schedule/index.html',
        view=view,
        tasks=tasks,
        engineers=engineers,
        customers=customers,
        kpi=kpi,
        today=today,
        active_statuses=ACTIVE_STATUSES,
        all_statuses=ALL_STATUSES,
        status_color=STATUS_COLOR,
        buckets_by_engineer=buckets_by_engineer,
        unassigned=unassigned,
        buckets_by_status=buckets_by_status,
        overdue_bucket=overdue_bucket,
        matrix=matrix,
        matrix_unassigned=matrix_unassigned,
        buckets_by_customer=buckets_by_customer,
        customers_with_tasks=customers_with_tasks,
        is_overdue=is_overdue,
        # 回填筛选条
        f_engineer=request.args.get('engineer_id', type=int) or 0,
        f_status=request.args.get('status', ''),
        f_customer=request.args.get('customer_id', type=int) or 0,
        f_q=request.args.get('q', ''),
        f_overdue=request.args.get('overdue', ''),
        f_start_from=request.args.get('start_from', ''),
        f_start_to=request.args.get('start_to', ''),
        f_period=eff_period,
    )


@task_schedule_bp.route('/list')
@login_required
@require_permission('task:schedule')
def list_view():
    """扁平表格视图（带分页）"""
    page = request.args.get('page', 1, type=int)
    # V18: 默认本季度口径
    eff_args, eff_period = _effective_request_args(request.args)
    query = _apply_filters(_base_query(), eff_args)
    query = query.order_by(InspectionTask.planned_end.asc(), InspectionTask.id.desc())
    pag = paginate(query, page=page, per_page=30)

    engineers = _engineers_with_tasks()
    customers = Customer.query.order_by(Customer.name).all()
    today = date.today()
    return render_template(
        'task_schedule/list.html',
        **paginate_render_args(pag),
        engineers=engineers,
        customers=customers,
        all_statuses=ALL_STATUSES,
        status_color=STATUS_COLOR,
        today=today,
        is_overdue=is_overdue,
        f_engineer=request.args.get('engineer_id', type=int) or 0,
        f_status=request.args.get('status', ''),
        f_customer=request.args.get('customer_id', type=int) or 0,
        f_q=request.args.get('q', ''),
        f_overdue=request.args.get('overdue', ''),
        f_start_from=request.args.get('start_from', ''),
        f_start_to=request.args.get('start_to', ''),
        f_period=eff_period,
    )


# ============================================================
# 导入 / 模板下载
# ============================================================

EXCEL_HEADERS = ['客户名称', '任务描述', '优先级', '开始日期', '完成日期', '完成状态', '负责人', '完成时间', '预估工作量']

# 优先级允许值（与 UI 保持一致；超出范围回退 '中'）
PRIORITY_VALUES = {'低', '中', '高', '紧急'}


@task_schedule_bp.route('/import/template')
@login_required
@require_permission('task:schedule')
def import_template():
    """下载 Excel 导入模板（含表头 + 1 行示例）"""
    from utils.excel_export import export_xlsx
    rows = [[
        '示例客户A', '示例客户A2026年二季度巡检', '中',
        '2026-04-01', '2026-06-30', '已完成', '张三', '2026-06-15', '1'
    ]]
    tmp_path, download_name = export_xlsx(
        EXCEL_HEADERS, rows,
        filename='任务安排导入模板.xlsx',
        sheet_name='成员分工安排表',
    )
    return send_from_directory(
        os.path.dirname(tmp_path), os.path.basename(tmp_path),
        as_attachment=True, download_name=download_name,
    )


@task_schedule_bp.route('/import', methods=['POST'])
@login_required
@require_permission('task:schedule')
def import_excel():
    """批量导入"成员分工安排表"

    流程（upsert by (title, customer_id)）：
      1. 客户名 = 标题去掉 yyyy年... 后缀；找不到 Customer → 自动创建（仅 name）
      2. 负责人 = User.realname 精确匹配；找不到则记为 skipped
      3. 同 (title, customer_id) 已存在 → 更新 status/dates/assignee；否则新建
    """
    from utils.upload import (validate_upload, save_temp_upload,
                              open_excel, cleanup_temp_file, ALLOWED_EXCEL_EXT)

    f = request.files.get('importFile')
    if not f:
        flash('请选择 Excel 文件', 'danger')
        return redirect(url_for('task_schedule.index'))

    ok, err, _ = validate_upload(f, ALLOWED_EXCEL_EXT, max_size_mb=5)
    if not ok:
        flash(err, 'danger')
        return redirect(url_for('task_schedule.index'))

    tmp = save_temp_upload(f, suffix='.xlsx')
    try:
        wb, ws, err = open_excel(tmp, app=current_app)
        if err:
            flash(err[0], err[1] if len(err) > 1 else 'danger')
            return redirect(url_for('task_schedule.index'))

        # 列名映射（按表头第一行）
        header = [c.value for c in ws[1]]
        col = {}
        for i, h in enumerate(header):
            if h:
                col[str(h).strip()] = i

        required = ['任务描述', '负责人']
        miss = [h for h in required if h not in col]
        if miss:
            flash('Excel 缺少必需列：' + '、'.join(miss), 'danger')
            return redirect(url_for('task_schedule.index'))

        created = 0
        updated = 0
        skipped = 0
        skip_reasons = []
        new_customer_names = []

        # 预取所有用户/客户，省 N+1
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
            user = user_by_name.get(owner_name)
            if not user:
                skipped += 1
                skip_reasons.append(f'第{r}行：找不到负责人 "{owner_name}"')
                continue

            # 解析客户：优先取 Excel 里的 '客户名称' 列；为空则从标题抽（老格式兼容）
            customer_name = str(cell('客户名称') or '').strip() or extract_customer_name(title)
            if not customer_name:
                skipped += 1
                skip_reasons.append(f'第{r}行：无法从「客户名称」列或标题中识别客户')
                continue
            customer = Customer.query.filter_by(name=customer_name).first()
            if not customer:
                customer = Customer(name=customer_name)
                db.session.add(customer)
                db.session.flush()  # 拿 id
                new_customer_names.append(customer_name)

            # 状态映射
            raw_status = str(cell('完成状态') or '').strip()
            status = STATUS_FROM_EXCEL.get(raw_status, '待执行')

            # 优先级：未填或非法值回退 '中'
            raw_priority = str(cell('优先级') or '').strip()
            priority = raw_priority if raw_priority in PRIORITY_VALUES else '中'

            planned_start = parse_excel_date(cell('开始日期'))
            planned_end = parse_excel_date(cell('完成日期'))
            actual_end = parse_excel_datetime(cell('完成时间'))

            # 预估工作量（人天）：允许 "1"/"1.5"/"3天"，非法/空 → None
            effort = _parse_effort(cell('预估工作量'))

            # upsert：(title, customer_id) 唯一
            existing = (InspectionTask.query
                        .filter_by(title=title, customer_id=customer.id)
                        .first())
            if existing:
                existing.status = status
                existing.priority = priority
                existing.assigned_to_user_id = user.id
                existing.planned_start = planned_start or existing.planned_start
                existing.planned_end = planned_end or existing.planned_end
                if actual_end:
                    existing.actual_end = actual_end
                if status == '已完成' and not existing.actual_end:
                    existing.actual_end = local_now()
                if effort is not None:
                    existing.estimated_effort = effort
                existing.dispatched_by = existing.dispatched_by or current_user.id
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
                    assigned_to_user_id=user.id,
                    dispatched_by=current_user.id,
                    dispatched_at=datetime.utcnow(),
                    source='Excel导入',
                    template_category='巡检',
                    created_by=(current_user.realname or current_user.username),
                )
                db.session.add(task)
                created += 1

        db.session.commit()

        msg_parts = [f'新增 {created}', f'更新 {updated}']
        if new_customer_names:
            msg_parts.append(f'自动创建客户 {len(new_customer_names)} 个：'
                             + '、'.join(new_customer_names[:8])
                             + ('...' if len(new_customer_names) > 8 else ''))
        if skipped:
            msg_parts.append(f'跳过 {skipped} 行（' + '；'.join(skip_reasons[:5])
                             + ('...' if len(skip_reasons) > 5 else '') + '）')
        flash('导入完成：' + '；'.join(msg_parts), 'success' if not skipped else 'warning')
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('任务安排导入失败')
        flash(f'导入失败：{e}', 'danger')
    finally:
        cleanup_temp_file(tmp)

    return redirect(url_for('task_schedule.index'))


# ============================================================
# AJAX：改状态 / 改负责人 / 快速新建
# ============================================================

def _apply_status(task, new_status, now=None):
    """改任务状态 + 自动维护 actual_start/actual_end 时间戳。单条/批量复用。"""
    now = now or local_now()
    task.status = new_status
    if new_status == '执行中' and not task.actual_start:
        task.actual_start = now
    if new_status == '已完成' and not task.actual_end:
        task.actual_end = now


def _apply_assignee(task, user, now=None):
    """指派负责人；user=None 视为清除。已派发过的不覆盖派发人。"""
    now = now or local_now()
    if user is None:
        task.assigned_to_user_id = None
        return
    task.assigned_to_user_id = user.id
    task.dispatched_by = task.dispatched_by or current_user.id
    task.dispatched_at = task.dispatched_at or now


@task_schedule_bp.route('/<int:task_id>/status', methods=['POST'])
@login_required
@require_permission('task:schedule')
def change_status(task_id):
    """AJAX 改单个任务状态"""
    task = InspectionTask.query.get_or_404(task_id)
    new_status = (request.form.get('status') or
                  (request.get_json(silent=True) or {}).get('status') or '').strip()
    if new_status not in ALL_STATUSES:
        return jsonify(success=False, error='非法状态'), 400

    _apply_status(task, new_status)
    db.session.commit()
    return jsonify(success=True, status=new_status)


@task_schedule_bp.route('/<int:task_id>/complete-time', methods=['POST'])
@login_required
@require_permission('task:schedule')
def set_complete_time(task_id):
    """AJAX 手动设置/修改/清除任务完成时间（actual_end）。空值=清除。"""
    task = InspectionTask.query.get_or_404(task_id)
    raw = (request.form.get('actual_end') or
           (request.get_json(silent=True) or {}).get('actual_end') or '').strip()
    if raw:
        d = parse_excel_date(raw)
        if not d:
            return jsonify(success=False, error='日期格式不正确'), 400
        # actual_end 是 DateTime 字段，parse_excel_date 返回 date，补 00:00 转 datetime
        task.actual_end = datetime(d.year, d.month, d.day)
    else:
        task.actual_end = None
    db.session.commit()
    return jsonify(success=True,
                   actual_end=task.actual_end.strftime('%Y-%m-%d') if task.actual_end else '')


@task_schedule_bp.route('/<int:task_id>/title', methods=['POST'])
@login_required
@require_permission('task:schedule')
def set_title(task_id):
    """AJAX 改任务标题。"""
    task = InspectionTask.query.get_or_404(task_id)
    raw = (request.form.get('title') or
           (request.get_json(silent=True) or {}).get('title') or '').strip()
    if not raw:
        return jsonify(success=False, error='标题不能为空'), 400
    task.title = raw
    db.session.commit()
    return jsonify(success=True, title=task.title)


@task_schedule_bp.route('/<int:task_id>/effort', methods=['POST'])
@login_required
@require_permission('task:schedule')
def set_effort(task_id):
    """AJAX 改预估工作量（人天）。空串=清除为 None。"""
    task = InspectionTask.query.get_or_404(task_id)
    raw = (request.form.get('estimated_effort') or
           (request.get_json(silent=True) or {}).get('estimated_effort') or '').strip()
    if not raw:
        task.estimated_effort = None
    else:
        effort = _parse_effort(raw)
        if effort is None:
            return jsonify(success=False, error='工作量格式不正确（应为数字，如 1 或 0.5）'), 400
        task.estimated_effort = effort
    db.session.commit()
    return jsonify(success=True,
                   estimated_effort=task.estimated_effort,
                   estimated_effort_text=_fmt_effort(task.estimated_effort))


@task_schedule_bp.route('/<int:task_id>/assign', methods=['POST'])
@login_required
@require_permission('task:schedule')
def change_assignee(task_id):
    """AJAX 改负责人"""
    task = InspectionTask.query.get_or_404(task_id)
    payload = request.get_json(silent=True) or {}
    uid = request.form.get('assignee_id', type=int) or payload.get('assignee_id')
    try:
        uid = int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return jsonify(success=False, error='非法用户ID'), 400

    if uid:
        user = User.query.get(uid)
        if not user:
            return jsonify(success=False, error='用户不存在'), 400
        _apply_assignee(task, user)
        name = user.realname or user.username
    else:
        _apply_assignee(task, None)
        name = ''
    db.session.commit()
    return jsonify(success=True, assignee_id=task.assigned_to_user_id, assignee_name=name)


@task_schedule_bp.route('/<int:task_id>/status-form', methods=['POST'])
@login_required
def change_status_form(task_id):
    """表单版改状态（兼容老 task_dispatch 的 accept/start/complete 重定向落点）"""
    task = InspectionTask.query.get_or_404(task_id)
    new_status = (request.values.get('status') or '').strip()
    if new_status not in ALL_STATUSES:
        flash('非法状态', 'danger')
        return redirect(url_for('task_schedule.list_view'))
    _apply_status(task, new_status)
    db.session.commit()
    flash('任务状态已更新为「%s」' % new_status, 'success')
    return redirect(request.referrer or url_for('task_schedule.list_view'))


@task_schedule_bp.route('/<int:task_id>/assign-form', methods=['POST'])
@login_required
@require_permission('task:dispatch')
def assign_form(task_id):
    """表单版派发（兼容老 task_dispatch 的 assign 重定向落点）"""
    task = InspectionTask.query.get_or_404(task_id)
    uid = request.form.get('assignee_id', type=int)
    if not uid:
        flash('请选择派发对象', 'danger')
        return redirect(url_for('task_schedule.list_view'))
    user = User.query.get(uid)
    if not user:
        flash('用户不存在', 'danger')
        return redirect(url_for('task_schedule.list_view'))
    task.assigned_to_user_id = user.id
    task.dispatched_by = current_user.id
    task.dispatched_at = datetime.utcnow()
    db.session.commit()
    flash('任务已派发给 %s' % (user.realname or user.username), 'success')
    return redirect(url_for('task_schedule.list_view'))


@task_schedule_bp.route('/quick-add', methods=['POST'])
@login_required
@require_permission('task:schedule')
def quick_add():
    """看板内"+ 新任务"快速新建"""
    title = (request.form.get('title') or '').strip()
    customer_id = request.form.get('customer_id', type=int)
    assignee_id = request.form.get('assignee_id', type=int)
    priority = (request.form.get('priority') or '中').strip()
    planned_start = parse_excel_date(request.form.get('planned_start'))
    planned_end = parse_excel_date(request.form.get('planned_end'))
    effort = _parse_effort(request.form.get('estimated_effort'))

    if not title:
        flash('任务标题不能为空', 'danger')
        return redirect(request.referrer or url_for('task_schedule.index'))
    if not customer_id:
        flash('请选择客户', 'danger')
        return redirect(request.referrer or url_for('task_schedule.index'))

    task = InspectionTask(
        title=title,
        task_type='计划',
        status='待执行',
        priority=priority,
        customer_id=customer_id,
        assigned_to_user_id=assignee_id or None,
        planned_start=planned_start,
        planned_end=planned_end,
        estimated_effort=effort,
        dispatched_by=current_user.id,
        dispatched_at=datetime.utcnow(),
        source='手动',
        template_category='巡检',
        created_by=(current_user.realname or current_user.username),
    )
    db.session.add(task)
    db.session.commit()
    flash('任务已创建', 'success')
    return redirect(request.referrer or url_for('task_schedule.index'))


@task_schedule_bp.route('/<int:task_id>/delete', methods=['POST'])
@login_required
@require_permission('task:schedule')
def delete_task(task_id):
    """删除任务"""
    task = InspectionTask.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    flash('任务已删除', 'success')
    return redirect(request.referrer or url_for('task_schedule.index'))


@task_schedule_bp.route('/regenerate', methods=['POST'])
@login_required
@require_permission('task:schedule')
def regenerate():
    """按各客户巡检频率一次性回填本年度全部任务（幂等，可重复点）。

    生产历史客户多半在新增/编辑时才生成任务，老存量客户缺当年任务；
    跨年/跨季度后任务也不会自动滚动。此入口让管理员手动补齐。
    幂等性由 generate_for_all_customers 内部的 (customer_id, planned_start)
    existing 集合保证。
    """
    from utils.customer_task_generator import generate_for_all_customers
    try:
        n = generate_for_all_customers()
        flash(f'已回填 {n} 个本年度巡检任务', 'success')
    except Exception as e:
        current_app.logger.exception('regenerate 任务回填失败')
        flash(f'回填失败：{e}', 'danger')
    return redirect(request.referrer or url_for('task_schedule.index'))


# ============================================================
# AJAX 批量操作（列表视图工具栏调用）
# ============================================================

def _parse_ids(form):
    """从 form 里抠 ids 多值字段为 List[int]，去重、剔非法"""
    raw = form.getlist('ids') or form.getlist('ids[]')
    out = []
    seen = set()
    for v in raw:
        try:
            i = int(v)
        except (TypeError, ValueError):
            continue
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


@task_schedule_bp.route('/batch/status', methods=['POST'])
@login_required
@require_permission('task:schedule')
def batch_status():
    """批量改状态"""
    ids = _parse_ids(request.form)
    new_status = (request.form.get('status') or '').strip()
    if not ids:
        return jsonify(success=False, error='未选择任务'), 400
    if new_status not in ALL_STATUSES:
        return jsonify(success=False, error='非法状态'), 400

    tasks = InspectionTask.query.filter(InspectionTask.id.in_(ids)).all()
    now = local_now()
    for t in tasks:
        _apply_status(t, new_status, now)
    db.session.commit()
    return jsonify(success=True, count=len(tasks), status=new_status)


@task_schedule_bp.route('/batch/assign', methods=['POST'])
@login_required
@require_permission('task:schedule')
def batch_assign():
    """批量指派负责人；assignee_id 为空串视为清除指派"""
    ids = _parse_ids(request.form)
    raw_uid = (request.form.get('assignee_id') or '').strip()
    if not ids:
        return jsonify(success=False, error='未选择任务'), 400

    user = None
    if raw_uid:
        try:
            user = User.query.get(int(raw_uid))
        except (TypeError, ValueError):
            user = None
        if not user:
            return jsonify(success=False, error='用户不存在'), 400

    tasks = InspectionTask.query.filter(InspectionTask.id.in_(ids)).all()
    now = local_now()
    for t in tasks:
        _apply_assignee(t, user, now)
    db.session.commit()
    name = (user.realname or user.username) if user else ''
    return jsonify(success=True, count=len(tasks),
                   assignee_id=(user.id if user else None), assignee_name=name)


@task_schedule_bp.route('/batch/delete', methods=['POST'])
@login_required
@require_permission('task:schedule')
def batch_delete():
    """批量删除任务"""
    ids = _parse_ids(request.form)
    if not ids:
        return jsonify(success=False, error='未选择任务'), 400

    count = (InspectionTask.query
             .filter(InspectionTask.id.in_(ids))
             .delete(synchronize_session=False))
    db.session.commit()
    return jsonify(success=True, count=count)


# ============================================================
# 任务详情（V18：收编自老 /inspection-tasks/<id>）
# ============================================================

@task_schedule_bp.route('/<int:task_id>')
@login_required
def task_detail(task_id):
    """任务详情。task:schedule | inspection:view 任一权限均可看。"""
    if not (has_permission('task:schedule') or has_permission('inspection:view')):
        flash('权限不足，需要：任务安排-看板 或 巡检管理-查看', 'danger')
        return redirect(url_for('index'))

    from models import Inspection, Inspector, InspectionTemplate
    task = InspectionTask.query.get_or_404(task_id)

    # 关联巡检记录
    records = (Inspection.query.filter_by(task_id=task.id)
               .order_by(Inspection.id.desc()).all())

    # 老数据兼容：把 inspector_ids 解析成人名（仅展示）
    inspector_names = []
    if task.inspector_ids:
        try:
            ids = [int(x) for x in task.inspector_ids.split(',') if x.strip()]
            if ids:
                inspectors = Inspector.query.filter(Inspector.id.in_(ids)).all()
                inspector_names = [i.name for i in inspectors if getattr(i, 'name', None)]
        except (ValueError, AttributeError):
            inspector_names = []

    template = None
    if task.template_id:
        template = InspectionTemplate.query.get(task.template_id)

    return render_template(
        'task_schedule/detail.html',
        task=task,
        records=records,
        customer=task.customer_rel,
        template=template,
        inspector_names=inspector_names,
        all_statuses=ALL_STATUSES,
        status_color=STATUS_COLOR,
    )


@task_schedule_bp.route('/export')
@login_required
@require_permission('task:schedule')
def export_excel():
    """按当前筛选条件导出 Excel"""
    from utils.excel_export import export_xlsx

    # V18: 导出口径与看板一致（默认本季度）
    eff_args, _eff_period = _effective_request_args(request.args)
    query = _apply_filters(_base_query(), eff_args)
    tasks = query.order_by(InspectionTask.planned_end.asc(), InspectionTask.id.desc()).all()

    rows = []
    for t in tasks:
        user = t.assignee_rel
        rows.append([
            (t.customer_rel.name if t.customer_rel else ''),
            t.title,
            t.priority or '',
            t.planned_start.isoformat() if t.planned_start else '',
            t.planned_end.isoformat() if t.planned_end else '',
            t.status,
            (user.realname or user.username) if user else '',
            t.actual_end.strftime('%Y-%m-%d') if t.actual_end else '',
            _fmt_effort(t.estimated_effort),
        ])

    tmp_path, download_name = export_xlsx(
        EXCEL_HEADERS, rows,
        filename=f'任务安排_{date.today().isoformat()}.xlsx',
        sheet_name='成员分工安排表',
    )
    return send_from_directory(
        os.path.dirname(tmp_path), os.path.basename(tmp_path),
        as_attachment=True, download_name=download_name,
    )
