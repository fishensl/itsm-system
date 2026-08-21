# ITSM 运维管理系统审计报告（2026-08）

> 审计基线：2026-08-13，`master`，`ece64de1e0c28484b8a3da45fcbf5eb29031e87b`
> 审计范围：流程闭环、功能完善、UI 统一、字段统一、数据安全、备份恢复
> 实施更新：截至 2026-08-21，P0 代码止血、P1 备份/恢复/发布加固、无需产品规则的 P2 字段/UI/契约收敛、P3 兼容端点观测基础及设备字段统一均已部署到生产提交 `c5f763f`。生产 `itsm.service`、`itsm-backup.timer` 正常，`/readyz` 的 database/frontend/master_key/migration 均为 `ok`；本报告的问题统计和健康度仍保留审计基线口径，不反向改写历史风险数量。G1 历史改写、G2 主密钥轮换和 G3 隔离恢复演练已于 2026-08-21 获得执行授权，仍按独立闸门留存实施与回滚证据。

## 1. 总览

### 1.1 审计方法与边界

- 以当前工作区源码、路由注册顺序、模型、服务层、Vue 调用、测试和部署脚本为依据，逐项复核已有审计结论；不把旧报告中的结论直接视为当前事实。
- 审计基线核对 229 个 Python 文件、45 个 Vue 视图、36 个迁移文件、64 个测试文件，当时可收集 840 个 pytest 用例；整改持续增加回归后当前收集数为 914。
- 2026-08-21 已对生产主机 `172.16.123.124` 做现场核验：代码与本地同为 `c5f763f`，应用和备份 timer 为 active，自动备份配置为启用、03:30、保留 3 份，最近一次状态为 `ok`；密钥权限为 `600`。生产客户 scope 开关未设置，当前按默认关闭运行；告警渠道仍需受控故障注入验证。
- 严重程度口径：高＝可导致越权、敏感数据泄露、主流程不可用或恢复失败；中＝重要功能不闭环、跨层不一致或存在明显运维风险；低＝一致性、体验、可维护性和长期成本问题。

### 1.2 统计与健康度

| 维度 | 高 | 中 | 低 | 合计 | 健康度 | 评价 |
|---|---:|---:|---:|---:|---:|---|
| 流程闭环 | 3 | 5 | 0 | 8 | 3.2 / 5 | 工单、巡检、故障转单和备件库存主干较完整；合同例外任务存在确定性死胡同 |
| 功能完善 | 0 | 5 | 1 | 6 | 3.8 / 5 | 核心模块覆盖面高，问题主要是后端能力未接前端及若干孤儿模型/半成品 |
| UI 统一 | 0 | 2 | 4 | 6 | 3.5 / 5 | SPA、全局搜索、通知和 DataTable 基础已成形；页面迁移率和响应式规范仍不足 |
| 字段统一 | 0 | 6 | 0 | 6 | 3.4 / 5 | `domain_metadata` 已覆盖大部分核心实体；客户页、权限映射、状态和 JSON 边界仍有双源 |
| 数据安全 | 8 | 7 | 0 | 15 | 2.4 / 5 | 加密、MFA、操作动态码和部分审计已具备；仍有历史密钥、匿名上传下载、XSS、越权和审计缺口 |
| 备份恢复 | 9 | 7 | 1 | 17 | 2.3 / 5 | 已支持 PG dump、Web 导入导出和调度；失败处理、原子性、配对轮转、发布回滚闭环不足 |
| **总计** | **20** | **32** | **6** | **58** | **3.1 / 5** | 业务能力已达到可用阶段，下一阶段重点应从“继续加页面”转为“安全、恢复、契约和流程收口” |

### 1.3 做得好的方面

- 工单已经具备状态机、派单/接单、挂起与 SLA 顺延、审核/验收、版本化提交、处置进展、知识库归档和敏感操作审计，属于当前最成熟的业务主线（`services/ticket_service.py:95-126, 325-367, 390-400`；`blueprints/vue_api.py:1918-2058`）。
- 巡检具备任务、报告版本、审核清单、正式报告生成失败后的补生成入口及通知兜底（`services/inspection_service.py:462-530`；`blueprints/vue_api.py:2885-2973`）。
- 故障转工单已实现幂等桥接、权限、审计与前端入口，旧结论“故障完全不联动工单”已不准确（`services/fault_service.py:93-121`；`blueprints/vue_api_ops.py:473-493`；`frontend/src/views/faults/index.vue:216-250`）。
- 备件已经具备采购入库、销售出库、借用、归还、库存回补与流水；缺的是“申请—审批”而非基础借还能力（`models/spare.py:102-125`；`services/spare_service.py:257-340`；`frontend/src/views/spare/index.vue:266-320`）。
- Vue SPA 已是唯一业务 UI，GlobalSearch、NotificationBell、移动端底栏、DataTable 移动卡片和列设置均已落地（`frontend/src/layouts/MainLayout.vue:169-200`；`frontend/src/components/DataTable.vue:1-157`）。
- 安全基础并非空白：设备/AI/通知密钥已加密，设备明文查看有权限、操作动态码、限流和审计；CSRF 默认开启，前端非 GET 自动携带令牌（`utils/crypto.py:25-109`；`frontend/src/utils/request.ts:18-25`；`blueprints/vue_api.py:1081-1124`）。
- 备份侧已有 PG 自定义格式 dump、Web 加密备份包、一次性下载、导入前快照和可配置调度器，这些可作为 P1 加固基础，无需推倒重做（`scripts/backup.sh:27-47`；`blueprints/vue_api_sys.py:638-817`；`utils/scheduler.py:75-106`）。
- CI 已覆盖 Python 3.10/3.12、pytest、Ruff、前端 lint/unit/build；迁移不可变、状态生成物、metadata 权限矩阵、JSON 边界和 UI 语义色均有门禁，当前 914 个测试全量通过（`.github/workflows/ci.yml`；`tests/test_entity_metadata.py`；`tests/test_json_boundaries.py`；`tests/test_ui_convergence.py`）。

### 1.4 当前状态标记

| 项目 | 当前状态 | 证据/说明 |
|---|---|---|
| 旧 Fernet 主密钥备份退出当前索引 | **已修复** | 提交 `ece64de` 已删除 `.secret.key.bak.20260719_165843` 的跟踪记录；本轮再次确认 `git ls-files -- '.secret.key*'` 无输出 |
| 旧密钥 blob 从 Git 历史移除 | **未修复，需单独授权** | `git rev-list --objects --all` 仍可见 blob `b6d605f5...`；历史改写会影响全部协作者和远端引用 |
| 当前生产密钥轮换 | **已核验未轮换，待 G2 窗口** | 生产 `.secret.key` 的 SHA256 与历史泄露 blob 完全一致；密钥权限为 `600`，但保密性已失效。2026-08-21 已获执行授权，须在 G3 和停服前备份验证通过后执行 `scripts/rotate_secret_key.py --apply` |
| P0 代码止血 | **已修复** | 提交 `507c2fd`：设备详情契约、任务越权、CSRF、匿名上传、知识库 XSS、拓扑白名单、敏感审计、遗留明文导出、缺钥 fail-closed、初始管理员和合同例外审核闭环 |
| P1 备份/恢复/发布代码 | **已修复（约定范围）** | 提交 `507c2fd`：备份失败硬退出、PG 完整性校验、配对轮转、导入 staging、不可变前端包、迁移门禁、health/ready、临时导出清理 |
| 数据 scope、跨进程 RBAC、自动备份状态告警 | **代码已完成，scope 待审计启用** | `30a040e` 完成统一范围、RBAC 版本失效、导出审计、备份 RPO/失败告警；`c2a73bf` 增加默认关闭的发布闸门。生产 `ITSM_CUSTOMER_SCOPE_ENFORCE` 当前未设置，须完成用户—部门—客户关系审计后再开启 |
| P2/P3 Backlog | **确定性收敛项已实施，产品流程待 G4** | `8c0c4cf`、`c54dfd9` 完成 DataTable、metadata、状态/JSON 边界、响应式/主题代码与兼容观测；备件审批、SLA、满意度、项目/知识审核等仍需产品确认，兼容端点删除仍需 G5 的 30 天生产数据 |

