# -*- coding: utf-8 -*-
"""巡检任务老 URL 兼容（V18 已并入 task_schedule，301/307 重定向）"""
from flask import (request, redirect, url_for)
from flask_login import login_required
from blueprints.ops import ops_bp


# ============================ 巡检任务（V18: 已并入 task_schedule，仅保留 URL 301 兼容） ============================
@ops_bp.route('/inspection-tasks')
@login_required
def inspection_task_list():
    """老列表 → 任务安排列表视图"""
    return redirect(url_for('task_schedule.list_view', **request.args), code=301)


@ops_bp.route('/inspection-tasks/<int:id>')
@login_required
def inspection_task_detail(id):
    """老详情 → task_schedule.task_detail"""
    return redirect(url_for('task_schedule.task_detail', task_id=id), code=301)


# ============================ 巡检任务（V18: 兼容 POST 重定向） ============================
@ops_bp.route('/inspection-tasks/add', methods=['POST'])
@login_required
def inspection_task_add():
    """老 add → quick_add（307 保留方法 + body）"""
    return redirect(url_for('task_schedule.quick_add'), code=307)


def _parse_date(s):
    """Helper: 解析 YYYY-MM-DD 字符串为 date，失败返回 None（保留给其他调用方）"""
    if not s:
        return None
    try:
        from datetime import datetime as _dt
        return _dt.strptime(s.strip(), '%Y-%m-%d').date()
    except Exception:
        return None


@ops_bp.route('/inspection-tasks/edit/<int:id>', methods=['POST'])
@login_required
def inspection_task_edit(id):
    """老 edit：仅支持改状态字段（其余字段已迁到任务安排详情页）"""
    new_status = (request.form.get('status') or '').strip()
    if new_status:
        return redirect(
            url_for('task_schedule.change_status_form', task_id=id, status=new_status),
            code=307,
        )
    return redirect(url_for('task_schedule.task_detail', task_id=id))


@ops_bp.route('/inspection-tasks/delete/<int:id>', methods=['POST'])
@login_required
def inspection_task_delete(id):
    """老 delete → task_schedule.delete_task"""
    return redirect(url_for('task_schedule.delete_task', task_id=id), code=307)


