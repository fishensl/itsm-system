# 变更日志

本文档记录 ITSM 运维管理系统的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [v1.1] — 2026-07-19

### 功能补全（v1.1 续）

- **合同自动巡检配置端到端可用**：合同表单补齐「巡检频率/巡检模板/自动生成任务 + 开始/结束日期」字段，
  create/update_contract 持久化（此前表单无字段、service 不持久化，自动生成在新增路径为死逻辑）；
  编辑预填改用 `tojson` 安全序列化（修复标题含引号截断隐患）；checkbox 经 `inspection_config_present`
  标记区分表单提交与局部更新
- **备份包密码保护（可选）**：导出可设密码（PBKDF2 480k → Fernet 整包加密 + magic 头识别），
  导入自动识别加密包并校验密码，错误密码/未提供密码明确拒绝——含密钥的备份包可安全外传/上云

### 修复（v1.1 续）

- **故障记录恢复可编辑/删除**：此前 UI 标注「历史归档仅支持查看」并隐藏了编辑/删除入口（路由实际可用）。
  列表/详情页恢复编辑按钮（fault:edit）与删除按钮（fault:delete，按钮按权限渲染）；
  operator 角色补授 `fault:delete` 权限码；新增「新增故障」入口；提示语更新为引导优先使用工单

### 修复

- **故障记录恢复可编辑/删除**：此前 UI 标注「历史归档仅支持查看」并隐藏了编辑/删除入口（路由实际可用）。
  列表/详情页恢复编辑按钮（fault:edit）与删除按钮（fault:delete，按钮按权限渲染）；
  operator 角色补授 `fault:delete` 权限码；新增「新增故障」入口；提示语更新为引导优先使用工单

### 工程化深化（W5）

- **密钥轮换工具**：`scripts/rotate_secret_key.py`（dry-run 默认、旧密钥自动备份、单事务全量重加密
  + 提交前回读校验、密钥文件原子替换；已端到端验证）
- **密码哈希升级**：旧 pbkdf2 哈希在用户登录成功时透明重哈希为 scrypt（werkzeug 3 默认，零依赖）
- **依赖漏洞清零**：flask 3.1.1→3.1.3、cryptography 44.0.3→48.0.1（pip-audit 项目依赖 5 漏洞→0，
  全量测试回归通过）
- **文档**：新增 `AGENTS.md`（结构/命令/约定/勿动清单）；README 项目结构与技术栈同步新架构
- 累计 **112 用例全绿**

### 数据一致性（W4）

- **状态常量化**：新增 `utils/constants.py` 单一真源（工单/巡检任务/审核/商机/报价/合同/项目/采集任务）；
  sales_service 写入边界校验非法状态直接拒绝；ticket_service / inspection_service 切换引用
- **JSON 边界**：新增 `utils/json_fields.py`（parse_json 失败记日志非静默）；修复模板匹配 API
  `len(items_json)` 数 JSON 字符数的 bug（改用模型 `total_sub_items`）；裸 dict 返回改 jsonify
- **事务完整性**：备件新增两次 commit 改 service 单事务 + 图片失败不阻塞；设备导入逐行 commit
  改整批事务（顺带补齐「是否维修/是否在用」两列长期被忽略的导入缺陷）；工单删除走 form_commit
  + 审计日志；`User.check_password` 明文升级不再隐式 commit（登录流程显式提交）
- **怪异行为清理**：故障类型页不再按 cwd 相对路径双态返回（固定渲染页面）
- **双轨收敛**：新增 `scripts/faults_to_tickets.py` 迁移脚本（dry-run 默认、幂等、fault.ticket_id 桥接）；
  模型层标注旧 InspectionTemplate 仍被合同自动生成链依赖（下线前需先迁 contract.inspection_template_id）
- 新增 W4 测试 10 用例；累计 **111 用例全绿**

### 结构重构（W3）

- **巨型文件拆包**（端点名全部不变，模板零改动）：
  - `ops.py`（1476 行）→ `blueprints/ops/` 8 模块（巡检/任务重定向/模板/故障/工单/知识库/巡检员/报告）
  - `asset.py`（982 行）→ `blueprints/asset/` 4 模块（设备/字典/固件/配置备份）
  - `app.py`（1245 行）→ 325 行，24 个视图迁入 `views/` 包（dashboard/auth/admin_users/system）
  - `models.py`（1108 行）→ `models/` 包 11 模块（`base.py` 持 db 单例，`__init__` 全量 re-export）
- **重复代码消除**：
  - `register_dict_crud` 工厂替代设备类型/品牌/网络类型/自定义字段四份同构 CRUD（-200 行）
  - 四份手写 Excel 导出统一走 `utils.excel_export`；修 `fault_export` 引用不存在的 `Fault.customer`（必 500）
  - `utils.decorators.form_commit` 封装表单写操作，sales/spare 26 个路由收敛
- **依赖清理**：消除 asset→app 循环导入（删 app.py 死封装）；模块级 `os.makedirs` 导入副作用移入 `create_app._ensure_runtime_dirs`
- 新增测试 16 用例；累计 **101 用例全绿**

### 性能优化（W1）

