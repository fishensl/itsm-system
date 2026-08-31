# -*- coding: utf-8 -*-
"""凭据传输信封 challenge API。"""
from flask import request
from flask_login import login_required

from app import limiter
from blueprints.vue_api import fail, ok, vue_api_bp
from services.base import ServiceError
from services.credential_envelope_service import issue_challenge
from utils.operation_token import require_op_token


@vue_api_bp.route('/api/security/credential-envelope/challenge', methods=['POST'])
@limiter.limit('30 per minute;120 per hour')
@login_required
@require_op_token()
def api_credential_envelope_challenge():
    data = request.get_json(silent=True) or {}
    if data.get('version') != 1:
        return fail('不支持的凭据传输信封版本', 400)
    try:
        result = issue_challenge(
            str(data.get('purpose') or ''),
            data.get('client_public_key'),
            target_id=data.get('target_id'),
            history_id=data.get('history_id'),
            operation_token=request.headers.get('X-Operation-Token', ''),
        )
    except (ServiceError, ValueError) as exc:
        return fail(str(exc) or '凭据传输信封签发失败', 400)
    return ok(result)
