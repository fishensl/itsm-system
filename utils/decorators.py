"""共享装饰器"""
from functools import wraps

from flask import current_app, flash, redirect, url_for

from models import db


def api_view(func):
    """标记为 API 端点：自动豁免 CSRF

    Flask-WTF 的 CSRFProtect.exempt(func) 实质上就是设置 func.__csrf_exempt__ = True，
    此处直接设置该属性，避免在模块导入阶段（无 app context）调用 current_app。
    """
    func.__csrf_exempt__ = True
    return func


def form_commit(success, redirect_endpoint, fail, after=None):
    """表单写操作统一封装（替代 sales/spare 等蓝图中 30+ 份同构 try/except 代码）。

    视图函数只写业务调用（可返回结果供 after 使用），装饰器负责：
    异常时 rollback + logger.exception + flash(fail) → 重定向；
    成功时 flash(success) → 重定向。

    :param success: 成功消息 str，或 callable(result)->str
    :param redirect_endpoint: 重定向端点（url_for 参数）
    :param fail: 失败兜底消息（异常时 flash(str(e) or fail)）
    :param after: 可选钩子 callable(result)->str，返回值追加到成功消息；
                  用于"保存后副作用"（如合同自动生成巡检任务），钩子异常仅记日志不阻塞主流程
    """
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                result = f(*args, **kwargs)
            except Exception as e:
                db.session.rollback()
                current_app.logger.exception('%s: %r', fail, e)
                flash(str(e) or fail, 'danger')
                return redirect(url_for(redirect_endpoint))
            msg = success(result) if callable(success) else success
            if after is not None:
                try:
                    msg += after(result) or ''
                except Exception:
                    current_app.logger.exception('%s（后置处理失败）', fail)
            flash(msg, 'success')
            return redirect(url_for(redirect_endpoint))
        return wrapper
    return deco
