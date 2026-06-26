# -*- coding: utf-8 -*-
"""销售管理蓝图：商机 / 报价单 / 合同 / 项目

所有业务规则下沉到 services/sales_service.py，路由层只做参数接收和模板渲染。
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required
from models import Opportunity, Quotation, Contract, Project, Customer, db
from services.sales_service import (
    create_opportunity, update_opportunity, delete_opportunity,
    create_quotation, update_quotation, delete_quotation,
    create_contract, update_contract, delete_contract,
    create_project, update_project, delete_project,
)
from utils.permission import require_permission

sales_bp = Blueprint('sales', __name__)


# ============================ 商机 ============================
@sales_bp.route('/opportunities')
@login_required
@require_permission('sales:view')
def opportunity_list():
    opps = Opportunity.query.order_by(Opportunity.id.desc()).all()
    customers = Customer.query.order_by(Customer.name).all()
    return render_template('opportunities/list.html', opps=opps, customers=customers)


@sales_bp.route('/opportunities/add', methods=['POST'])
@login_required
@require_permission('sales:add')
def opportunity_add():
    from flask_login import current_user
    try:
        create_opportunity(request.form.to_dict(), current_user.realname or current_user.username)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '商机创建失败', 'danger')
        return redirect(url_for('sales.opportunity_list'))
    flash('商机已创建', 'success')
    return redirect(url_for('sales.opportunity_list'))


@sales_bp.route('/opportunities/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:edit')
def opportunity_edit(id):
    try:
        update_opportunity(id, request.form.to_dict())
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '商机更新失败', 'danger')
        return redirect(url_for('sales.opportunity_list'))
    flash('已更新', 'success')
    return redirect(url_for('sales.opportunity_list'))


@sales_bp.route('/opportunities/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:delete')
def opportunity_delete(id):
    try:
        delete_opportunity(id)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '商机删除失败', 'danger')
        return redirect(url_for('sales.opportunity_list'))
    flash('已删除', 'success')
    return redirect(url_for('sales.opportunity_list'))


# ============================ 报价单 ============================
@sales_bp.route('/quotations')
@login_required
@require_permission('sales:view')
def quotation_list():
    quotes = Quotation.query.order_by(Quotation.id.desc()).all()
    customers = Customer.query.order_by(Customer.name).all()
    return render_template('quotations/list.html', quotes=quotes, customers=customers)


@sales_bp.route('/quotations/add', methods=['POST'])
@login_required
@require_permission('sales:add')
def quotation_add():
    from flask_login import current_user
    try:
        create_quotation(request.form.to_dict(), current_user.realname or current_user.username)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '报价单创建失败', 'danger')
        return redirect(url_for('sales.quotation_list'))
    flash('报价单已创建', 'success')
    return redirect(url_for('sales.quotation_list'))


@sales_bp.route('/quotations/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:edit')
def quotation_edit(id):
    try:
        update_quotation(id, request.form.to_dict())
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '报价单更新失败', 'danger')
        return redirect(url_for('sales.quotation_list'))
    flash('已更新', 'success')
    return redirect(url_for('sales.quotation_list'))


@sales_bp.route('/quotations/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:delete')
def quotation_delete(id):
    try:
        delete_quotation(id)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '报价单删除失败', 'danger')
        return redirect(url_for('sales.quotation_list'))
    flash('已删除', 'success')
    return redirect(url_for('sales.quotation_list'))


# ============================ 合同 ============================
@sales_bp.route('/contracts')
@login_required
@require_permission('sales:view')
def contract_list():
    contracts = Contract.query.order_by(Contract.id.desc()).all()
    customers = Customer.query.order_by(Customer.name).all()
    return render_template('contracts/list.html', contracts=contracts, customers=customers)


@sales_bp.route('/contracts/add', methods=['POST'])
@login_required
@require_permission('sales:add')
def contract_add():
    from flask_login import current_user
    try:
        c = create_contract(request.form.to_dict(), current_user.realname or current_user.username)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '合同创建失败', 'danger')
        return redirect(url_for('sales.contract_list'))
    # 新合同：若配置了巡检频率 + 模板，立即按合同自动生成历史和未来任务（失败不阻塞）
    gen_msg = ''
    if c and c.inspection_frequency and c.inspection_template_id and c.auto_generate_tasks:
        try:
            from utils.auto_task_generator import generate_contract_tasks
            generated = generate_contract_tasks(contract_id=c.id)
            if generated:
                gen_msg = f'，已生成 {len(generated)} 个巡检任务'
        except Exception:
            current_app.logger.exception('合同 %s 任务自动生成失败', c.id)
    flash(f'合同已创建{gen_msg}', 'success')
    return redirect(url_for('sales.contract_list'))


@sales_bp.route('/contracts/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:edit')
def contract_edit(id):
    try:
        update_contract(id, request.form.to_dict())
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '合同更新失败', 'danger')
        return redirect(url_for('sales.contract_list'))
    # 合同更新后：若打开了自动巡检 + 设置了频率/模板，补齐尚未生成的任务（幂等）
    gen_msg = ''
    try:
        from models import Contract
        c = Contract.query.get(id)
        if c and c.inspection_frequency and c.inspection_template_id and c.auto_generate_tasks:
            from utils.auto_task_generator import generate_contract_tasks
            generated = generate_contract_tasks(contract_id=c.id)
            if generated:
                gen_msg = f'，已生成 {len(generated)} 个巡检任务'
    except Exception:
        current_app.logger.exception('合同 %s 任务自动生成失败', id)
    flash(f'已更新{gen_msg}', 'success')
    return redirect(url_for('sales.contract_list'))


@sales_bp.route('/contracts/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:delete')
def contract_delete(id):
    try:
        delete_contract(id)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '合同删除失败', 'danger')
        return redirect(url_for('sales.contract_list'))
    flash('已删除', 'success')
    return redirect(url_for('sales.contract_list'))


# ============================ 项目 ============================
@sales_bp.route('/projects')
@login_required
@require_permission('sales:view')
def project_list():
    projects = Project.query.order_by(Project.id.desc()).all()
    customers = Customer.query.order_by(Customer.name).all()
    return render_template('projects/list.html', projects=projects, customers=customers)


@sales_bp.route('/projects/add', methods=['POST'])
@login_required
@require_permission('sales:add')
def project_add():
    from flask_login import current_user
    try:
        create_project(request.form.to_dict(), current_user.realname or current_user.username)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '项目创建失败', 'danger')
        return redirect(url_for('sales.project_list'))
    flash('项目已创建', 'success')
    return redirect(url_for('sales.project_list'))


@sales_bp.route('/projects/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:edit')
def project_edit(id):
    try:
        update_project(id, request.form.to_dict())
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '项目更新失败', 'danger')
        return redirect(url_for('sales.project_list'))
    flash('已更新', 'success')
    return redirect(url_for('sales.project_list'))


@sales_bp.route('/projects/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:delete')
def project_delete(id):
    try:
        delete_project(id)
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("更新失败：%s", repr(e))
        flash(str(e) or '项目删除失败', 'danger')
        return redirect(url_for('sales.project_list'))
    flash('已删除', 'success')
    return redirect(url_for('sales.project_list'))
