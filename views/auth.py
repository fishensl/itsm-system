# -*- coding: utf-8 -*-
"""登录/登出（SSR 业务页已剥离：登录一律 302 到 SPA /app/login）"""
from flask import request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import db
from models import User
from app import csrf, limiter


# ---------- 登录 ----------
# 注意：@csrf.exempt 必须是最外层装饰器——Flask-Limiter 4.1 的 limit() 返回 RouteLimit
# 对象包装函数，若 exempt 在内层会因包装丢失豁免标记/身份，导致登录被 CSRF 拦截(400)。
@csrf.exempt  # 登录页对未登录用户开放，不能强制 CSRF
@limiter.limit('5 per minute;30 per hour', methods=['POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and not user.is_active:
            flash('该账号已停用，请联系管理员', 'danger')
            current_app.logger.warning(f'停用账号 [{username}] 尝试登录')
            return redirect(url_for('login'))
        if user and user.check_password(password):
            # 历史明文账号本次登录已就地升级为哈希（模型只打标记，这里显式提交）
            if getattr(user, '_plaintext_upgraded', False):
                db.session.commit()
                current_app.logger.info(f'用户 [{username}] 的明文密码已自动升级为哈希存储')
            elif user.needs_rehash():
                # 旧 pbkdf2 哈希透明升级为 scrypt（werkzeug 3 默认，零依赖）
                user.set_password(password)
                db.session.commit()
                current_app.logger.info(f'用户 [{username}] 密码哈希已升级 pbkdf2→scrypt')
            login_user(user)
            current_app.logger.info(f'用户 [{username}] 登录成功')
            return redirect(url_for('index'))
        flash('用户名或密码错误', 'danger')
        current_app.logger.warning(f'用户 [{username}] 登录失败')
    # SSR 业务页已剥离：GET 与 POST 失败均跳转 SPA 登录页（历史书签/测试兼容表单 POST）
    return redirect('/app/login')


@login_required
def logout():
    current_app.logger.info(f'用户 [{current_user.username}] 登出')
    logout_user()
    return redirect(url_for('login'))
