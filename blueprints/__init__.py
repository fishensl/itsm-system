"""蓝图包 — 注册所有新增模块"""
from blueprints.departments import dept_bp
from blueprints.categories import category_bp
# V17: task_dispatch 已并入 task_schedule，仅保留 URL 兼容重定向
from blueprints.task_dispatch import dispatch_bp
from blueprints.contract_tasks import contract_task_bp
from blueprints.drafts import draft_bp
from blueprints.sales import sales_bp
from blueprints.spare import spare_bp
from blueprints.customer import customer_bp
from blueprints.asset import asset_bp
from blueprints.ops import ops_bp
from blueprints.rack import rack_bp
from blueprints.tools import tools_bp
from blueprints.topology import topology_bp
from blueprints.rbac import rbac_bp
from blueprints.backup import backup_bp
from blueprints.task_schedule import task_schedule_bp


def register_blueprints(app):
    # drafts 是纯 API 蓝图（/api/drafts/*），整蓝图豁免 CSRF
    csrf_ext = app.extensions.get('csrf')
    if csrf_ext is not None:
        csrf_ext.exempt(draft_bp)
        # rack 蓝图的 /api/rack/* 端点也豁免 CSRF（前端用 fetch）
        csrf_ext.exempt(rack_bp)
        # 注：rbac 蓝图不再整体豁免 CSRF——其 fetch 已显式带 X-CSRFToken，
        #     普通 POST 表单经 base.html 自动注入 csrf_token，保持 CSRF 保护防越权提权
    # 注意：app.py 中的 /api/* 路由已通过 @api_view (= @csrf.exempt) 单独豁免
    # 不要再把 customer_bp/asset_bp 等加入 exempt，否则普通 POST 表单也被绕过

    app.register_blueprint(dept_bp, url_prefix='/departments')
    app.register_blueprint(category_bp, url_prefix='/customer-categories')
    app.register_blueprint(dispatch_bp, url_prefix='/task-dispatch')
    app.register_blueprint(contract_task_bp, url_prefix='/contract-tasks')
    app.register_blueprint(draft_bp, url_prefix='/api/drafts')
    # 销售管理（商机/报价/合同/项目）：URL 前缀为空
    app.register_blueprint(sales_bp)
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
    # V14: 角色/权限管理
    app.register_blueprint(rbac_bp, url_prefix='/rbac')
    # V15: 数据备份/恢复（admin）
    app.register_blueprint(backup_bp)
    # V16: 任务安排看板（Excel 导入 + 三视图）
    app.register_blueprint(task_schedule_bp)