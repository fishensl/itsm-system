"""部门管理蓝图"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Department, User
from utils.permission import require_permission

dept_bp = Blueprint('departments', __name__)


@dept_bp.route('/')
@login_required
@require_permission('department:view')
def dept_list():
    departments = Department.query.order_by(Department.sort_order, Department.id).all()
    users = User.query.filter(User.is_active == True).order_by(User.realname).all()
    # 构建树：顶级部门 + 其 children
    dept_map = {}
    for d in departments:
        dept_map[d.id] = {
            'id': d.id, 'name': d.name, 'parent_id': d.parent_id,
            'head_id': d.head_id, 'head_name': d.head.realname if d.head else '',
            'sort_order': d.sort_order,
            'member_count': len(d.members) if d.members else 0,
            'children': [],
        }
    tree = []
    for d in departments:
        node = dept_map[d.id]
        if d.parent_id and d.parent_id in dept_map:
            dept_map[d.parent_id]['children'].append(node)
        else:
            tree.append(node)
    return render_template('departments/list.html', tree=tree, all_depts=departments, users=users)


@dept_bp.route('/add', methods=['POST'])
@login_required
@require_permission('department:edit')
def dept_add():
    name = request.form.get('name', '').strip()
    parent_id = request.form.get('parent_id', type=int)
    head_id = request.form.get('head_id', type=int)
    sort_order = request.form.get('sort_order', 0, type=int)
    if not name:
        flash('部门名称不能为空', 'danger')
        return redirect(url_for('departments.dept_list'))
    if Department.query.filter_by(name=name).first():
        flash('部门名称已存在', 'danger')
        return redirect(url_for('departments.dept_list'))
    dept = Department(name=name, parent_id=parent_id, head_id=head_id, sort_order=sort_order)
    db.session.add(dept)
    db.session.commit()
    flash('部门已添加', 'success')
    return redirect(url_for('departments.dept_list'))


@dept_bp.route('/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('department:edit')
def dept_edit(id):
    dept = Department.query.get_or_404(id)
    dept.name = request.form.get('name', '').strip() or dept.name
    dept.parent_id = request.form.get('parent_id', type=int)
    dept.head_id = request.form.get('head_id', type=int)
    dept.sort_order = request.form.get('sort_order', dept.sort_order, type=int)
    db.session.commit()
    flash('部门已更新', 'success')
    return redirect(url_for('departments.dept_list'))


@dept_bp.route('/delete/<int:id>')
@login_required
@require_permission('department:edit')
def dept_delete(id):
    dept = Department.query.get_or_404(id)
    # 检查是否有成员
    member_count = User.query.filter_by(department_id=id).count()
    if member_count > 0:
        flash(f'部门「{dept.name}」下有 {member_count} 个成员，无法删除', 'danger')
        return redirect(url_for('departments.dept_list'))
    # 检查是否有子部门
    child_count = Department.query.filter_by(parent_id=id).count()
    if child_count > 0:
        flash(f'部门「{dept.name}」下有子部门，无法删除', 'danger')
        return redirect(url_for('departments.dept_list'))
    db.session.delete(dept)
    db.session.commit()
    flash('部门已删除', 'success')
    return redirect(url_for('departments.dept_list'))


@dept_bp.route('/api/tree')
@login_required
def api_dept_tree():
    """返回部门树 JSON"""
    departments = Department.query.order_by(Department.sort_order, Department.id).all()
    result = []
    for d in departments:
        head_name = d.head.realname if d.head else ''
        result.append({
            'id': d.id,
            'name': d.name,
            'parent_id': d.parent_id,
            'head_id': d.head_id,
            'head_name': head_name,
            'sort_order': d.sort_order,
        })
    return jsonify(result)