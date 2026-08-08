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

from flask import (Blueprint, request, redirect, url_for,
                   flash, jsonify, send_from_directory, current_app)
from flask_login import login_required, current_user
from sqlalchemy import or_

from models import db, InspectionTask, User
from utils.permission import require_permission, has_permission, is_supervisor


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

ALL_STATUSES = ['待执行', '执行中', '待审核', '已完成', '已取消']
ACTIVE_STATUSES = ['待执行', '执行中', '待审核', '已完成']  # 看板默认展示前四种

# V17: 状态颜色统一 — 待执行红(提醒)/执行中橙(进行中)/待审核蓝(审核中)/已完成绿/已取消灰
STATUS_COLOR = {
    '待执行': 'danger',
    '执行中': 'warning',
    '待审核': 'info',
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
    # 实际工作量合计（仅已完成任务有实际值）
    actual_effort_done = sum(t.actual_effort or 0 for t in tasks if t.status == '已完成')
    return {
        'total': total, 'todo': todo, 'doing': doing, 'done': done, 'overdue': overdue,
        'effort_total': effort_total, 'effort_done': effort_done,
        'actual_effort_done': actual_effort_done,
    }


# ============================================================
# 路由
# ============================================================

@task_schedule_bp.route('/')
@login_required
@require_permission('task:schedule')
def index():
    """看板首页（SSR 已剥离：302 到 SPA 任务看板）"""
    return redirect('/app/task-schedule')


@task_schedule_bp.route('/list')
@login_required
@require_permission('task:schedule')
def list_view():
    """扁平表格视图（SSR 已剥离：302 到 SPA 任务看板）"""
    return redirect('/app/task-schedule')


# ============================================================
# 导入 / 模板下载
# ============================================================

EXCEL_HEADERS = ['客户名称', '任务描述', '优先级', '开始日期', '完成日期', '完成状态', '负责人', '完成时间', '预估工作量', '实际工作量']

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
        '2026-04-01', '2026-06-30', '已完成', '张三', '2026-06-15', '1', '1.5'
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
    """批量导入"成员分工安排表"（复用 services.task_schedule_service 公共服务）"""
    from services.task_schedule_service import import_task_excel
    f = request.files.get('importFile')
    if not f:
        flash('请选择 Excel 文件', 'danger')
        return redirect(url_for('task_schedule.index'))
    try:
        result = import_task_excel(f, current_user)
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        return redirect(url_for('task_schedule.index'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('任务安排导入失败')
        flash(f'导入失败：{e}', 'danger')
        return redirect(url_for('task_schedule.index'))
    msg_parts = [f'新增 {result["created"]}', f'更新 {result["updated"]}']
    if result['new_customer_names']:
        msg_parts.append(f'自动创建客户 {len(result["new_customer_names"])} 个：'
                         + '、'.join(result['new_customer_names'][:8])
                         + ('...' if len(result['new_customer_names']) > 8 else ''))
    if result['skipped']:
        msg_parts.append(f'跳过 {result["skipped"]} 行（' + '；'.join(result['skip_reasons'][:5])
                         + ('...' if len(result['skip_reasons']) > 5 else '') + '）')
    flash('导入完成：' + '；'.join(msg_parts), 'success' if not result['skipped'] else 'warning')
    return redirect(url_for('task_schedule.index'))

    return redirect(url_for('task_schedule.index'))


# ============================================================
# AJAX：改状态 / 改负责人 / 快速新建
# ============================================================

def _apply_status(task, new_status, now=None, allow_reopen=False):
    """改任务状态 + 状态机校验 + 自动维护 actual_start/actual_end 时间戳。单条/批量复用。
    校验失败抛 ValueError（由调用方转 400/flash）。allow_reopen 语义见 check_task_transition。"""
    from services.task_schedule_service import check_task_transition
    err = check_task_transition(task, new_status, allow_reopen=allow_reopen)
    if err:
        raise ValueError(err)
    now = now or local_now()
    task.status = new_status
    if new_status == '执行中' and not task.actual_start:
        task.actual_start = now
    if new_status == '已完成' and not task.actual_end:
        task.actual_end = now
    # 重开（终态→执行中）：清空完成时间戳，重新计时
    if new_status == '执行中' and task.actual_end:
        task.actual_end = None


def _apply_assignee(task, user, now=None):
    """指派负责人；user=None 视为清除。已派发过的不覆盖派发人。"""
    now = now or local_now()
    if user is None:
        task.assigned_to_user_id = None
        return
    task.assigned_to_user_id = user.id
    task.dispatched_by = task.dispatched_by or current_user.id
    task.dispatched_at = task.dispatched_at or now


@task_schedule_bp.route('/<int:task_id>/upload-report', methods=['POST'])
@login_required
@require_permission('inspection:edit')
def upload_report(task_id):
    """工程师从任务详情上传巡检报告 → 自动生成/复用巡检记录并提交审核（SSR 版）"""
    import os
    from services.inspection_service import upload_report_for_task
    from utils.upload import validate_upload
    task = InspectionTask.query.get_or_404(task_id)
    f = request.files.get('report_file')
    if not f:
        flash('请选择要上传的巡检报告文件', 'danger')
        return redirect(url_for('task_schedule.task_detail', task_id=task_id))
    ALLOWED_REPORT_EXT = {'.doc', '.docx', '.pdf', '.xlsx', '.xls',
                          '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.zip'}
    ok_flag, err, safe_name = validate_upload(f, ALLOWED_REPORT_EXT, max_size_mb=50)
    if not ok_flag:
        flash(err or '文件校验失败', 'danger')
        return redirect(url_for('task_schedule.task_detail', task_id=task_id))
    os.makedirs(os.path.join('static', 'uploads', 'inspection_reports', str(task.id)), exist_ok=True)
    rel_path = '/'.join(('uploads', 'inspection_reports', str(task.id), safe_name))
    f.save(os.path.join('static', rel_path))
    conclusion = (request.form.get('conclusion') or '').strip()
    remark = (request.form.get('remark') or '').strip()
    try:
        inspection, version = upload_report_for_task(
            task.id, rel_path, conclusion,
            current_user_id=current_user.id,
            current_user_name=current_user.realname or current_user.username,
            force=current_user.is_admin,
            remark=remark,
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('上传巡检报告失败 task_id=%s', task_id)
        flash(str(e) or '上传失败', 'danger')
        return redirect(url_for('task_schedule.task_detail', task_id=task_id))
    flash(f'报告已上传（版本 {version.version_no}）并提交审核，任务状态：{task.status}', 'success')
    return redirect(url_for('task_schedule.task_detail', task_id=task_id))


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

    try:
        _apply_status(task, new_status)
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
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


@task_schedule_bp.route('/<int:task_id>/actual-effort', methods=['POST'])
@login_required
@require_permission('task:schedule')
def set_actual_effort(task_id):
    """AJAX 改实际工作量（人天）。空串=清除为 None。"""
    task = InspectionTask.query.get_or_404(task_id)
    raw = (request.form.get('actual_effort') or
           (request.get_json(silent=True) or {}).get('actual_effort') or '').strip()
    if not raw:
        task.actual_effort = None
    else:
        effort = _parse_effort(raw)
        if effort is None:
            return jsonify(success=False, error='工作量格式不正确（应为数字，如 1 或 0.5）'), 400
        task.actual_effort = effort
    db.session.commit()
    return jsonify(success=True,
                   actual_effort=task.actual_effort,
                   actual_effort_text=_fmt_effort(task.actual_effort))


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
    try:
        _apply_status(task, new_status)
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(request.referrer or url_for('task_schedule.list_view'))
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

    # V28: 客户合同过期门禁 → 合同审批态
    from utils.constants import TASK_CONTRACT_REVIEW, TASK_PENDING
    from utils.customer_contract import contract_expired as _ce
    from models import Customer as _C
    status = TASK_PENDING
    exception_reason = (request.form.get('contract_exception_reason') or '').strip()
    cust = _C.query.get(customer_id) if customer_id else None
    if cust is not None and _ce(cust):
        if not exception_reason:
            flash('该客户合同已过期，请填写合同例外原因后提交（需部门主管审核）', 'danger')
            return redirect(request.referrer or url_for('task_schedule.index'))
        status = TASK_CONTRACT_REVIEW

    task = InspectionTask(
        title=title,
        task_type='计划',
        status=status,
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
        contract_exception_status='待审核' if status == TASK_CONTRACT_REVIEW else '',
        contract_exception_reason=exception_reason,
        contract_exception_by=(current_user.realname or current_user.username),
        contract_exception_at=datetime.utcnow() if status == TASK_CONTRACT_REVIEW else None,
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
    # 重开（已完成/已取消 → 执行中）为纠正性操作，仅限管理员/部门主管
    reopens = [t for t in tasks if t.status in ('已完成', '已取消') and new_status == '执行中']
    if reopens:
        is_admin = getattr(current_user, 'is_admin', False)
        if not is_admin and not is_supervisor(current_user):
            db.session.rollback()
            return jsonify(success=False,
                           error=f'重开已完成/已取消任务（{len(reopens)} 条）需要管理员或部门主管权限'), 403
    try:
        for t in tasks:
            _apply_status(t, new_status, now, allow_reopen=bool(reopens))
    except ValueError as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 400
    db.session.commit()
    if reopens:
        from blueprints.vue_api_sys import audit_log
        audit_log('task:reopen', 'inspection_task', None,
                  f'批量重开 {len(reopens)} 个已完成/已取消任务 → 执行中（操作人：'
                  f'{current_user.realname or current_user.username}）')
        current_app.logger.info(
            '任务重开审计(SSR): 用户[%s] 批量重开 %d 个任务, IP=%s',
            current_user.username, len(reopens), request.remote_addr)
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
    """任务详情（SSR 已剥离：302 到 SPA 任务看板）"""
    if not (has_permission('task:schedule') or has_permission('inspection:view')):
        flash('权限不足，需要：任务安排-看板 或 巡检管理-查看', 'danger')
        return redirect(url_for('index'))
    return redirect('/app/task-schedule')


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
            _fmt_effort(t.actual_effort),
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
