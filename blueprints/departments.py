"""部门管理蓝图（SSR 页面与 CRUD 已由 Vue SPA /api/departments/* 接管，仅保留树 API）"""
from flask import Blueprint, jsonify
from flask_login import login_required
from sqlalchemy.orm import joinedload
from models import Department
from utils.permission import require_permission

dept_bp = Blueprint('departments', __name__)


@dept_bp.route('/api/tree')
@login_required
@require_permission('department:view')
def api_dept_tree():
    """返回部门树 JSON"""
    departments = Department.query.options(joinedload(Department.head))\
        .order_by(Department.sort_order, Department.id).all()
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
