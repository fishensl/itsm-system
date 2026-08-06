"""合同自动巡检任务蓝图（SSR 页面/表单已由 Vue SPA /api/contract-tasks/* 接管，仅保留任务查询 API）"""
from flask import Blueprint, jsonify
from flask_login import login_required
from models import InspectionTask
from utils.permission import require_permission

contract_task_bp = Blueprint('contract_tasks', __name__)


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