### 1.5 本轮整改状态（提交 `507c2fd`、`30a040e`、`c2a73bf`、`8c0c4cf`、`c54dfd9`）

| 状态 | 审计项 | 说明 |
|---|---|---|
| **已修复** | FL-01、FL-02、FL-03 | 设备详情唯一契约；任务合同例外可见、可审、可审计、可通知；通用更新不能绕过审核 |
| **已修复** | DS-02～DS-10、DS-14、DS-15 | 匿名上传 404、HTML 白名单净化、RBAC/配置审计、旧明文导出下线、任务权限、缺钥拒启、显式初始化、CSRF 和上传白名单、访问异常 fail-closed、12 位密码与首次改密 |
| **已修复** | DS-11、DS-13 | 已补敏感配置与批量导出审计；RBAC 采用数据库版本号+2 秒 TTL 且未知/停用角色 fail closed |
| **代码已完成，待启用** | DS-12 | 统一客户/设备范围已覆盖列表、详情、搜索、字典、导出及密码导出审批；scope 强制开关默认关闭，待生产关系审计后开启 |
| **已修复，告警待注入验收** | BR-01 | 自动备份记录最后尝试/成功/失败、连续失败、耗时和 RPO；生产已启用且 2026-08-21 核验健康为 `ok`。仍需受控故障注入确认站内及外部渠道的实际送达，并在测试后恢复成功状态 |
| **已修复** | BR-02～BR-08、BR-10～BR-17 | 备份/导入硬失败与原子激活、不可变前端 Release、同版本离线 manifest、失败停止、配对轮转、迁移锁/CI、ready、生产日志和校验和 |
| **部分修复** | BR-09 | 已要求 dump/meta 配对、预检查与恢复后 ready；健康失败可自动恢复上一版前端并保留失败版本。代码/schema 自动同版本回退仍需发布单元继续收敛 |
| **已修复** | UI-01、UI-03、UI-05、UI-06 | 9 个常规顶层列表迁入 DataTable，PacketAnalyzer 增加移动卡片；DataTable 视图由 12 增至 21；主题进入 Pinia 并支持系统/浅色/深色；新增 404；业务提示统一到 UI store |
| **已修复** | FD-01～FD-06 | 客户与补充实体已消费 metadata；实体—路由权限矩阵覆盖所有当前页面；状态机、模型默认值、自动任务和 Vue 比较复用 constants 生成物；数据库 JSON Text 读写统一经公共边界并验证损坏/错误容器类型 |
| **代码已完成，待视觉验收** | UI-02、UI-04 | Dialog 已具备桌面/平板/手机视口约束，浅色/深色语义 token 与 Element Plus 映射已补齐，Vue 硬编码语义色有静态门禁；仍需 375/768/1440px 浏览器截图与对比度人工验收 |
| **部分修复** | WP-17 | 兼容端点已有弃用头/日志，删除仍等待 30 天生产零调用证据 |
| **已授权，执行中** | DS-01 / G1、G2、G3 | 2026-08-21 已获明确授权；执行顺序为无停服审计与告警注入 → G3 隔离恢复 → G2 停服轮换与抽检 → G1 历史改写和远端验证 |

### 1.6 生产无停服核验（2026-08-21）

- **客户关系审计**：生产共有 37 个客户、46 台设备、5 个活跃用户，设备均已关联客户，但 `customer_engineers` 为 0 条；4 名活跃非管理员的配置可见客户均为 0，37 个客户均无活跃工程师关联。现在开启 `ITSM_CUSTOMER_SCOPE_ENFORCE` 会使非管理员客户数据全部不可见，因此保持关闭，须先由管理员补齐用户—客户关系再复审。
- **备份告警故障注入**：使用标识 `GATE-ALERT-20260821-0534` 将备份健康状态受控切换为 `failed`，连续失败数变为 1；已向管理员写入站内通知 `notifications.id=11`，随后将全部备份状态字段精确恢复，健康状态重新为 `ok`。企业微信、钉钉、飞书渠道均未启用且未配置凭据，故外部送达无法验收，必须先完成至少一个外部渠道配置。
- **远端同步**：本地 `master` 的 18 个待同步提交已正常推送到 `origin/master`；既有未跟踪文件未纳入提交。后续 G1 会再次改写提交 SHA，届时须按 G1 方案强推并要求协作者重新克隆。

## 2. 维度一：流程闭环

### 2.1 健康项

- 工单主流程闭环度高，且合同例外审核已有可复用范式：权限 `contract:review`、审核动作、前端按钮和审计均已存在（`services/ticket_service.py:390-400`；`blueprints/vue_api.py:1940-1958, 2032-2034`；`frontend/src/views/tickets/TicketExpandRow.vue:70-80`）。
- 巡检审核、故障转单、合同自动生成巡检任务、备件借还均已有实际服务和测试，不应重复建设。

### 2.2 问题清单

