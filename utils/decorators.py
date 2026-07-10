"""共享装饰器"""


def api_view(func):
    """标记为 API 端点：自动豁免 CSRF

    Flask-WTF 的 CSRFProtect.exempt(func) 实质上就是设置 func.__csrf_exempt__ = True，
    此处直接设置该属性，避免在模块导入阶段（无 app context）调用 current_app。
    """
    func.__csrf_exempt__ = True
    return func
