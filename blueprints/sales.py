# -*- coding: utf-8 -*-
"""销售管理蓝图：商机 / 报价单 / 合同 / 项目

所有业务规则下沉到 services/sales_service.py，路由层只做参数接收和模板渲染。
写操作统一走 utils.decorators.form_commit（try/except/rollback/flash/redirect 封装）。
"""
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from models import Opportunity, Quotation, Contract, Project, Customer
from services.sales_service import (
    create_opportunity, update_opportunity, delete_opportunity,
    create_quotation, update_quotation, delete_quotation,
    create_contract, update_contract, delete_contract,
    create_project, update_project, delete_project,
)
from utils.decorators import form_commit
from utils.permission import require_permission

sales_bp = Blueprint('sales', __name__)


def _gen_contract_tasks_msg(c):
    """合同保存后自动生成巡检任务（幂等；作为 form_commit after 钩子，失败仅记日志）"""
    if c and c.inspection_frequency and c.inspection_template_id and c.auto_generate_tasks:
        from utils.auto_task_generator import generate_contract_tasks
        generated = generate_contract_tasks(contract_id=c.id)
        if generated:
            return f'，已生成 {len(generated)} 个巡检任务'
    return ''


def _me():
    return current_user.realname or current_user.username


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
@form_commit('商机已创建', 'sales.opportunity_list', '商机创建失败')
def opportunity_add():
    create_opportunity(request.form.to_dict(), _me())


@sales_bp.route('/opportunities/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:edit')
@form_commit('已更新', 'sales.opportunity_list', '商机更新失败')
def opportunity_edit(id):
    update_opportunity(id, request.form.to_dict())


@sales_bp.route('/opportunities/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:delete')
@form_commit('已删除', 'sales.opportunity_list', '商机删除失败')
def opportunity_delete(id):
    delete_opportunity(id)


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
@form_commit('报价单已创建', 'sales.quotation_list', '报价单创建失败')
def quotation_add():
    create_quotation(request.form.to_dict(), _me())


@sales_bp.route('/quotations/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:edit')
@form_commit('已更新', 'sales.quotation_list', '报价单更新失败')
def quotation_edit(id):
    update_quotation(id, request.form.to_dict())


@sales_bp.route('/quotations/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:delete')
@form_commit('已删除', 'sales.quotation_list', '报价单删除失败')
def quotation_delete(id):
    delete_quotation(id)


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
@form_commit('合同已创建', 'sales.contract_list', '合同创建失败', after=_gen_contract_tasks_msg)
def contract_add():
    return create_contract(request.form.to_dict(), _me())


@sales_bp.route('/contracts/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:edit')
@form_commit('已更新', 'sales.contract_list', '合同更新失败', after=_gen_contract_tasks_msg)
def contract_edit(id):
    return update_contract(id, request.form.to_dict())


@sales_bp.route('/contracts/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:delete')
@form_commit('已删除', 'sales.contract_list', '合同删除失败')
def contract_delete(id):
    delete_contract(id)


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
@form_commit('项目已创建', 'sales.project_list', '项目创建失败')
def project_add():
    create_project(request.form.to_dict(), _me())


@sales_bp.route('/projects/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:edit')
@form_commit('已更新', 'sales.project_list', '项目更新失败')
def project_edit(id):
    update_project(id, request.form.to_dict())


@sales_bp.route('/projects/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('sales:delete')
@form_commit('已删除', 'sales.project_list', '项目删除失败')
def project_delete(id):
    delete_project(id)
