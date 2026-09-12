# 流程问题与后续建议（暂缓实施）

日期：2026-09-12。按用户要求独立存档，后续再考虑，不作为当前 UI 适配的实施清单。保留原编号、证据、优先级与建议；WF08–11 中已完成的通知/导入修正仅记录历史，其他建议未实施。

## 业务定位修正（用户确认）

系统审核用于内部把关材料准确性与标准性，客户需要的是最终服务信息，不需要再次验收。内部全局通知保留审核通过、退回原因；客户群不展示内部审核过程，仅展示巡检主题、服务状态及实施时间/工作量。客户反馈为可选，不推进业务状态、不阻塞结束。

因此 WF01、WF04 原建议中的“增加或统一客户验收闭环”不再作为改造目标。存量工单状态/验收接口暂不迁移；未来如清理历史命名，应统一为内部质量审核/归档语义，而不是新增客户审批环节。

## 标准依据与判断口径

1. [国家标准全文公开系统：GB/T 28827.1-2022](https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=D8FCA634AA99E6AD0F9EDAC3A9A00670)：现行，2023-05-01 实施。本次采用 2022 版，避免继续按废止的 2012 版通用要求作判断。
2. [国家标准平台：GB/T 28827.2-2012 交付规范](https://std.samr.gov.cn/gb/search/gbDetailed?id=71F772D7E169D3A7E05397BE0A0AB82A)：查询标记现行，作为交付管理参考。
3. [ITSS 分会换版工作通知](https://itss.cn/web/itss/a/7d4b4ba3a8f8453da495964889b2f7ff)：确认通用要求 2022 版与能力成熟度 2023 版的评估切换安排。
4. [交付要求修订项目](https://std.samr.gov.cn/gb/search/gbDetailed?id=456CE2749F33B3D7E06397BE0A0A7328)：2026 年修订项目，尚不能作为已发布现行标准的强制依据。

官方页面用于核对标准身份、版本与适用方向；当前未获取完整授权正文，不编造条款编号。下列“流程差距”是对服务策划、实施、检查、改进及可追溯性的工程判断，不等于标准逐条不符合项。ITSS 评价还涉及人员、资源、技术、过程和组织证据，不能仅检查软件页面就宣称通过。

## 流程问题与建议

| 编号 | 级别 | 代码证据 | 不合理之处/风险 | 改善及验收条件 |
|---|---|---|---|---|
| WF01 | 口径已澄清 | services/ticket_service.py:audit_ticket；utils/constants.py:TICKET_CHECKED | 旧“已验收”命名容易被理解为客户动作，实际为内部质量审核 | 不新增客户验收要求；历史命名及状态迁移后续考虑 |
| WF02 | P1 | services/ticket_service.py:99–135、442；utils/constants.py:SLA_HOURS_BY_PRIORITY | SLA 按全局优先级固定小时计算，缺客户合同服务窗口、响应/解决目标分离与节假日模型 | 建立合同服务目录与 SLA 快照；验证暂停、重开、改优先级不悄悄改写已承诺目标 |
| WF03 | P1 | services/ticket_service.py:219、233；models/ticket.py:assigned_to；utils/notifications.py:notify_by_name | 处理人按姓名/用户名字符串绑定，重名、改名和停用后责任归属不稳定 | 引入负责人 user_id 与显示名快照，迁移冲突人工核对；提醒按当前负责人而非字符串猜测 |
| WF04 | 不作为流程缺口 | services/notification_management.py:confirm_event | 原建议误将可选客户回执视为必需的验收流程 | 客户仅接收最终信息；入口文案改为可选反馈，不改变状态与计时；不要求合并为客户验收环节 |
| WF05 | P1 | services/fault_service.py:sync_fault_from_ticket；models/ticket.py:root_cause_category；services/ 目录 | 有故障同步和根因字段，但核查范围未见独立问题调查、已知错误、长期措施及效果验证状态机 | 高频故障可升级问题单，责任人/措施/到期/验证闭环；不能用填根因分类替代问题管理 |
| WF06 | P1 | blueprints/asset/config_backups.py；models/device.py；services/ 目录 | 配置备份与密码历史可追溯，但核查范围未见统一变更申请、影响评估、审批、维护窗口、回退验证链 | 配置变更记录关联设备/工单/审批/前后版本，紧急变更需事后复核；不能把“存在备份”视为变更管理完成 |
| WF07 | P2 | services/ticket_service.py:354；services/fault_service.py:147；services/spare_service.py:197、212 | 关闭、故障/出入库删除与数据历史的保留策略需统一 | 明确作废、冲销、删除边界和保留周期，验收跨报表库存/故障引用一致性；本轮不修改生产历史 |
| WF08 | P2 | services/notification_jobs.py；services/notification_policy.py | 原提醒只有巡检主管升级、时间硬编码，工单和摘要不完整 | 本轮补齐规则配置、工单升级、工单/巡检/失败摘要，并验证范围及去重 |
| WF09 | P2 | services/notification_management.py:metrics | 原通知缺耗时和客户/渠道统计 | 本轮补齐范围内分组与含排队平均投递耗时；接口接受率不称客户已读率 |
| WF10 | P1 | utils/backup_config.py:record_backup_result；services/auth_service.py:verify_operation_code；services/notification_outbox.py | 备份/安全锁定及合同例外通知原有提交后窗口 | 本轮将持久化结果与通知入队结合；进程内高频访问检测仍需区分“检测持久化”与“消息投递持久化” |
| WF11 | P2 | services/device_import_service.py:prepare_device_import；tests/test_vue_api_inspections.py:832 | 仅补类型字典却计设备更新，资产变更统计失真 | 本轮修正，设备未变计跳过，字典仍随事务补齐；原巡检用例与补字典回归已通过 |
| WF12 | P2 | utils/backup_config.py:get_backup_status；scripts/backup.sh、rollback.sh | 已有备份状态和 RPO 年龄，但实际恢复时长、恢复成功证据仍需演练 | 在隔离环境记录备份/恢复校验与实际 RTO；生产窗口单独验收，不以脚本存在代替恢复可用性 |
| WF13 | P2 | models/customer.py、models/user.py、utils/permission.py；services/offboard_service.py | 已有组织/范围/离职处理基础，岗位能力、服务授权与交接质量需组织证据 | 形成服务责任矩阵、交接清单和能力培训记录；软件关联不等于能力证明 |
| WF15 | P1 | blueprints/vue_api.py:api_ticket_action；services/ticket_service.py:audit_ticket | 路由传入 realname，服务却只按 username 查询审核用户，实名和账号不同时版本 reviewed_by 可能为空 | 后续传入明确 reviewer_user_id，并用实名不同的账号验证审计链；不依赖字符串反查 |
| WF14 | P2 | models/knowledge.py；blueprints/vue_api_ops.py；blueprints/ops/reports.py | 已有知识和报表模块，持续改进的计划—责任—完成—复核证据未形成统一链 | 将 SLA、重复故障、客户反馈形成改进项，并可追溯验证结果 |

## 正向核查结果

- 巡检首次提交冻结实施结束，退回/待审不会自动继续计时，符合分离执行和审核等待的管理需要。
- 版本化提交、审核意见、修改要求和报告权限已有基础，新增通知不得外发内部审核正文。
- 客户群凭据加密、客户范围、外网操作 MFA、上传安全检查与后台白名单发送是已存在/本轮保留的边界。
- 静默、摘要、重试和客户回执解决沟通记录问题，但不能替代合同 SLA 或服务验收。

## 整改路线与 Backlog

| 优先级 | 范围 | 完成标准 |
|---|---|---|
| P0 | 本次核查未确认可直接定级 P0 的新缺陷 | 不把缺少运行证据推定成已发生安全事故 |
| P1 | WF01–06、WF10、WF15 | 明确状态/验收/责任/SLA/问题/变更契约；补齐对象级与事务测试，保留历史迁移方案 |
| P2 | WF08–09、WF11 | 本轮代码补齐、前后端回归和浏览器抽查；已修改与待验收分开记录 |
| P2 | WF07、WF12–14 | 数据保留、恢复演练和持续改进台账；涉及生产和组织制度需实际操作者确认 |

审查是本次用户要求的交付物；对工单状态、合同 SLA、问题管理、变更审批等业务规则只提出有证据的调整方案，不在 UI 修复中暗改历史业务语义。


相关 UI 验证见 [UI 检查报告](project-ui-itss-audit-2026-09-12.md)。