| ID | 文件:行号 | 严重程度 | 问题描述 | 修复建议 |
|---|---|---|---|---|
| FL-01 | `blueprints/__init__.py:40,51`；`blueprints/asset/devices.py:18-48`；`blueprints/vue_api.py:997-1005`；`frontend/src/utils/request.ts:71-75` | 高 | `asset_bp` 先注册，同路径裸 JSON `GET /api/devices/<id>` 遮蔽统一契约路由。前端 `request()` 读取不到 `code=0`，设备详情抽屉会抛错；`tests/test_security_passwords.py:41-45` 还在按错误响应形状断言，掩盖故障。 | 下线或改名遗留 GET，保留唯一 `{code,data,message}` 端点；增加路由表唯一性测试和设备详情契约测试，禁止测试继续断言裸响应。 |
| FL-02 | `utils/constants.py:30-43`；`blueprints/vue_api_ops.py:1341-1374,1377-1428`；`blueprints/vue_api.py:1444-1464,1498-1501`；`frontend/src/views/taskSchedule/index.vue:68-103` | 高 | 合同过期任务会进入“合同审批”，但无专用审核 API；任务 payload 不含例外字段，看板也不建立“合同审批”分组，任务创建后会从常用状态视图消失。通用 PUT 仅要求 `task:schedule`，也不能表达审核权限和审核意见。 | 仿照工单实现 `POST /api/task-schedule/<id>/contract-review`，复用 `check_task_transition`，要求 `contract:review`；payload 返回例外字段；前端加入审核列/待办和按钮；通过转“待执行”，拒绝转“已取消”，全程审计。 |
| FL-03 | `utils/wecom_notify.py:17,29,43`；`blueprints/vue_api_ops.py:1341-1374` | 高 | `EVENT_CONTRACT_REVIEW` 已定义、可配置但全库无触发点，合同例外申请不会产生站内或外部渠道通知。 | 在任务进入合同审批及审核结果落库后触发事件；接收人至少覆盖部门主管和 admin；增加去重游标、失败重试和事件测试。 |
| FL-04 | `models/ticket.py:40,88`；`services/inspection_service.py:478-510`；`frontend/src/views/inspections/InspectionExpandRow.vue:51-55` | 中 | 工单模型已有 `related_inspection_id`，但巡检异常/退回后没有“一键转工单”入口、责任人选择、幂等校验或回写状态，异常仍依赖线下处置。 | 设计“巡检异常→工单”动作：默认复制客户、设备、异常项、报告版本；回填 `related_inspection_id`；重复转单提示现有工单；工单关闭后在巡检详情显示处置结果。 |
| FL-05 | `models/spare.py:102-125`；`services/spare_service.py:300-340`；`frontend/src/views/spare/index.vue:279-320,740-768` | 中 | 当前是有 `spare:add` 即可直接借出、`spare:edit` 即可归还，没有“申请人—审批人—库管出库”的职责分离。 | 保留现有借还作为库管执行层，新增 `SpareRequest` 申请单和待审/通过/驳回/已出库/已归还状态机；审批后才调用现有扣库存服务。 |
| FL-06 | `services/ticket_service.py:95-126,365-366`；`blueprints/vue_api.py:1676-1679`；`utils/scheduler.py:65-70` | 中 | 已计算 SLA 截止时间并在列表标红，也有“挂起超时”通知，但没有针对一般工单 SLA 临期/超时的调度事件、一次性游标、升级策略。 | 新增 `EVENT_TICKET_SLA_DUE/OVERDUE`、提醒游标和分级升级规则；首次临期、首次超时、持续超时分别通知负责人/主管，避免每轮重复轰炸。 |
| FL-07 | `services/sales_service.py:62-93,163-216,257-289`；`utils/constants.py:66-108`；`models/sales.py:74-91` | 中 | 商机成交不会生成合同；项目只有 CRUD/进度字段，没有项目任务、里程碑或与巡检/工单的挂接；项目状态只有合法值集合，没有转换表。 | 把“成交→合同”做成显式向导而非静默副作用，允许补齐合同字段后确认生成；新增项目任务/里程碑和状态转换，支持关联现有工单、巡检任务。 |
| FL-08 | `models/ticket.py:61,84`；`frontend/src/views/tickets/index.vue:329-352`；全库无 satisfaction/survey 模型或路由 | 中 | 工单关闭后无满意度回访、差评升级、回访完成标记，服务质量闭环停在内部验收。 | 新增一次性回访 token、评分/意见、匿名或登录校验、差评自动通知主管；统计口径进入仪表盘但与技术审核解耦。 |

## 3. 维度二：功能完善

### 3.1 健康项

- 仪表盘核心指标来自真实 SQL 聚合，不是静态占位（`blueprints/vue_api.py:293-505`；`views/dashboard.py:19-28`）。
- 报告中心、全局搜索、通知规则、多渠道通知、MFA、操作动态码、数据备份 UI 已形成较完整的管理能力。

### 3.2 问题清单

| ID | 文件:行号 | 严重程度 | 问题描述 | 修复建议 |
|---|---|---|---|---|
| FN-01 | `blueprints/drafts.py:24-120`；`tests/test_drafts_api.py:1-52`；`frontend/src` 无 `/api/drafts` 调用 | 中 | 草稿后端和测试完整，但 Vue 表单零消费，用户实际得不到自动保存/恢复能力；`draft:manage` 权限也没有形成产品入口。 | 先接工单、巡检、故障三个高成本表单，采用防抖保存、版本号/更新时间提示、提交成功删除草稿；确认无人使用后再决定是否删除后端。 |
| FN-02 | `models/misc.py:70-87`；`services/device_service.py:141-148`；前端设备模块无 collect/online 调用 | 中 | `DeviceCollectTask` 仅在删除设备时被清理，没有创建、执行、消费或展示；设备“在线状态”也没有可靠采集数据源。 | 先做产品决策：需要在线采集则补采集器、任务状态、最后心跳和失败重试；不需要则迁移删除孤儿表/模型，避免制造“已有在线能力”的错觉。 |
| FN-03 | `models/knowledge.py:23-27`；`blueprints/vue_api_ops.py:172-232`；`frontend/src/views/knowledge/index.vue:54,128,175,218-245` | 中 | 知识库已有草稿/发布字段和发布审计，但拥有编辑权的人可在创建/编辑时直接写 `is_published`；`helpful_count` 只有展示，无投票记录、去重和撤销。 | 若需要真实审核，拆分 `kb:edit` 与 `kb:publish`，禁止普通保存直接发布；新增按用户去重的投票表和 API，计数由关系聚合或事务维护。 |
| FN-04 | `services/sales_service.py:277-289`；`utils/constants.py:104-108` | 中 | 项目状态更新只校验值，不校验转换，可从已完成任意回退；也没有任务和里程碑导致“项目管理”实质仍是档案 CRUD。 | 增加 `PROJECT_TRANSITIONS`、重开权限和审计；项目任务复用通用任务能力或建立轻量 ProjectTask，避免再造一套无关联看板。 |
| FN-05 | `models/ticket.py:154-169`；`services/fault_service.py:59-68,93-121` | 中 | 故障有结果字段但无独立状态机；转工单后只回填 `fault.ticket_id`，工单关闭/重开不会同步故障结果或在工单侧明确展示来源故障。 | 明确“故障记录”是档案还是流程。若是流程，增加转换表；建立双向导航，工单关闭时由可配置规则回写故障，不直接强耦合所有字段。 |
| FN-06 | `models/device.py:50-62`；`frontend/src/views/firmwares/index.vue:81-131`；`blueprints/vue_api_asset.py:817-965` | 低 | 固件库目前是版本元数据和外部下载 URL 管理，没有文件托管、签名/校验状态或设备升级任务；名称容易让用户误以为系统能完成固件分发。 | 保持元数据库定位并在 UI 明示；如未来托管文件，必须增加哈希验证、签名、审批、分批发布和回滚，不宜直接复用普通上传目录。 |

## 4. 维度三：UI 统一

### 4.1 健康项

- 45 个 Vue 视图中已有 12 个视图使用 DataTable；客户以外的大多数核心列表已具备分页、列设置和移动卡片基础。
- GlobalSearch、NotificationBell 在桌面和移动端均有入口，旧报告中“移动端不可用”的结论已过时（`frontend/src/layouts/MainLayout.vue:169-200,559-568`）。

### 4.2 问题清单

