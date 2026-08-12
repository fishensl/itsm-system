# -*- coding: utf-8 -*-
"""Legacy bookmark shells; authentication is exclusively provided by Vue JSON APIs."""
from flask import redirect
from flask_login import logout_user, login_required
from app import csrf


@csrf.exempt
def login():
    """GET/POST compatibility shell; never accepts credentials."""
    return redirect('/app/login')


@login_required
def logout():
    logout_user()
    return redirect('/app/login')


# ==================== 自助改密兼容端点 ====================
# SSR 剥离后改密由 SPA 弹窗（/api/auth/change-password）承担。
# 旧书签/旧前端产物仍可能整页访问 /me/change_password —— 302 到 SPA 工作台，
# 用户可在右上角用户菜单弹窗改密，避免 404。
@login_required
def me_change_password():
    return redirect('/app/')
