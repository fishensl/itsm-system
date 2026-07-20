"""合同自动巡检任务蓝图"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required
from models import Contract, InspectionTask
from utils.permission import require_permission

contract_task_bp = Blueprint('contract_tasks', __name__)


@contract_task_bp.route('/')
@login_required
@require_permission('contract_auto:manage')
def contract_task_list():
    """合同巡检配置列表 — 显示所有设置了自动巡检频率的合同"""
    contracts = Contract.query.filter(
        Contract.inspection_frequency != '',
        Contract.inspection_frequency.isnot(None)
    ).order_by(Contract.id.desc()).all()
    all_contracts = Contract.query.order_by(Contract.id.desc()).all()
    # 模板下拉：新任务模板（旧模板仅存于历史合同，只读回退）
    from models import InspectionTaskTemplate
    templates = InspectionTaskTemplate.query.filter_by(is_active=True)\
        .order_by(InspectionTaskTemplate.name).all()
    return render_template('contract_tasks/list.html',
                           contracts=contracts, all_contracts=all_contracts, templates=templates)


@contract_task_bp.route('/generate', methods=['POST'])
@login_required
@require_permission('contract_auto:manage')
def generate_tasks():
    """手动触发自动生成巡检任务"""
    from utils.auto_task_generator import generate_contract_tasks
    contract_id = request.form.get('contract_id', type=int)
    to_date_str = request.form.get('to_date', '')

    try:
        if to_date_str:
            from datetime import datetime
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        else:
            from datetime import date
            to_date = date.today()

        generated = generate_contract_tasks(contract_id=contract_id, to_date=to_date)
        flash(f'已生成 {len(generated)} 个巡检任务', 'success')
    except Exception as e:
        current_app.logger.exception('生成合同任务失败: contract_id=%s', contract_id)
        flash(f'生成失败：{str(e)}', 'danger')

    return redirect(url_for('contract_tasks.contract_task_list'))


@contract_task_bp.route('/preview/<int:contract_id>')
@login_required
@require_permission('contract_auto:manage')
def preview_tasks(contract_id):
    """预览将生成的任务（干跑，不入库）"""
    from utils.auto_task_generator import generate_contract_tasks
    try:
        generated = generate_contract_tasks(contract_id=contract_id, dry_run=True)
        return jsonify({'success': True, 'tasks': generated, 'count': len(generated)})
    except Exception as e:
        current_app.logger.exception('预览合同任务失败: contract_id=%s', contract_id)
        return jsonify({'success': False, 'error': str(e)})


@contract_task_bp.route('/api/contracts/<int:contract_id>/generated-tasks')
@login_required
@require_permission('contract_auto:manage')
def api_contract_tasks(contract_id):
    """获取合同关联的自动生成任务"""
    tasks = InspectionTask.query.filter_by(
        contract_id=contract_id,
        source='合同自动生成'
    ).order_by(InspectionTask.planned_start).all()
    result = [{
        'id': t.id,
        'title': t.title,
        'status': t.status,
        'planned_start': t.planned_start.strftime('%Y-%m-%d') if t.planned_start else '',
        'planned_end': t.planned_end.strftime('%Y-%m-%d') if t.planned_end else '',
        'assigned_to': t.assigned_to_user_id,
    } for t in tasks]
    return jsonify(result)