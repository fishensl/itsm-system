# 业务工作流矩阵

本矩阵用于约束“页面按钮、API、服务层状态机、通知与测试”保持一致。状态值的唯一来源是
`utils/constants.py`，流转必须经过对应 service，禁止页面或路由直接写状态字符串。

| 业务域 | 主流程 | 纠正/异常出口 | 权限与审计 | 回归基座 |
| --- | --- | --- | --- | --- |
| 工单 | 待派单 → 已派单 → 处理中 → 待审核 → 已验收 → 已关闭 | 撤回重派；审核/验收退回处理中；处理中可挂起并顺延 SLA；已关闭可受控重开；合同过期先走合同审批 | 派单、审核、验收、重开分权；敏感导出和删除审计 | `test_ticket_service.py`、`test_vue_api_tickets.py`、`test_customer_contract.py` |
| 巡检任务 | 待执行 → 执行中 → 待审核 → 已完成 | 退回执行中；待执行/执行中可取消；终态受控重开；存在巡检记录时必须报告审核通过才能完成 | 审核独立权限；报告版本、审核人、意见留档 | `test_inspection_service.py`、`test_vue_api_inspections.py`、`test_vue_api_task_schedule.py` |
| 报告版本 | 草稿/上传 → 待审核 → 已通过或已退回 | 退回后重新上传产生新版本，旧文件与审核意见不覆盖 | 提交人与审核人分离；审核清单留痕 | `test_vue_api_inspections.py`、`test_vue_api_tickets.py` |
| 设备密码导出 | 申请 → 待审核 → 通过 → 一次性下载 | 拒绝、过期、已下载均不可重复取包 | `device:reveal`、操作码（开关）、AES ZIP、表审计 | `test_export_review.py`、`test_security_passwords.py` |
| 备件库存 | 采购入库；销售 FIFO 出库；借用扣减 → 归还回补 | 删除采购/销售单自动反向冲销；超借/超卖拒绝 | 备件增删改权限；库存流水留痕 | `test_spare_service.py`、`test_spare_borrow.py`、`test_vue_api_sales.py` |
| 销售 | 商机顺序推进 → 成交/失败；报价草稿 → 已发送 → 接受/拒绝；合同草签 → 已签 → 执行中 → 完成/终止 | 各终态不可回退；合同状态联动项目 | `sales:view/edit`；服务层转换表校验 | `test_vue_api_sales.py`、`test_customer_contract.py` |
| 离职 | 停用 → 会话版本递增 → 清 MFA/恢复码 → 外部钩子 → 审计 | 外部钩子失败只告警，不回滚访问撤销 | admin + 操作码（开关）；历史业务记录全部保留 | `test_offboard.py`、`test_session_security.py` |

## 统一实现要求

1. Vue 只展示服务端允许的动作；不能依靠隐藏按钮替代后端权限与状态校验。
2. 列表、详情、表单、导出字段从 `domain_metadata/` 选择 profile，不重复声明业务标签和导出码。
3. 所有终态重开、审核、密码查看、密码导出、账号撤销必须写表审计。
4. 新流程必须同时补 service 单测与 API 断言；已有用例仅在接口正式废弃时迁移。
5. 强制身份能力均默认关闭，批次上线后再按 `docs/SECURITY_GUIDE.md` 渐进启用。