- **N+1 消除**：固件版本库按品牌+型号挂设备（单条 OR 查询替代逐组查询）；机柜列表/详情（selectinload+joinedload）；部门树（head/members 预加载）；报告中心三类记录 customer_rel 预加载
- **报告中心**：首次进入默认近 12 个月窗口（页面有提示，可清空查看全部）；文件反查索引只取有报告文件的记录（原三表全量扫描）
- **首页**：客户名映射按需 IN 加载（替代全表）；巡检任务匹配下推 SQL（逗号包裹防 id 误匹配，如 12 误中 123）；主管视角部门成员去重查询
- **索引迁移**（f7a8b9c0d1e2）：devices(customer_id)、devices(brand,model)、inspection_tasks(status/assigned_to_user_id/contract_id)、inspections(customer_id/review_status)、tickets(customer_id/assigned_to)
- **修复**：报告中心明细行从不渲染（路由写 `items`、模板读 `items_list`，HEAD 上即存在）
- 新增 W1 回归测试 13 用例（各角色首页、SQL 匹配防误伤、固件分组、机柜 API、报告窗口）

### 安全加固（W0）

- **设备明文密码收敛**：设备 JSON（`/api/devices/<id>`）不再携带明文密码；新增 `POST /api/devices/<id>/reveal-password` 按需查看（新权限码 `device:reveal` + 审计日志含操作人/IP）；Excel 导出密码列按权限收敛并记导出审计；设备列表/详情页改为掩码 + 按需查看
- **报告加固**：删除报告改用新权限码 `report:delete`；删除/下载均做 realpath 防路径穿越 + 扩展名白名单；删除写审计日志
- **读 API 权限补齐**：机柜（device:view）、部门树（department:view）、合同任务（contract_auto:manage）、客户级联（customer:view）
- **CSRF 收敛**：取消 drafts/rack 蓝图级豁免（前端 fetch 经 base.html 自动带 X-CSRFToken，保护不变、攻击面收窄）
- **API 错误格式统一**：API 请求未登录/无权限返回 JSON 401/403（兼容蓝图内 `/xxx/api/...` 路径），不再 302 跳登录页
- **知识库浏览计数**：改原子 UPDATE 自增 + 会话去重，修复并发丢失与 GET 副作用问题
- **日志轮转**：`RotatingFileHandler`（10MB × 10），修复 app.log 无限增长

### 重构与缺陷修复（T0）

- `app.py` 改造为 `create_app()` 应用工厂，路由集中注册（端点名不变，模板 url_for 不受影响）；`wsgi.py` 同步更新
- 修复备件删除校验必抛 `TypeError` 的缺陷（`p.stocks.count()` 对 list 调用），备件删除恢复正常
- 修复设备详情页「密码修改历史」从不渲染（路由传 `histories`、模板用 `history_data` 变量名不一致），历史密码改掩码 + 按需 reveal
- 草稿 `related_id` 统一 int 入库（修复 save/load 类型不匹配隐患）
- 实现 `/api/devices/<id>/password-history` 端点（前端原调用 404），列表不含明文

### 工程化（W2）

- 新增 pytest 测试套件 **72 用例**：工单状态机全转换、备件 FIFO/冲销、巡检审核流、四角色权限矩阵、密码安全、CSRF 策略、报告安全、草稿、冒烟
- 新增 GitHub Actions CI（ruff + pytest + pip-audit 告警）、`requirements-dev.txt`、`pyproject.toml`
- ruff 首次全量清理（104 处未用导入/未用变量）

---

## [v1.0] — 2026-06-15

### 首个 GitHub 版本

- Flask 应用主体：14 个业务模块，45 张数据表
- 客户管理 / 设备资产管理 / 巡检任务 / 故障工单 / 知识库 / 备件 / 销售 / 机柜 / AI 集成
- GitHub 一键部署脚本 `scripts/deploy.sh`（Ubuntu 24 + systemd + Gunicorn）
- 在线更新脚本 `scripts/update.sh`（git pull + 零停机重启）
- 备份脚本 `scripts/backup.sh` 和回滚脚本 `scripts/rollback.sh`
- 手动部署迁移脚本 `scripts/migrate-to-github.sh`
- 版本信息文件 `VERSION` 和变更日志 `CHANGELOG.md`

---

## 开发历程（2026-05-22 ~ 2026-06-14）

### 2026-06-14 — V13 用户主数据化
- User 表新增 phone / email / certifications 字段（12 项认证证书）
- 用户自助修改密码 / 管理员强制重置密码
- Inspector 表瘦身，工单派单改为文本输入
- 巡检记录保存时冻结巡检人员快照

### 2026-06-14 — V12 固件版本库
- 新建 device_firmwares 表
- 按品牌+型号分组展示，同型号设备版本对比

### 2026-06-14 — V11 巡检流程标准化
- 设备检查模板富字段编辑（11 种字段类型）
- 任务模板自动匹配 + 章节配置 + 拖拽排序
- 巡检表单草稿自动保存
- 审核通过自动生成 Word 巡检报告

### 2026-06-13 — V6.1 机柜 + 常用工具
- 机柜管理：机房位置 / 机柜 / 设备上架可视化（U 位画布）
- 常用工具：IP 计算 / 子网 / MAC / 进制 / 时间戳 / Base64 / MTU / 带宽 / 报文分析

### 2026-06-13 — V6 四阶段增强
- 备件库字段扩展（+8 字段）
- 拓扑图 UI 重构（按客户分组）
- 知识库附件（多附件上传 + 预览）
- 报告管理重构（客户→类型双层分组）

### 2026-06-12 — P0 阶段
- 工作台合并 Fault + Ticket 统计卡片
- Fault 降级为只读
- 删除重复 AI 配置路由

### 2026-05-22 — 项目创建
- 客户 / 设备 / 巡检 / 故障 / 用户 基础 CRUD
- AES 密码加密 / Excel 导入导出 / Word 报告生成
- Flask-Login 认证 / Bootstrap 5 UI
