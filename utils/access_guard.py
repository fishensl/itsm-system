# -*- coding: utf-8 -*-
"""内外网访问隔离守卫（before_request 全局注册）

外网（非可信网段）仅放行工单/故障处置流程：登录改密、站内通知、工单/故障
增删改查+挂起/进展/审核/照片、SPA 入口与静态资源；其余敏感模块
（客户/设备/合同/销售/备件/巡检/用户/报表/AI/通知渠道配置等）一律拒绝。

- API 请求 → 403 JSON {code:1, message}
- 页面请求 → 302 到 /app/login

未配置可信网段（全部内网）时本守卫不生效（兼容存量零配置部署）。
"""
from flask import request, jsonify, redirect, abort
from flask_login import current_user

# 外网放行的路径前缀（其余 /api/* 一律拒绝）
_EXTERNAL_API_PREFIXES = (
    '/api/auth/',      # 登录/改密/侧栏/我的信息
    '/api/notifications',  # 站内通知铃铛
    '/api/tickets',    # 工单主流程
    '/api/faults',     # 故障主流程
)
# 页面/静态前缀（SPA 入口 + 静态资源，照片等上传文件在 static/uploads/ 下）
_EXTERNAL_PAGE_PREFIXES = ('/app/', '/static/', '/uploads/')
_EXTERNAL_NAKED_PATHS = {'/', '/login', '/logout', '/healthz'}

# 放行前缀内的敏感子路径（外网仍拒绝）
_EXTERNAL_BLOCKED_FRAGMENTS = (
    '/export',          # 工单/故障导出（批量数据外泄面）
    '/export-bundle',
)
# 外网禁止的 HTTP 方法（针对具体资源的破坏性操作）
_EXTERNAL_BLOCKED_METHODS = ('DELETE',)


def _external_blocked(path, method):
    """外网请求命中敏感子路径/方法 → 拒绝"""
    if method in _EXTERNAL_BLOCKED_METHODS and '/api/' in path:
        return True
    for frag in _EXTERNAL_BLOCKED_FRAGMENTS:
        if frag in path:
            return True
    return False


def _external_allowed(path, method):
    """外网请求是否放行"""
    if _external_blocked(path, method):
        return False
    for prefix in _EXTERNAL_API_PREFIXES:
        if path.startswith(prefix):
            return True
    for prefix in _EXTERNAL_PAGE_PREFIXES:
        if path.startswith(prefix):
            return True
    if path in _EXTERNAL_NAKED_PATHS:
        return True
    return False


def _deny(message='该功能仅限内网/VPN 访问'):
    if '/api/' in request.path:
        return jsonify({'code': 1, 'message': message}), 403
    return redirect('/app/login')


def register_access_guard(app):
    """注册全局 before_request：外网拒绝敏感路径（未配置网段时零生效）"""
    from utils.access_control import is_internal_request

    @app.before_request
    def _access_guard():
        # 业务上传文件不能继承 Flask /static 的匿名直出行为。返回 404 而不是
        # 401/302，避免向匿名请求确认备份、报告或照片是否存在。
        if request.path.startswith('/static/uploads/') and not current_user.is_authenticated:
            abort(404)
        # 静态资源（drawio/图标等大文件）不参与判定，避免每请求读配置
        if request.path.startswith('/static/vendor/') or request.path.startswith('/static/stencils/'):
            return None
        try:
            if is_internal_request():
                return None
        except Exception:
            app.logger.exception('可信网段判定失败')
            # SPA 壳与外网工单流程维持可用；其余敏感 API 在判定异常时 fail closed。
            if request.path.startswith('/api/') and not _external_allowed(
                    request.path, request.method):
                return _deny('访问控制状态异常，敏感接口已临时关闭')
            return None
        if _external_allowed(request.path, request.method):
            return None
        return _deny()