| ID | 文件:行号 | 严重程度 | 问题描述 | 修复建议 |
|---|---|---|---|---|
| UI-01 | `frontend/src/views/contractTasks/index.vue:31`；`firmwares/index.vue:41`；`rack/index.vue:102`；`taskTemplates/index.vue:13`；`topology/index.vue:36`；`system/exportReviews.vue:14`；`system/notifyRules.vue:14`；`devices/DictTable.vue:9`；`system/ReviewChecklist.vue:16`；`tools/PacketAnalyzer.vue:58` | 中 | 审计时至少 10 个顶层/功能列表仍直接使用 `el-table`。**状态：已修复（`8c0c4cf`）**，9 个常规列表已迁入 DataTable，使用视图由 12 增至 21；PacketAnalyzer 保留高密度桌面表格但补移动卡片；详情弹窗内小表按语义保留。 | 后续新顶层列表继续强制使用 DataTable；对嵌套详情表和专业分析表按移动端验收决定，不追求形式上的 100%。 |
| UI-02 | `frontend/src/styles/index.css:138-199`；`tests/test_ui_convergence.py` | 中 | 审计时固定宽度 Dialog 在窄屏容易溢出。**状态：代码已修复（`c54dfd9`）**，全局规则约束桌面/平板/手机宽度、动态视口正文高度和可换行操作区；尚未执行 375/768/1440px 浏览器截图验收。 | 上线前对报告预览、审核、复杂表单做三档视口人工/截图回归；发现例外时按组件语义补全屏模式，不恢复页面级硬编码。 |
| UI-03 | `frontend/src/stores/ui.ts:15-58`；`frontend/src/main.ts:20`；`frontend/src/layouts/MainLayout.vue:94-101` | 低 | 审计时主题保存在 MainLayout 局部 ref。**状态：已修复（`8c0c4cf`）**，主题偏好、系统媒体查询和应用动作已进入 Pinia，挂载前初始化，支持系统/浅色/深色三态。 | 后续独立编辑器/登录布局直接复用 UI store，不再自建主题状态。 |
| UI-04 | `frontend/src/styles/index.css:2-76`；`tests/test_ui_convergence.py` | 低 | 审计时深色模式 token 不完整且 Vue 视图散落硬编码颜色。**状态：代码已修复（`c54dfd9`）**，已补 primary/success/warning/danger/info、soft、overlay、shadow 等明暗 token，映射 Element Plus，并以静态测试禁止 Vue 语义色回流；WCAG/禁用态仍待浏览器抽样。 | 上线前抽查登录、仪表盘、设备、巡检、任务、知识库在暗色下的文字、边框、告警和禁用态对比度。 |
| UI-05 | `frontend/src/router/index.ts:279-285`；`frontend/src/views/errors/NotFound.vue:1-74` | 低 | 审计时未匹配路由直接回工作台。**状态：已修复（`8c0c4cf`）**，404 与 403 分开，提供返回、工作台、全局搜索和错误标识。 | 后续把错误标识接入前端错误采集；保留旧书签命中统计。 |
| UI-06 | `frontend/src/router/index.ts:304-310`；`frontend/src/components/ExportDialog.vue:73-252`；`frontend/src/stores/ui.ts:63-69` | 低 | 审计时 Pinia toast、全局事件桥和 `ElMessage` 并存。**状态：已修复（`8c0c4cf`）**，路由和导出校验统一走 UI store；事件桥仅作为 axios 到 store 的适配器；MessageBox 只承担确认/详情交互。 | 新组件统一调用 UI store，禁止重新引入业务 `ElMessage`。 |

## 5. 维度四：字段统一

### 5.1 健康项

- `domain_metadata` 已覆盖设备、工单、故障、巡检、客户、销售、备件、用户、角色、机柜、拓扑、通知规则等核心实体，且多个页面已通过 `fetchEntityMeta(s)` 和 `mergeFieldMeta` 消费。
- 设备/工单/巡检/故障/客户/备件导出已逐步复用元数据列定义，方向正确。

### 5.2 问题清单

| ID | 文件:行号 | 严重程度 | 问题描述 | 修复建议 |
|---|---|---|---|---|
| FD-01 | `domain_metadata/entities.py:676-681`；`frontend/src/views/customers/index.vue:343-349,633` | 中 | 审计时客户页未调用 metadata。**状态：已修复（`8c0c4cf`）**，树列表、详情与表单标签统一读取 `customer` profile，保留后端旧版本回退文案。 | 后续把表单 required/options 也逐步由 profile 驱动，不只统一 label。 |
| FD-02 | `domain_metadata/entities.py:608-635,807-825`；`frontend/src/views/regions/index.vue`；`deviceCheckTemplates/index.vue`；`system/notifyChannels.vue` | 中 | 审计时地区、设备检查模板、通知渠道未登记。**状态：已修复（`8c0c4cf`）**，三个 schema 及消费者已落地；通知渠道只暴露 `has_secret`，不登记 secret/config。 | 为新增实体继续执行“先登记 schema、再建页面”的门禁。 |
| FD-03 | `domain_metadata/entities.py:650-860`；`tests/test_entity_metadata.py:95-130` | 中 | 审计时 metadata 与页面/API 权限口径错位。**状态：已修复（`c54dfd9`）**，补齐设备关联工单/巡检和合同自动巡检的权限别名，并建立当前全部页面的实体—路由—metadata 权限矩阵测试。 | 新页面必须同步扩展矩阵；页面入口用查看权限，写按钮继续使用动作权限，避免通过复用不相干实体 schema 引入权限漂移。 |
| FD-04 | `utils/constants.py:157-224`；`scripts/generate_frontend_status.py:1-55`；`frontend/src/utils/status.generated.ts`；`.github/workflows/ci.yml` | 中 | 审计时前后端分别维护状态/颜色。**状态：已修复（`8c0c4cf`）**，后端目录生成只读 TS，任务看板复用同一 tag map，CI 与 pytest 都会拒绝过期生成物。 | 状态增删只改 `constants.py` 后重新生成；前端手工文件只保留非状态机录入选项。 |
| FD-05 | `utils/constants.py:9-140`；`services/ticket_service.py`；`services/task_schedule_service.py`；`blueprints/vue_api.py`；`frontend/src/views/inspections/index.vue`；`frontend/src/views/sales/index.vue` | 中 | 审计时服务、路由、模型默认值、生成器和前端比较仍散落业务状态。**状态：已修复（`c54dfd9`）**，工单转换表进入常量真源，任务/工单/巡检/销售的写入、查询、默认值与 Vue 比较均引用 constants 或生成 TS；兼容输入别名和用户文案不作为状态写入。 | 状态增删仅修改 `utils/constants.py` 并更新生成物；继续以生成检查、转换表覆盖和代码评审阻止新裸写入。 |
| FD-06 | `utils/json_fields.py:1-36`；`tests/test_json_boundaries.py`；`blueprints/drafts.py`；`utils/sidebar_config.py`；`utils/report_generator.py` | 中 | 审计时多个 db.Text JSON 字段直接解析，损坏数据和错误容器类型行为不一致。**状态：已修复（`c54dfd9`）**，客户/设备/巡检/模板/提交版本/草稿/仪表盘/侧栏/证书等数据库 JSON 边界统一走 `parse_json/dumps_json` 并校验 list/dict 类型；备份 manifest、加密信封、通知请求体等非数据库 JSON 保持专用协议实现。 | 新增 JSON Text 字段必须声明默认容器类型并补损坏、空串、旧格式测试；禁止用字符串长度代表条目数。 |

## 6. 维度五：数据安全

### 6.1 健康项

- 未发现明显 SQL 注入拼接；主要查询使用 SQLAlchemy。
- 设备密码查看、复制、历史密码、密码导出新流程已具备权限、限流/操作动态码、一次性下载和审计。
- 登录、MFA、会话失效、可信网段、CSP/安全头框架均已存在，可在现有基础上收紧。

