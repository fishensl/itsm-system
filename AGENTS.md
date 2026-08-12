# AGENTS.md — ITSM 运维管理系统（编码代理指南）

> 本文件面向代码代理/新开发者：项目结构、构建测试命令、必须遵守的约定。
> 人类向介绍见 README.md；变更历史见 CHANGELOG.md。

## 项目速览

基于 **Python 3.10+ / Flask 3.1** 的 IT 运维管理系统：客户/设备资产/巡检/工单/知识库/备件/销售管线/机柜/拓扑/AI 集成。
前端为 **Vue 3.5 + TypeScript + Element Plus** 单页应用，后端提供 JSON API；生产使用 PostgreSQL、Gunicorn + systemd 部署，SQLite 仅用于开发/测试显式配置。

## 目录结构（2026-07 重构后）

```
app.py                  # 应用工厂 create_app() / 扩展实例 / register_routes / init_db（仅 ~325 行）
wsgi.py                 # Gunicorn 入口：create_app() + init_db(app)
config.py               # 配置、日志（RotatingFileHandler）、安全头
frontend/               # Vue 3 SPA（唯一 UI；/app/* 前缀；CI 构建发布）
  src/api/              #   模块化 API 封装（axios，统一契约 {code,data,message}）
  src/stores/           #   Pinia：user(权限) / ui(主题/侧栏/toast)
  src/views/            #   页面（devices/tickets/inspections/customers/taskBoard/knowledge/
                        #   faults/reports/spare/sales/rack/topology/tools/system/...）
  src/components/       #   DataTable(桌面表格+移动端卡片) / GlobalSearch / NotificationBell
views/                  # 主应用视图（app.register_routes 集中注册，端点名无蓝图前缀）
  dashboard.py          #   首页仪表盘 + 工作台偏好 API
  auth.py               #   登录/登出/自助改密
  admin_users.py        #   用户管理/权限对照/AI 配置
  system.py             #   系统概览/schema 修复/侧栏/导入模板下载/客户列表
models/                 # 模型包（base.py 持 db 单例；__init__ 全量 re-export）
  base.py               #   db = SQLAlchemy()
  user.py customer.py device.py inspection.py ticket.py knowledge.py
  spare.py sales.py misc.py rack.py notification.py audit.py
blueprints/             # 业务蓝图（register_blueprints 统一注册）
  asset/                #   包：devices/dicts/firmwares/config_backups（蓝图名 asset）
  ops/                  #   包：inspections/tickets/faults/knowledge/templates/reports/...（蓝图名 ops）
  vue_api.py            #   Vue SPA 核心 API（auth/sidebar/dashboard/设备/工单/看板/通知/搜索）
  vue_api_ops.py        #   Vue API：知识库/故障/报告
  vue_api_sales.py      #   Vue API：备件/销售
  vue_api_asset.py      #   Vue API：机柜（兼容命名空间 /api/v2/rack/*）/拓扑/工具
  vue_api_sys.py        #   Vue API：用户/RBAC/部门/审计日志/系统概览（audit_log 写表辅助）
  customer.py sales.py spare.py rack.py topology.py rbac.py backup.py
  task_schedule.py task_dispatch.py(仅301/307兼容) contract_tasks.py drafts.py
  departments.py categories.py tools.py
services/               # 业务服务层（@transaction + ServiceError；不接触 request）
utils/                  # 工具层
  permission.py         #   RBAC：PERMISSION_MAP（53 权限码）+ 角色模板 + 进程级缓存
  constants.py          #   状态值单一真源（工单/巡检/审核/商机/合同/项目...）
  json_fields.py        #   JSON Text 字段读写边界（parse_json/dumps_json）
  decorators.py         #   api_view（CSRF 豁免标记）+ form_commit（表单写操作封装）
  crypto.py             #   Fernet 加解密（密钥在项目根 .secret.key）
  permission.py / pagination.py / upload.py / excel_export.py / report_generator.py ...
migrations/             # Alembic 迁移（init_db 启动时自动 upgrade）
tests/                  # pytest（425+ 用例；conftest 模块级 app + 用例级清库重播种）
scripts/                # 部署运维 + 数据脚本（faults_to_tickets.py / rotate_secret_key.py）
domain_metadata/        # 列表/详情/表单/导出字段注册表（跨层单一真源）
static/                 # 静态资源（drawio vendor ~21MB 勿动；static/app=Vue产物）
```

## Vue SPA（/app/*，唯一 UI）

- 技术栈：Vue 3.5 + TS + Element Plus + Pinia + Vite；开发 `cd frontend && npm run dev`（proxy → :5000）
- **统一响应契约**：`{code:0,data,message}` / `{code:1,message}`；前端 `request()` 自动解包、401 跳登录
- **API 命名空间**：新接口优先沿用模块现有 `/api/*` 或兼容命名空间 `/api/v2/*`
- **新模块流程**：`blueprints/vue_api_*.py` 追加路由（复用 vue_api_bp）→ `frontend/src/api/*.ts` → `frontend/src/views/*` → router 注册（meta.perm）→ `tests/test_vue_api_*.py`
- **列表页**统一用 `DataTable` 组件（列配置驱动，移动端自动卡片化）
- **字段一致性**：业务字段必须先登记到 `domain_metadata/`，列表、详情、表单与导出从相同 schema/profile 派生，禁止各自维护标签与列集合
- **审计**：敏感操作（设备密码/删除、工单删除、用户管理等）经 `vue_api_sys.audit_log()` 写 audit_logs 表，admin 在 `/app/system/audit` 查询
- **部署**：CI 构建 dist → GitHub Release `vue-dist` → update.sh 拉取解压 `static/app/`；无 Release 产物时必须本地构建，不再回退 SSR

