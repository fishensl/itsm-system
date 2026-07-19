# -*- coding: utf-8 -*-
"""登录/登出/自助改密"""
from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import db
from models import User
from app import csrf, limiter


# ---------- 登录 ----------
@limiter.limit('5 per minute;30 per hour', methods=['POST'])
@csrf.exempt  # 登录页对未登录用户开放，不能强制 CSRF
def login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and not user.is_active:
            flash('该账号已停用，请联系管理员', 'danger')
            current_app.logger.warning(f'停用账号 [{username}] 尝试登录')
            return render_template('login.html')
        if user and user.check_password(password):
            # 历史明文账号本次登录已就地升级为哈希（模型只打标记，这里显式提交）
            if getattr(user, '_plaintext_upgraded', False):
                db.session.commit()
                current_app.logger.info(f'用户 [{username}] 的明文密码已自动升级为哈希存储')
            login_user(user)
            current_app.logger.info(f'用户 [{username}] 登录成功')
            return redirect(url_for('index'))
        flash('用户名或密码错误', 'danger')
        current_app.logger.warning(f'用户 [{username}] 登录失败')
    return render_template('login.html')


@login_required
def logout():
    current_app.logger.info(f'用户 [{current_user.username}] 登出')
    logout_user()
    return redirect(url_for('login'))

# ==================== V13: 用户自助修改密码 ====================
@login_required
@limiter.limit('10 per hour')
def me_change_password():
    """登录用户自助修改密码（需校验原密码）"""
    if request.method == 'POST':
        old_pwd = request.form.get('old_password') or ''
        new_pwd = (request.form.get('new_password') or '').strip()
        confirm = (request.form.get('confirm_password') or '').strip()
        if not current_user.check_password(old_pwd):
            flash('原密码错误', 'danger')
            return redirect(url_for('me_change_password'))
        if len(new_pwd) < 6:
            flash('新密码长度至少 6 位', 'danger')
            return redirect(url_for('me_change_password'))
        if new_pwd != confirm:
            flash('两次输入的新密码不一致', 'danger')
            return redirect(url_for('me_change_password'))
        if new_pwd == old_pwd:
            flash('新密码不能与原密码相同', 'warning')
            return redirect(url_for('me_change_password'))
        current_user.set_password(new_pwd)
        db.session.commit()
        current_app.logger.info(f'用户 [{current_user.username}] 自助修改了密码')
        flash('密码已修改，请使用新密码重新登录', 'success')
        # 改完强制退出，让用户用新密码登录
        from flask_login import logout_user
        logout_user()
        return redirect(url_for('login'))
    return render_template('auth/change_password.html')