### 6.2 问题清单

| ID | 文件:行号 | 严重程度 | 问题描述 | 修复建议 |
|---|---|---|---|---|
| DS-01 | Git 历史 `2f2a0e3`；当前修复 `ece64de`；`.gitignore:41-44` | 高 | 完整旧 Fernet 主密钥曾进入 Git。当前索引已清理，但 blob `b6d605f5...` 仍在历史和可能的远端克隆中；只 `git rm --cached` 不能消除泄露。 | 作为安全事件处理：盘点使用该密钥加密的数据和备份；单独征得全体协作者确认后用 BFG/filter-repo 改写全部 refs 并强推；通知重新克隆；在停服窗口轮换当前密钥。旧备份必须与对应旧密钥隔离配对保存，否则不可恢复。 |
| DS-02 | `utils/access_guard.py:22-23,70-82`；`blueprints/asset/config_backups.py:25-47`；`blueprints/vue_api.py:1961-1984,3030-3120` | 高 | Flask `/static` 可直接出文件，外网守卫又整体放行 `/static/` 和 `/uploads/`；设备配置、巡检报告/照片、拓扑等 `static/uploads` 文件可被匿名猜路径下载。 | 增加最先执行的 `before_request`：匿名访问 `/static/uploads/*` 统一 404；已登录用户（含外网工单流程用户）放行。长期把敏感文件迁出 static，通过带权限的下载端点返回。 |
| DS-03 | `blueprints/vue_api_ops.py:163-200`；`frontend/src/views/knowledge/index.vue:64-65` | 高 | 知识库正文原样入库并用 `v-html` 渲染，具备存储型 XSS 条件；可窃取非 HttpOnly CSRF token、诱导敏感操作或污染管理员页面。 | 服务端保存前使用白名单净化；优先复用现有依赖，若无则用标准库 `html.parser` 实现允许标签/属性/协议；补历史数据清洗脚本。前端可再加 DOMPurify 作为纵深防御。 |
| DS-04 | `blueprints/vue_api_sys.py:852-989` | 高 | 角色 CRUD、角色权限矩阵和用户权限覆盖均不写 `audit_logs`。这些操作可直接改变自身或他人权限，是最高敏感度变更，却不可追溯。 | 所有成功和拒绝的权限变更写结构化审计，记录 before/after 差异、操作人、目标、IP；删除/批量覆盖需操作动态码；审计写入与业务事务统一或使用可靠 outbox。 |
| DS-05 | `blueprints/asset/devices.py:102-167`；`tests/test_security_passwords.py:101-135`；前端无 `/devices/export` 引用 | 高 | 遗留 `/devices/export` 可在 `device:reveal` 下直接批量导出明文密码，绕过新审批/一次性下载流程，且只写普通 logger、不写审计表。前端已无引用，但测试仍把端点保活。 | 下线路由及对应遗留测试；如短期必须保留，强制走密码导出申请、操作动态码、一次性 token 和审计表，禁止直接响应 Excel。 |
| DS-06 | `blueprints/task_schedule.py:572-588`；`blueprints/task_dispatch.py:5-8` | 高 | `status-form` 只有 `login_required`，任何登录用户均可通过兼容 307 路由改变任务状态；相邻派发端点已有 `task:dispatch`，权限明显遗漏。 | 至少补 `task:schedule`，更合理的是按动作使用 `task:dispatch`/任务归属校验；为 viewer 增加 403 回归；评估兼容路由无调用后整体下线。 |
| DS-07 | `utils/crypto.py:112-132`；`wsgi.py:4-10` | 高 | 生产启动时若 `.secret.key` 和 locked key 都丢失，`ensure_master_key_available()` 会静默生成新密钥；已有密文随后全部不可解，且没有恢复阻断。 | 生产环境缺钥必须 fail closed；只允许显式初始化命令在全新空库创建密钥。启动时检测敏感密文字段是否已有数据，并给出明确恢复指引。 |
| DS-08 | `app.py:351-357,383`；`blueprints/vue_api_sys.py:187` | 高 | 空库自动创建并打印已知凭据 `admin/admin123`，新建用户未传密码时默认 `changeme`，且没有强制首次改密字段。生产首次启动窗口存在接管风险。 | 生产禁止内置默认密码；通过一次性随机引导密钥/CLI 创建首个管理员，不写日志；新增 `must_change_password`，首次登录只能改密和绑 MFA。 |
| DS-09 | `blueprints/asset/config_backups.py:13-16`；`views/dashboard.py:81-101`；`views/system.py:148-171`；`frontend/src/utils/request.ts:18-25` | 中 | 5 个 SPA/内部写端点使用 `@api_view` 豁免 CSRF，而统一 request 已自动带 token，没有保留豁免的必要。 | 删除这些写端点的豁免；GET 上的 `@api_view` 也应清理语义；`tests/test_csrf.py` 增加无 token 400/有 token 成功回归。 |
| DS-10 | `blueprints/vue_api_asset.py:523-560` | 中 | 拓扑上传的 unknown 分支设 `allowed=set()`，随后 `if allowed` 为假，任意未知扩展名都会被保存到静态目录。 | 未识别扩展名直接 400；所有分支统一调用 `validate_upload`，校验大小、扩展、MIME/文件头；XML/SVG 类主动内容使用下载附件或隔离预览。 |
| DS-11 | `blueprints/vue_api_sys.py:560-636,1006-1035,1066-1123,1151-1177`；`blueprints/vue_api.py:712-755,2207-2265,3432-3715`；`blueprints/vue_api_sales.py:99-151` | 中 | 审计时 AI、可信网段、通知配置和批量导出存在缺口。**状态：已修复（`507c2fd`、`30a040e`）**，导出审计只记录筛选、列、行数和 token，不写导出内容或 secret。 | 后续把 helper 独立 commit 收敛到同事务/outbox，并纳入审计可靠性监控。 |
| DS-12 | `utils/permission.py:257-298`；`blueprints/vue_api.py:592-709,997-1005,1355-1389,2120-2148,2369-2460` | 中 | 审计时客户范围未统一。**状态：代码已修复（`30a040e`、`c2a73bf`）**，强制过滤默认关闭；开启前必须审计 `customer_engineers`、部门及 scope 配置，避免历史关联缺失导致误拒绝。 | 生产先观察日志并补齐关系，再设置 `ITSM_CUSTOMER_SCOPE_ENFORCE=1`；开启后验收 all/department/self、直接 ID、搜索、导出和密码审批范围。 |
| DS-13 | `utils/permission.py:15-27,212-238`；`scripts/itsm.service:12` | 中 | 审计时角色缓存仅进程内且未知角色回退 viewer。**状态：已修复（`30a040e`）**，数据库版本号与 2 秒短 TTL 让多 worker 失效，未知/停用角色为空权限，停用 admin 也失去快捷权限。 | 生产以两个 worker 做权限撤销秒级生效演练；长期可按规模迁移到 Redis/pub-sub。 |
| DS-14 | `utils/access_guard.py:75-80` | 中 | 可信网段判断异常时按内网放行，配置/数据库异常会扩大外网权限边界。 | 对敏感 API fail closed 并告警；对 `/app` 静态壳可降级放行，实际数据 API 必须拒绝；增加异常注入测试。 |
| DS-15 | `blueprints/vue_api.py:214-227`；`blueprints/vue_api_sys.py:283-295`；`frontend/src/layouts/MainLayout.vue:203-217` | 中 | 密码策略仅 6 位；无常见密码阻断、强制首次改密或管理员重置后失效流程。 | 采用至少 12 位口令/长密码策略，禁止已知默认值；重置后 `auth_version` 已可用于踢下线，再补首次改密和 MFA 引导。 |