## 常用命令

```bash
# 启动（开发）
python app.py                      # create_app + init_db + 内建服务器 :5000

# 测试（隔离 venv）
python -m venv .venv --system-site-packages
.venv/Scripts/pip install -r requirements-dev.txt    # Windows
.venv/Scripts/python -m pytest tests/                # 全量（~85s）
.venv/Scripts/python -m pytest tests/test_ticket_service.py  # 单模块

# 代码检查（CI 门禁：只允许 F 系列真实问题）
.venv/Scripts/python -m ruff check .

# 数据库迁移（启动时自动执行；手动：）
flask db upgrade

# 数据脚本
python scripts/faults_to_tickets.py           # 旧故障→工单 预览（--apply 执行）
python scripts/rotate_secret_key.py           # 密钥轮换 预览（--apply 执行）
```

## 必须遵守的约定

### 分层

- **路由层**（views/ blueprints/）：只做参数接收、权限装饰、调 service、返回统一 JSON；`/login` 等遗留地址仅保留 Vue 302 兼容壳。
- **服务层**（services/）：业务规则；`@transaction` 自动 commit/rollback；失败抛 `ServiceError`。
- **模型层**（models/）：瘦模型，无状态机、无 commit 副作用。

### 写操作

新功能统一使用 JSON API 与 service 事务，不新增 Jinja 表单或 SSR 页面。遗留兼容写路由维护时使用
`@form_commit(...)`；保存后的副作用（如合同自动生成任务）放 service 或明确的 after 钩子。

### 权限

- 装饰器三段栈：`@login_required` → `@require_permission('域:操作')` → 视图。
- 权限码集中在 `utils/permission.py: PERMISSION_MAP`；新增权限码需同步角色模板与 `seed_permissions`（幂等）。
- 敏感操作（查看明文密码 `device:reveal`、删除报告 `report:delete`、删除工单）**必须写审计日志**
  （操作人/对象/IP，current_app.logger.info）。
- API 请求未登录/无权限自动返回 JSON 401/403；Vue 路由负责登录跳转，遗留页面 URL 仅重定向到 SPA。

### CSRF 策略（全站统一）

- Flask 在 `csrf_token` cookie 中同步 token；前端 `utils/request.ts` 为非 GET 请求自动带 `X-CSRFToken` 头。
- 遗留兼容表单仍需显式提交 `csrf_token`，禁止为迁移方便扩大豁免范围。
- **禁止蓝图级 CSRF 豁免**；仅接收外部回调的端点用 `@api_view` 显式豁免。
- 登录路由豁免（未登录用户无法持 token）但有限流。

### 状态值

用 `utils/constants.py` 的常量与集合，**禁止散落裸字符串**；service 写入边界用
`_check_status`/集合校验（非法值直接 ServiceError）。工单状态机转换表在 `services/ticket_service.py`。

### JSON Text 字段（~25 处 db.Text）

读写走 `utils/json_fields.py: parse_json/dumps_json`；禁止 `len(json_str)`（是字符数不是条数！）。

### 密文与密钥

- 设备密码/凭证/AI Key 用 `utils/crypto.py` Fernet 加密入库（`*_encrypted` 列）。
- **明文不下发**：设备 JSON/导出默认不含明文；查看走 `POST /api/devices/<id>/reveal-password`
  （device:reveal 权限 + 审计）。
- `.secret.key` 与数据库必须同时备份；轮换用 `scripts/rotate_secret_key.py`。
- 用户密码：werkzeug 哈希；旧 pbkdf2 在登录成功时透明升级为 scrypt（views/auth.login）。

### 数据库

- schema 变更**必须**写 Alembic 迁移（migrations/versions/，幂等、先查后改）；models/ 同步声明。
- 高频过滤列补索引（参照迁移 f7a8b9c0d1e2）。
- 查询注意 N+1：列表渲染前用 joinedload/selectinload 预加载关联。

### 测试

- 任何行为变更必须同步测试；service 层优先（内存快、覆盖状态机/FIFO/审核流）。
- conftest 提供 admin_client/op_client/sales_client/viewer_client 四角色客户端。
- CSRF 相关用例参考 tests/test_csrf.py（独立 app 实例开启 WTF_CSRF_ENABLED）。

## 部署

- 生产：`gunicorn wsgi:app`（scripts/itsm.service），更新 `sudo bash scripts/update.sh`，
  回滚 `scripts/rollback.sh`，备份 `scripts/backup.sh`（含 .secret.key）。
- 生产必须设置 `ITSM_SECRET_KEY`（未设置且 ITSM_ENV=production 时拒绝启动）。

## 勿动清单

- `static/vendor/`（drawio ~21MB、Bootstrap、ECharts 第三方库）
- `instance/`、`logs/`、`reports/`、`uploads/`、`backups/`（运行时数据，已 gitignore）
- `.secret.key`（运行时密钥，泄露=全部密文可解）
