"""[Deprecated 2026-06-23] 任务派发已并入 task_schedule。

本蓝图仅保留 URL 兼容重定向：
  GET  /task-dispatch/            → 301  /task-schedule/list
  POST /task-dispatch/assign/<id> → 307  /task-schedule/<id>/assign-form
  POST /task-dispatch/accept/<id> → 307  /task-schedule/<id>/status-form?status=执行中
  POST /task-dispatch/start/<id>  → 307  /task-schedule/<id>/status-form?status=执行中
  POST /task-dispatch/complete/<id> → 307 /task-schedule/<id>/status-form?status=已完成

（POST 用 307 保留 body；侧栏入口已在 sidebar_config 删除。）
"""
from flask import Blueprint, redirect, url_for, request
from flask_login import login_required

dispatch_bp = Blueprint('task_dispatch', __name__)


@dispatch_bp.route('/')
@login_required
def dispatch_list():
    return redirect(url_for('task_schedule.list_view', **request.args), code=301)


@dispatch_bp.route('/assign/<int:task_id>', methods=['POST'])
@login_required
def dispatch_assign(task_id):
    return redirect(url_for('task_schedule.assign_form', task_id=task_id), code=307)


@dispatch_bp.route('/accept/<int:task_id>', methods=['POST'])
@dispatch_bp.route('/start/<int:task_id>', methods=['POST'])
@login_required
def dispatch_accept_start(task_id):
    return redirect(url_for('task_schedule.change_status_form',
                            task_id=task_id, status='执行中'), code=307)


@dispatch_bp.route('/complete/<int:task_id>', methods=['POST'])
@login_required
def dispatch_complete(task_id):
    return redirect(url_for('task_schedule.change_status_form',
                            task_id=task_id, status='已完成'), code=307)
