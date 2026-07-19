# AGENTS.md — ITSM 运维管理系统（编码代理指南）

> 本文件面向代码代理/新开发者：项目结构、构建测试命令、必须遵守的约定。
> 人类向介绍见 README.md；变更历史见 CHANGELOG.md。

## 项目速览

基于 **Python 3.10+ / Flask 3.1** 的 IT 运维管理系统：客户/设备资产/巡检/工单/知识库/备件/销售管线/机柜/拓扑/AI 集成。
服务端渲染（Jinja2 + Bootstrap 5），SQLite（默认）或 PostgreSQL，Gunicorn + systemd 部署。

## 目录结构（2026-07 重构后）

```
app.py                  # 应用工厂 create_app() / 扩展实例 / register_routes / init_db（仅 ~325 行）
wsgi.py                 # Gunicorn 入口：create_app() + init_db(app)
config.py               # 配置、日志（RotatingFileHandler）、安全头
views/                  # 主应用视图（app.register_routes 集中注册，端点名无蓝图前缀）
  dashboard.py          #   首页仪表盘 + 工作台偏好 API
  auth.py               #   登录/登出/自助改密
  admin_users.py        #   用户管理/权限对照/AI 配置
  system.py             #   系统概览/schema 修复/侧栏/导入模板下载/客户列表
models/                 # 模型包（base.py 持 db 单例；__init__ 全量 re-export）
  base.py               #   db = SQLAlchemy()
  user.py customer.py device.py inspection.py ticket.py knowledge.py
  spare.py sales.py misc.py rack.py
blueprints/             # 业务蓝图（register_blueprints 统一注册）
  asset/                #   包：devices/dicts/firmwares/config_backups（蓝图名 asset）
  ops/                  #   包：inspections/tickets/faults/knowledge/templates/reports/...（蓝图名 ops）
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
tests/                  # pytest（111 用例；conftest 模块级 app + 用例级清库重播种）
scripts/                # 部署运维 + 数据脚本（faults_to_tickets.py / rotate_secret_key.py）
templates/ static/      # Jinja2 模板 / 静态资源（drawio vendor ~21MB 勿动）
```

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

- **路由层**（views/ blueprints/）：只做参数接收、权限装饰、调 service、渲染/重定向。
- **服务层**（services/）：业务规则；`@transaction` 自动 commit/rollback；失败抛 `ServiceError`。
- **模型层**（models/）：瘦模型，无状态机、无 commit 副作用。

### 表单写操作

统一用 `@form_commit(成功消息, 重定向端点, 失败兜底, after=可选钩子)`（utils/decorators.py），
不要新写 try/except/rollback/flash/redirect 样板。保存后副作用（如合同自动生成任务）放 `after` 钩子。

### 权限

- 装饰器三段栈：`@login_required` → `@require_permission('域:操作')` → 视图。
- 权限码集中在 `utils/permission.py: PERMISSION_MAP`；新增权限码需同步角色模板与 `seed_permissions`（幂等）。
- 敏感操作（查看明文密码 `device:reveal`、删除报告 `report:delete`、删除工单）**必须写审计日志**
  （操作人/对象/IP，current_app.logger.info）。
- API 请求未登录/无权限自动返回 JSON 401/403（按路径含 `/api/` 判定），页面走重定向。

### CSRF 策略（全站统一）

- 普通表单：base.html 自动注入 csrf_token 隐藏域。
- 前端 fetch JSON API：base.html 包装 window.fetch，非 GET 自动带 `X-CSRFToken` 头。
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
