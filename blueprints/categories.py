"""单位类别管理蓝图"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, CustomerCategory
from utils.permission import require_permission

category_bp = Blueprint('categories', __name__)


@category_bp.route('/')
@login_required
@require_permission('category:view')
def category_list():
    categories = CustomerCategory.query.order_by(CustomerCategory.sort_order, CustomerCategory.id).all()
    return render_template('customer_categories/list.html', categories=categories)


@category_bp.route('/add', methods=['POST'])
@login_required
@require_permission('category:edit')
def category_add():
    name = request.form.get('name', '').strip()
    sort_order = request.form.get('sort_order', 0, type=int)
    if not name:
        flash('类别名称不能为空', 'danger')
        return redirect(url_for('categories.category_list'))
    if CustomerCategory.query.filter_by(name=name).first():
        flash('类别名称已存在', 'danger')
        return redirect(url_for('categories.category_list'))
    cat = CustomerCategory(name=name, sort_order=sort_order)
    db.session.add(cat)
    db.session.commit()
    flash('类别已添加', 'success')
    return redirect(url_for('categories.category_list'))


@category_bp.route('/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('category:edit')
def category_edit(id):
    cat = CustomerCategory.query.get_or_404(id)
    cat.name = request.form.get('name', '').strip() or cat.name
    cat.sort_order = request.form.get('sort_order', cat.sort_order, type=int)
    db.session.commit()
    flash('类别已更新', 'success')
    return redirect(url_for('categories.category_list'))


@category_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('category:edit')
def category_delete(id):
    cat = CustomerCategory.query.get_or_404(id)
    from models import Customer
    count = Customer.query.filter_by(category_id=id).count()
    if count > 0:
        flash(f'类别「{cat.name}」下有 {count} 个客户，无法删除', 'danger')
        return redirect(url_for('categories.category_list'))
    db.session.delete(cat)
    db.session.commit()
    flash('类别已删除', 'success')
    return redirect(url_for('categories.category_list'))