## 7. 维度六：备份恢复

### 7.1 健康项

- `backup.sh` 已区分 PostgreSQL 和 SQLite，PG 使用 `pg_dump -Fc`；Web 端备份包支持密码加密和一次性下载。
- 导入前会尝试生成全量快照，导入数据库在同一 SQLAlchemy session 中完成，已有事务基础。
- 调度器有单进程锁和可配置时间/保留份数，具备继续加固的落点。

### 7.2 问题清单

| ID | 文件:行号 | 严重程度 | 问题描述 | 修复建议 |
|---|---|---|---|---|
| BR-01 | `utils/backup_config.py:8-12`；`utils/scheduler.py:75-106` | 高 | 审计时自动备份失败只有本机日志。**状态：代码已修复（`30a040e`）**，现已持久化最后成功/失败、连续失败和 RPO，并触发站内及外部渠道告警；默认是否开启仍是生产配置决策。 | 上线核验调度器实际启用、通知规则收件人、最近成功时间和一次故障注入；未完成现场核验前不宣称 RPO 已保障。 |
| BR-02 | `scripts/backup.sh:44-46,59-64,69-74` | 高 | `tar ... 2>/dev/null || true` 吞掉密钥、配置或业务文件归档失败，即使 meta 包不完整也显示备份完成并返回 0。 | 必需项缺失或 tar 失败立即非零退出；可选目录先建空目录或动态组装参数；失败写 stderr 并触发调度告警。 |
| BR-03 | `utils/data_io.py:340-354` | 高 | 备份包 sha256 不一致只追加 warning，仍继续清空和回灌数据库，损坏或被篡改的包可进入恢复流程。 | 哈希不一致硬拒绝；无 manifest/旧格式走显式兼容确认；长期为 manifest 增加签名或 HMAC，并对文件清单、大小和 schema 版本做前置校验。 |
| BR-04 | `utils/data_io.py:393-484`；`blueprints/vue_api_sys.py:749-761` | 高 | 文件和 `.secret.key` 在数据库 commit 前直接覆盖；若 commit 失败，DB 回滚但磁盘/密钥不能回滚，形成数据—密钥—附件不一致。 | 先解压到 staging；数据库 commit 成功后用 `os.replace` 原子落盘；保存原文件/密钥回滚副本；任一步失败恢复原状。大规模恢复宜停服执行。 |
| BR-05 | `blueprints/vue_api_sys.py:730-747` | 高 | 覆盖导入前的自动备份失败只告警并继续，恰好在最需要兜底时允许无恢复点地破坏当前数据。 | pre-import 备份失败必须阻断导入，除非用户再次输入高风险确认并提供外部已验证备份编号；默认不允许绕过。 |
| BR-06 | `scripts/update.sh:302-355` | 高 | 前端部署失败只设置标志，脚本仍执行迁移、重装 service、重启，最后才退出 1；可能以新后端 schema + 旧/缺失前端运行。 | 前端失败在迁移前立即退出；发布采用 backend/frontend/schema 同一 release manifest；重启后健康检查失败自动回滚。 |
| BR-07 | `.github/workflows/ci.yml:72-82`；`scripts/update.sh:208-237`；`scripts/rollback.sh:12-14,107-111` | 高 | `vue-dist` 是可变 Release 并 `--clobber` 覆盖；部署直接删除旧 `static/app`，却没有脚本创建 `static/app.bak`，rollback 文档要求的前端备份并不存在。 | 每个 commit/tag 发布不可变前端包和 SHA256；部署前把旧 dist 移到带版本目录，原子切 symlink；回滚脚本按 release manifest 同时回滚代码、前端和 schema 兼容版本。 |
| BR-08 | `scripts/update.sh:176-184,255-300` | 高 | `git pull` 全部失败后仍继续，随后可能下载最新可变前端包，形成旧后端+新前端；本地构建还会直接复制到现有目录，非完整原子替换。 | 代码拉取失败必须终止；前端包 manifest 必须声明并校验 backend commit；本地构建也先到 staging 后原子切换。 |
| BR-09 | `scripts/rollback.sh:70-79,102-114` | 高 | PG 恢复在缺少同时间戳 meta 包时仍继续并启动服务；数据库密文可能与现有密钥不匹配。恢复后也没有应用健康和解密抽样。 | PG dump 与 meta 建立 manifest 配对，缺一默认拒绝；还原后 `chmod 600`，运行迁移版本、关键表计数、密文解密和 `/healthz` 检查后再启服务。 |
| BR-10 | `scripts/backup.sh:78-84` | 中 | 轮转只统计/删除 `itsm_full_*` 和 `itsm_pg_*`，`itsm_meta_*` 永不清理，既长期保留密钥又产生孤儿 meta；PG dump 与 meta 可能被分开删除。 | 以时间戳为备份集合轮转，dump+meta 同生同灭；孤儿集合报警并隔离；保留策略同时支持份数、天数和异地副本。 |
| BR-11 | `scripts/backup.sh:27-47` | 中 | `pg_dump -Fc` 后未执行 `pg_restore --list`，零字节/截断/格式异常不会被主动发现。 | dump 后检查文件非空并执行 `pg_restore --list`；定期在隔离库做真实恢复演练，记录 RPO/RTO 和校验结果。 |
| BR-12 | `app.py:321-333`；`wsgi.py:7-10`；`scripts/itsm.service:12`；`.github/workflows/ci.yml:12-70`；`views/system.py:61-104` | 中 | 每个 Gunicorn worker 导入 `wsgi.py` 都会执行 `init_db`/Alembic，缺少数据库级迁移锁；CI 没有“已发布迁移不可变”门禁，且运行时 GET 修复端点可绕过迁移直接 ALTER TABLE。 | 迁移从 worker 启动剥离到部署单次步骤，并使用 PG advisory lock；CI 保存已发布迁移哈希；线上 schema 修复改为只诊断和生成迁移建议，不直接改表。 |
| BR-13 | 全库无 `/healthz`；`scripts/update.sh:343-347`；`scripts/rollback.sh:102-114` | 中 | 部署/回滚只看 systemd status，没有验证数据库、密钥、迁移版本、前端入口和后台调度。 | 新增 `/healthz`（进程）和受保护 `/readyz`（DB、Alembic、密钥、静态版本）；部署与负载均衡以 ready 检查作为切换条件。 |
| BR-14 | `config.py:70-83`；`scripts/itsm.service:12` | 中 | 4 个 worker 共写一个 `RotatingFileHandler`，轮转不是多进程安全，可能丢日志或互相重命名；备份失败和安全事件因此更难追溯。 | 生产输出 stdout/journald 或集中日志；若必须文件轮转，交给 logrotate/systemd，不在每个 worker 内轮转。 |
| BR-15 | `scripts/update.sh:57-76,255-280` | 中 | 通过多个第三方镜像下载 GitHub Release，只做 ZIP 结构校验，不校验官方 SHA256/签名；镜像被劫持可替换前端资产。 | CI 发布 SHA256/签名 manifest；任何通道下载后都按固定 commit 校验；代理/镜像只是传输通道，不能成为信任根。 |
| BR-16 | `.gitignore:18-28`；当前 `git ls-files -- 'static/uploads/**'` 无输出 | 低 | 当前没有上传文件被跟踪，但忽略规则只显式列 3 个子目录；虽通用 `uploads/` 目前也会匹配嵌套目录，意图不清晰，新增子目录容易误判。 | 显式加入 `static/uploads/*` 和保留 `.gitkeep` 的例外；CI 断言运行时目录、密钥和备份文件不进入索引。 |
| BR-17 | `views/system.py:13-112`；`app.py:121` | 中 | `/system/repair-schema` 是 GET 管理端点，却会执行 `ALTER TABLE` 和 Alembic upgrade；刷新、扫描或误点击即可产生不可逆 schema 写操作，也绕过部署停服与备份步骤。 | 立即改为只读诊断；任何修复必须通过 CLI/迁移和二次确认的 POST，执行前验证备份并写审计。长期删除运行时补列机制。 |

