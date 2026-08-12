"""蓝图包 — 注册所有新增模块"""
from blueprints.departments import dept_bp
# V17: task_dispatch 已并入 task_schedule，仅保留 URL 兼容重定向
from blueprints.task_dispatch import dispatch_bp
from blueprints.contract_tasks import contract_task_bp
from blueprints.drafts import draft_bp
from blueprints.spare import spare_bp
from blueprints.customer import customer_bp
from blueprints.asset import asset_bp
from blueprints.ops import ops_bp
from blueprints.rack import rack_bp
from blueprints.tools import tools_bp
from blueprints.topology import topology_bp
from blueprints.task_schedule import task_schedule_bp
from blueprints.vue_api import vue_api_bp
from blueprints.vue_api_ops import vue_api_bp as _vb_ops  # noqa: F401 (注册路由副作用)
from blueprints.vue_api_sales import vue_api_bp as _vb_sales  # noqa: F401
from blueprints.vue_api_asset import vue_api_bp as _vb_asset  # noqa: F401
from blueprints.vue_api_sys import vue_api_bp as _vb_sys  # noqa: F401
from blueprints.vue_api_auth import vue_api_bp as _vb_auth  # noqa: F401


def register_blueprints(app):
    # CSRF 策略（全站统一）：
    # - 不做蓝图级豁免。Vue axios 拦截器从 csrf_token cookie 读取 token，
    #   为 drafts/rack/rbac 等 JSON API 的非 GET 请求附加 X-CSRFToken。
    # - 遗留兼容 POST 表单仍需显式提交 csrf_token，保持防越权提权保护。
    # - 仅个别需接收外部 POST 的端点用 @api_view 显式豁免（如登录态外的回调）。
    # 不要再把 customer_bp/asset_bp 等加入 exempt，否则普通 POST 表单也被绕过

    app.register_blueprint(dept_bp, url_prefix='/departments')
    app.register_blueprint(dispatch_bp, url_prefix='/task-dispatch')
    app.register_blueprint(contract_task_bp, url_prefix='/contract-tasks')
    app.register_blueprint(draft_bp, url_prefix='/api/drafts')
    # 备件管理：URL 前缀为空
    app.register_blueprint(spare_bp)
    # 客户管理（客户/地区）：URL 前缀为空
    app.register_blueprint(customer_bp)
    # 资产管理（设备）：URL 前缀为空
    app.register_blueprint(asset_bp)
    # 运维管理（巡检/工单/故障/知识库/报表/巡检任务/设备模板/任务模板）：URL 前缀为空
    app.register_blueprint(ops_bp)
    # V6.1: 机柜管理 + 常用工具
    app.register_blueprint(rack_bp)
    app.register_blueprint(tools_bp)
    # V20: 拓扑图（从 app.py 迁移为蓝图 + 在线绘制）
    app.register_blueprint(topology_bp)
    # V16: 任务安排看板（Excel 导入 + 三视图）
    app.register_blueprint(task_schedule_bp)
    # V2.0: Vue SPA API（统一响应契约，随迁随化）
    app.register_blueprint(vue_api_bp)
