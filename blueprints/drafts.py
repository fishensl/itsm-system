"""表单草稿自动保存蓝图"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import db, FormDraft
from datetime import datetime
import json

draft_bp = Blueprint('drafts', __name__)


def _norm_related_id(raw):
    """related_id 统一为 int 或 None（前端 JSON 可能传字符串/'null'/空值）。

    修复 save 不转型入库、load 用 type=int 查询导致的类型不匹配隐患。
    """
    if raw in (None, '', 'null', 'undefined'):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@draft_bp.route('/save', methods=['POST'])
@login_required
def draft_save():
    """保存草稿"""
    data = request.get_json() or request.form
    form_type = data.get('form_type', '')
    related_id = _norm_related_id(data.get('related_id'))
    form_data = data.get('form_data_json', '{}')

    if not form_type:
        return jsonify({'success': False, 'error': 'form_type required'}), 400

    # 查找已有草稿
    existing = FormDraft.query.filter_by(
        user_id=current_user.id,
        form_type=form_type,
        related_id=related_id
    ).first()

    if existing:
        existing.form_data_json = form_data if isinstance(form_data, str) else json.dumps(form_data, ensure_ascii=False)
        existing.updated_at = datetime.utcnow()
    else:
        draft = FormDraft(
            user_id=current_user.id,
            form_type=form_type,
            related_id=related_id,
            form_data_json=form_data if isinstance(form_data, str) else json.dumps(form_data, ensure_ascii=False),
            updated_at=datetime.utcnow()
        )
        db.session.add(draft)

    db.session.commit()
    return jsonify({'success': True})


@draft_bp.route('/load', methods=['GET'])
@login_required
def draft_load():
    """加载草稿"""
    form_type = request.args.get('form_type', '')
    related_id = _norm_related_id(request.args.get('related_id'))

    if not form_type:
        return jsonify({'success': False, 'error': 'form_type required'}), 400

    draft = FormDraft.query.filter_by(
        user_id=current_user.id,
        form_type=form_type,
        related_id=related_id
    ).first()

    if draft:
        return jsonify({
            'success': True,
            'form_type': draft.form_type,
            'related_id': draft.related_id,
            'form_data_json': draft.form_data_json,
            'updated_at': draft.updated_at.isoformat() if draft.updated_at else ''
        })
    return jsonify({'success': True, 'form_data_json': '{}', 'updated_at': ''})


@draft_bp.route('/delete', methods=['DELETE', 'POST'])
@login_required
def draft_delete():
    """删除草稿"""
    data = request.get_json() or request.form
    form_type = data.get('form_type', '')
    related_id = _norm_related_id(data.get('related_id'))

    draft = FormDraft.query.filter_by(
        user_id=current_user.id,
        form_type=form_type,
        related_id=related_id
    ).first()

    if draft:
        db.session.delete(draft)
        db.session.commit()

    return jsonify({'success': True})


@draft_bp.route('/list', methods=['GET'])
@login_required
def draft_list():
    """我的草稿列表"""
    drafts = FormDraft.query.filter_by(user_id=current_user.id).order_by(FormDraft.updated_at.desc()).all()
    result = [{
        'id': d.id,
        'form_type': d.form_type,
        'related_id': d.related_id,
        'updated_at': d.updated_at.isoformat() if d.updated_at else '',
    } for d in drafts]
    return jsonify(result)