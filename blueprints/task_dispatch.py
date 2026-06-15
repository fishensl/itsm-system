"""任务派发蓝图"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, InspectionTask, User, Department, Contract
from datetime import datetime
from utils.permission import require_permission, is_supervisor
from utils.pagination import paginate

dispatch_bp = Blueprint('task_dispatch', __name__)


@dispatch_bp.route('/')
@login_required
@require_permission('task:view_dept')
def dispatch_list():
    """派发看板 — 主管查看本部门任务"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    category_filter = request.args.get('category', '')

    query = InspectionTask.query

    # 如果是主管，只看本部门成员的任务
    if is_supervisor(current_user):
        dept = Department.query.get(current_user.department_id)
        if dept:
            dept_user_ids = [u.id for u in User.query.filter_by(department_id=dept.id).all()]
            query = query.filter(
                db.or_(
                    InspectionTask.assigned_to_user_id.in_(dept_user_ids),
                    InspectionTask.dispatched_by == current_user.id,
                    InspectionTask.assigned_to_user_id == None  # 未派发的
                )
            )

    if status_filter:
        query = query.filter(InspectionTask.status == status_filter)
    if category_filter:
        query = query.filter(InspectionTask.template_category == category_filter)

    tasks = query.order_by(InspectionTask.planned_start.asc(), InspectionTask.id.desc()).all()
    operators = User.query.filter(User.is_active == True).all()
    departments = Department.query.order_by(Department.sort_order).all()

    return render_template('task_dispatch/list.html',
                           tasks=tasks, operators=operators, departments=departments,
                           status_filter=status_filter, category_filter=category_filter)


@dispatch_bp.route('/assign/<int:task_id>', methods=['POST'])
@login_required
@require_permission('task:dispatch')
def dispatch_assign(task_id):
    """主管派发任务给指定人员"""
    task = InspectionTask.query.get_or_404(task_id)
    assignee_id = request.form.get('assignee_id', type=int)
    if not assignee_id:
        flash('请选择派发对象', 'danger')
        return redirect(url_for('task_dispatch.dispatch_list'))

    task.assigned_to_user_id = assignee_id
    task.dispatched_by = current_user.id
    task.dispatched_at = datetime.utcnow()
    if task.status == '待执行':
        task.status = '待执行'  # 保持待执行，等执行人接单

    db.session.commit()
    flash('任务已派发', 'success')
    return redirect(url_for('task_dispatch.dispatch_list'))


@dispatch_bp.route('/accept/<int:task_id>', methods=['POST'])
@login_required
def dispatch_accept(task_id):
    """运维人员接单"""
    task = InspectionTask.query.get_or_404(task_id)
    if task.assigned_to_user_id != current_user.id:
        flash('只能接分配给自己的任务', 'danger')
        return redirect(url_for('task_dispatch.dispatch_list'))
    task.status = '执行中'
    task.actual_start = datetime.utcnow()
    db.session.commit()
    flash('已接单', 'success')
    return redirect(url_for('task_dispatch.dispatch_list'))


@dispatch_bp.route('/start/<int:task_id>', methods=['POST'])
@login_required
def dispatch_start(task_id):
    """开始执行"""
    task = InspectionTask.query.get_or_404(task_id)
    task.status = '执行中'
    task.actual_start = datetime.utcnow()
    db.session.commit()
    flash('任务已开始执行', 'success')
    # 跳转到巡检创建页面（如果关联了模板）
    if task.template_id:
        return redirect(url_for('inspection_add', task_id=task.id))
    return redirect(url_for('task_dispatch.dispatch_list'))


@dispatch_bp.route('/complete/<int:task_id>', methods=['POST'])
@login_required
def dispatch_complete(task_id):
    """提交完成"""
    task = InspectionTask.query.get_or_404(task_id)
    task.status = '已完成'
    task.actual_end = datetime.utcnow()
    db.session.commit()
    flash('任务已完成', 'success')
    return redirect(url_for('task_dispatch.dispatch_list'))