## 8. 优先级路线图

### P0：立即（0–3 天，安全与主流程阻断）

> **实施状态：代码项已完成，提交 `507c2fd`；G1/G2 未执行。**

1. **密钥事件处置，带两个人工闸门**
   - 已完成：当前索引移除旧密钥备份，提交 `ece64de`。
   - 闸门 A：另行确认 Git 历史改写窗口，再执行 filter-repo/BFG、强推、保护分支协调和全员重新克隆；本计划不自动执行。
   - 闸门 B：确认生产停服窗口后，先完整且配对备份，运行 `scripts/rotate_secret_key.py` 预览，再 `--apply`；验证设备密码、AI Key、通知渠道密钥和密码历史可解密。旧备份需保留对应旧密钥的加密归档，不能只保留 dump。
2. **封住直接数据暴露**：匿名 `/static/uploads/*` 返回 404；下线遗留明文密码导出；未知拓扑扩展名拒绝；知识库保存前白名单净化并清理历史内容。
3. **修复权限与审计**：`status-form` 补权限和归属校验；RBAC、用户覆盖、可信网段、AI、通知渠道/规则写审计；生产缺主密钥 fail closed；去掉已知默认管理员密码。
4. **修复确定性主流程故障**：消除设备详情重复路由；补任务合同例外审核 API、payload、看板入口和通知事件。
5. **清理无理由 CSRF 豁免**：只处理内部 SPA 写端点，外部回调仍按端点显式豁免。

P0 完成定义：新增安全回归全部通过；匿名无法获取上传文件；viewer 无法改任务；知识库恶意 HTML 不执行；权限变更可查询审计；设备详情返回统一契约；合同例外任务可见、可审、可通知。

### P1：短期（1–2 个迭代，恢复能力与权限边界）

> **实施状态：P1 代码已由 `507c2fd`、`30a040e`、`c2a73bf` 完成；数据 scope 强制开关默认关闭，需生产关联审计后启用。G3 隔离恢复演练仍未完成。**

1. 加固 `backup.sh`：去掉吞错、dump 完整性校验、dump/meta 配对轮转、`.secret.key*` 权限断言、失败告警和最后成功时间。
2. 重构导入：哈希失败硬拒绝；数据库先提交，文件/密钥 staging+原子替换；pre-import 备份失败默认阻断；增加恢复演练脚本。
3. 收紧发布/回滚：Git 拉取或前端部署失败立即停；不可变 release manifest + SHA256；保留旧前端；新增 health/readiness 检查和自动回滚。
4. 将迁移移出 Gunicorn worker 启动，增加 PG advisory lock 和迁移不可变 CI；把 `/system/repair-schema` 改为只读诊断。
5. 统一数据 scope：客户可见集合作用于设备、客户、搜索、字典、详情和导出；RBAC 缓存改跨进程失效，未知角色 fail closed。
6. 补齐批量导出、AI 测试、通知测试等审计，强化密码策略和首次改密。

### P2：中期（1–2 个月，UI/字段统一与流程闭环）

1. 交付“备件申请→审批→出库→归还”“巡检异常→工单→结果回写”“SLA 临期/超时升级”“满意度回访”。
2. 交付“商机成交→合同向导”“项目任务/里程碑”“知识库独立发布权限与投票”。
3. 将至少 10 个顶层裸表格页迁入 DataTable，并统一响应式 Dialog、空态、筛选和操作列。
4. 客户页接入 metadata，补 region/device_check_template/notify_channel；修正实体/路由权限矩阵。
5. 后端 constants 生成前端状态定义，逐步消灭裸状态字符串和 JSON Text 直接解析。
6. 新增 404，主题进入 UI store，补齐暗色语义 token 和移动端视觉回归。

### P3：长期（季度级，架构收敛）

1. 收敛遗留/双轨 API：机柜 v1/v2、task_dispatch 307、旧 dashboard 偏好、旧设备/导出/拓扑端点；建立路由唯一性 CI。
2. 将路由中的事务、通知和审计收口到 service + domain event/outbox，避免业务提交成功但审计/通知丢失。
3. 建立发布单元：代码、前端、迁移、依赖锁、校验和、回滚说明同一不可变版本；定期自动恢复演练。
4. 生产日志改 stdout/集中采集，安全事件、备份失败、SLA 和通知失败进入统一可观测告警。
5. 清除 SSR 术语、兼容映射、空 templates 和孤儿模型，保留必要的兼容期指标后再删除。

## 9. Backlog 清单（产品决策项仍待确认；确定性收敛项已按后续指令更新）

| Backlog | 当前依据 | 建议验收标准 | 建议优先级 |
|---|---|---|---|
| 备件申请→审批流 | 现有借还直接扣/回库存（`services/spare_service.py:300-340`） | 申请、审批、出库、归还全链路；审批前不扣库存；全程审计 | P2 |
| 巡检异常→工单联动 | 已有 `Ticket.related_inspection_id`，无创建入口 | 一键转单、幂等、双向链接、关闭结果回写 | P2 |
| 工单 SLA 超时提醒 | 只有截止时间/红标和挂起超时 | 临期/超时事件、去重游标、分级升级、统计 | P2 |
| 满意度回访 | 全库无模型/路由 | 一次性回访、评分、差评升级、报表 | P2 |
| 商机成交自动生成合同 | 商机与合同独立 CRUD | 成交后向导补齐合同字段，确认后生成并保留来源关系 | P2 |
| 项目挂任务/里程碑 | 项目只有 CRUD/进度 | 项目任务、负责人、里程碑、关联工单/巡检、状态机 | P2 |
| 知识库投票 | 只有 `helpful_count` 展示 | 用户去重、可撤销、审计防刷、排行榜口径 | P2 |
| 知识库独立审核 | 编辑者可直接发布 | `kb:publish` 独立权限、提交/审核/退回、版本记录 | P2 |
| 10+ 页面迁 DataTable | **代码已完成（`8c0c4cf`）**：9 个常规列表迁移，专业工具页补移动卡片，使用视图 12→21 | 顶层列表统一分页、列设置、移动卡片、空态；详情小表可例外 | P2 |
| customers 页接 metadata | **代码已完成（`8c0c4cf`）**：list/detail/form 标签已消费 schema | list/detail/form/export 标签与字段集合来自同一 profile | P2 |
| `status.ts` 与后端 constants 单一真源 | **代码已完成（`8c0c4cf`）**：后端生成 TS，CI/pytest 检查漂移 | 后端生成 TS/JSON；CI 检测生成物过期 | P2/P3 |
| 404 页面 | **代码已完成（`8c0c4cf`）**：404/403 已分开并提供返回/搜索 | 404/403 可区分，有返回、搜索和错误追踪信息 | P2 |
| 暗色主题色值 | **代码已完成（`8c0c4cf`、`c54dfd9`）**：主题已入全局 store，明暗语义 token、Element Plus 映射和 Vue 硬编码色门禁已完成；浏览器视觉回归未完成 | 全局 store、语义 token、对比度与关键页面截图回归 | P2 |
| 草稿前端接入或下线 | 后端+测试完整，前端零消费 | 三类复杂表单接入；否则迁移删除模型/权限/API | P2 |
| 设备在线状态/采集任务决策 | `DeviceCollectTask` 孤儿 | 要么完整采集/心跳/重试，要么删除孤儿模型 | P2/P3 |
| 故障状态机与工单反向同步 | 目前只单向 `fault.ticket_id` | 明确状态转换和同步边界，避免双主数据 | P2 |
| 项目状态机 | 只有值校验 | 合法转换、重开权限、审计和并发测试 | P2 |
| SSR 死代码/术语/空 templates 清理 | templates 无跟踪文件；**已补兼容访问观测（`8c0c4cf`）**，删除仍待 G5 | 先采集兼容端点访问量，再删除无流量端点、`ui_version` 和旧文案 | P3 |
| 机柜双 API 收敛 | Vue 已只用 v2；**v1 已加弃用头/日志（`8c0c4cf`）**，删除待生产 30 天零调用 | 前端仅一个命名空间；兼容期告警；最终删除 v1 与重复测试 | P3 |
| task_dispatch 兼容路由下线 | **已加弃用头/日志（`8c0c4cf`）**，暂不删除 301/307 壳 | 访问量归零、调用方迁移、删除兼容端点 | P3 |
| 旧 dashboard 偏好 API 收敛 | **已加弃用头/日志（`8c0c4cf`）**，Vue 无引用；删除待 G5 | 单一 JSON 契约、CSRF 默认保护、迁移旧偏好 | P3 |
| 角色缓存跨进程一致性 | 4 worker 进程缓存 | 变更在秒级影响所有 worker，有并发回归 | P1/P3 |
| 上传文件移出 static | 当前先用守卫止血 | 私有对象存储/非 static 目录、鉴权下载、短时签名 URL | P3 |
| 审计可靠投递/outbox | helper 独立 commit 且失败不阻断 | 业务与审计同事务或可靠 outbox，告警可观测 | P3 |
| 不可变发布与灾备演练 | Release 可变、恢复未实演 | 每版本 manifest；季度隔离恢复；记录 RPO/RTO | P1/P3 |

## 10. 实施顺序、测试与验收建议

### 10.1 依赖顺序

1. 先处理密钥、匿名上传、XSS、越权和默认凭据，避免在继续开发期间扩大暴露面。
2. 再修设备详情和合同例外任务，恢复现有主流程可用性。
3. 然后加固备份/导入/发布；此阶段完成前不建议批量实施 schema 和文件目录迁移。
4. P0/P1 代码止血完成后，G1 历史改写、G2 密钥轮换可作为独立运维窗口挂起，不再阻塞无需生产变更的 P2/P3 代码收敛。
5. P2 字段/UI 确定性工作可直接推进；业务流程必须先过 G4，兼容路由删除必须先过 G5，不能用开发者推测替代产品规则或生产调用证据。

### 10.2 计划中的测试增量

| 变更域 | 测试建议 |
|---|---|
| CSRF | 扩展 `tests/test_csrf.py`：5 个写端点无 token 拒绝、有 token 成功 |
| 任务越权 | 新增 viewer 调用 `status-form` 返回 403；合法角色仍可按状态机转换 |
| 上传鉴权 | 匿名 `/static/uploads/<file>` 为 404，已登录内网/外网流程用户为 200；vendor/app 静态资源不受影响 |
| 知识库 XSS | script、事件属性、`javascript:` 被删除；允许的表格/列表/链接保留；历史清洗幂等 |
| 拓扑上传 | `.exe/.html/双扩展` 拒绝，允许类型成功，大小限制生效 |
| 审计 | RBAC、用户覆盖、AI、可信网段、通知配置/测试、批量导出均断言 `AuditLog` 的 action/target/IP，且不含 secret |
| 合同例外任务 | 创建后在看板可见；无 `contract:review` 403；通过/拒绝转换、审计、站内和渠道事件正确 |
| 设备详情契约 | `/api/devices/<id>` 只有一条有效规则并返回 `{code:0,data}`；密码字段不下发 |
| 数据范围 | all/department/self 对列表、详情、搜索、字典、导出结果一致，直接猜 ID 不能绕过 |
| data_io | sha256 不一致硬拒绝；DB commit 失败不替换密钥/文件；落盘失败可回滚；pre-import 备份失败阻断 |
| backup/update | shell 测试模拟 tar、pg_dump、pg_restore、git、curl、前端部署失败，断言退出码与不重启行为 |
| 迁移 | 并发启动仅一个迁移者；已发布 migration hash 变化使 CI 失败；从空库和上一版本均可升级 |

### 10.3 当前验证结果

- `.venv/Scripts/python -m pytest tests/`：**914 项全量通过**，退出码 0，耗时 2269.13 秒（37:49）；告警均为既存弃用/兼容性告警，无测试失败。
- `.venv/Scripts/python -m ruff check .`：**通过**，`All checks passed!`。
- 前端 `npm run lint`：**通过**（27 条既有 warning、0 error）；`npm run test:unit`：**33 项通过**；`npm run build`：**通过**。
- Git Bash `bash -n`：`backup.sh`、`update.sh`、`lib-release.sh` **全部通过**；发布恢复 3 条故障注入测试全部通过。
- 当前共收集并通过 914 项测试；测试 PostgreSQL 改为每次运行使用随机目录，避免中断后的 `postmaster.pid` 污染后续运行。
- 生产主机、systemd、定时任务、备份状态和密钥权限已于 2026-08-21 核验；尚未完成的发布门禁为隔离 PostgreSQL 的真实备份—恢复—解密—`readyz` 演练，以及备份失败告警的实际送达验证。

## 11. 需要单独确认的高风险操作

1. **Git 历史改写**：会重写 commit SHA、影响开放分支/PR/所有克隆。2026-08-21 已获执行授权；只在 G2 完成后实施，并记录 refs 范围、强推结果、远端 blob 验证和重新克隆通知。
2. **主密钥轮换 `--apply`**：需要停服、已验证且配对的备份、敏感字段盘点和回滚方案；轮换后当前库使用新密钥，旧备份只有在保留其配对旧密钥时才可恢复。2026-08-21 已获执行授权，须先通过 G3 并明确实际停服窗口。
3. **生产文件权限与上传迁移**：`chmod 600 .secret.key*` 应由备份/恢复/部署脚本共同断言；从 static 迁出文件需先盘点所有数据库路径和下载入口，不能直接移动。
4. **恢复/迁移演练**：必须在隔离实例进行，不得以生产库作为首次验证环境。
