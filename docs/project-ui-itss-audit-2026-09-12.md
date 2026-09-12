# 全项目 UI 一致性与响应式适配检查

日期：2026-09-12；基线：ce40ee6 加本地未提交通知拓展；本文件为检查报告，不代表生产已部署。

## 结论

UI 已有统一 token、DataTable 与窄屏弹窗规则；主要不一致集中于新增通知页面、低字号辅助文字和代码字体声明，而非所有页面都需要重做。

检查覆盖全部 65 个 `frontend/src` Vue 文件、全局样式及路由清单，扫描原始候选见 `ui-consistency-inventory-2026-09-12.json`。共 47 个初筛候选，包含媒体查询断点、图形标签、详情子表等正常设计，不能将候选数当作缺陷数。浏览器抽查结果见末尾；静态范围不等于所有页面已逐像素验收。

## 桌面适配基准

桌面以 1920×1080（1080p）为主要适配基准，使用自适应布局，不固定页面为 1920px 宽。保留较窄窗口兼容：1440px 是此前补充测试宽度，不是桌面设计上限。筛选区在桌面常驻，只有小于 768px 才折叠。1080p 屏幕在系统缩放或非最大化窗口下仍按实际 CSS 视口适配。

## UI 问题与处理

| 编号 | 级别 | 证据（检查时行号） | 现象及影响 | 处理 |
|---|---|---|---|---|
| UI01 | P2 | frontend/src/styles/index.css:88；components/FilePreview.vue:120；views/devices/index.vue:2108 | 业务字体、代码字体分别声明，`--font-mono` 多处无统一定义；跨系统回退不同 | 统一 UI/代码字体 token，保留代码等宽语义，不把设备配置改为普通文本字体 |
| UI02 | P2 | views/dashboard/index.vue:273、327、378；views/taskSchedule/index.vue:1471、1527、1563、1598；views/system/backup.vue:390、403、413 | 多处普通辅助说明为 11px，和全局最小 12px 不一致 | 普通提示提升至统一最小字号；机柜 U 位图形标签单列检查，不批量放大所有图形 |
| UI03 | P2 | views/notifications.vue:3；views/customers/notifications.vue:3；views/system/notificationCenter.vue | 新增通知页裸标题、控件直接堆叠，筛选及操作间距不足 | 使用 page-header/page-title/filter-row、分区与响应式网格 |
| UI04 | P2 | components/CustomerNotifyDialog.vue；components/NotificationTemplates.vue | 静默两组步进控件和说明共用一行，模板 pre 长行可能溢出 | 控件可换行；预览保留换行并自动折行；长内容断词 |
| UI05 | P3 | components/CustomerNotifyDialog.vue；views/spare/PartExpandRow.vue；views/tools/PacketAnalyzer.vue | 原生表格未使用移动卡片 | 前两者是嵌套历史明细，不误判为主列表违规；抓包分析是高密度工具表，建议后续独立移动摘要视图 |
| UI06 | P3 | views/rack/index.vue:622 | U 位图 10px 标签属于高密度图形 | 保留比例，建议提供点击后的正常字号详情及放大检查；不把图形标签统称字体错误 |

浏览器额外确认 UI07（P2）：深色模式卡片实际为 rgb(29,30,31)，与设计 token #1f2937 不一致；原因是 Element Plus 的 html.dark 选择器覆盖 :root 语义映射。本轮提高映射选择器一致性并复验，不把抗锯齿截图差异误判为字体文件错误。

浏览器额外确认 UI08（P1）：`frontend/vite.config.ts:deepElementPlusResolver` 把 ElFormItem、ElCollapseItem、ElDescriptionsItem 等子组件的 JS 父目录也用于样式目录，漏载各自 CSS。实际表单项缺默认间距、折叠标题高度异常。本轮将 JS 导出路径和组件自身样式路径分开；这是全局排版根因，需构建及代表页面回归。

## 流程建议另行存档

流程问题、ITSS 参考依据和后续路线已移至 [流程问题与后续建议](itss-workflow-backlog-2026-09-12.md)，按用户要求暂缓实施。

## 手机端操作便利性（本轮追加并实施）

| 编号 | 代码证据 | 原问题 | 本轮处理 |
|---|---|---|---|
| UI09 P2 | components/MobileFilterPanel.vue；views/devices、customers、tickets、taskSchedule/index.vue | 筛选控件占满首屏，收起后不易知道条件是否仍生效 | 手机默认折叠，保留输入及已选数量；桌面常驻；字段在窄屏按整行排列 |
| UI10 P2 | layouts/MainLayout.vue；components/GlobalSearch.vue；styles/index.css | 搜索包装类未落到可见节点，手机顶部仍占位；搜索缺明确关闭入口 | 显式包装桌面搜索，手机底部打开搜索、明确关闭按钮、结果宽度受视口约束 |
| UI11 P2 | components/DataTable.vue；components/GroupTree.vue；views/devices、customers/index.vue | 卡片详情依赖点整行；长客户名挤压操作；小按钮难点 | 明确查看/收起详情，客户名称换行、操作分行，常用按钮 44px 触控高度，底部导航语义按钮 |
| UI12 P1 | styles/index.css；components/CustomerNotifyDialog.vue | 长弹窗需滚到底部才能保存，按钮换行后最末行超屏 | 操作移到 footer；弹窗按动态视口限制总高度，正文独立滚动；表单标签手机置顶 |
| UI14 P1 | views/system/notificationCenter.vue；notificationCenter.spec.ts | 统计响应更新导致内联 query 对象重建，反复触发表格请求，增加移动流量 | 使用仅随筛选变化的缓存查询对象；测试验证响应不重建查询、状态筛选仍生效 |
| UI13 P2 | views/taskSchedule/index.vue；views/system/notificationCenter.vue | 统计卡横向挤压，通知管理设置占用日常阅读空间 | 手机统计卡四列网格；看板整屏一列横滑；通知规则/模板管理折叠 |

手机优化不修改权限、MFA、审核计时或真实消息发送条件；未自动发布客户进展或发送机器人测试。

## 本轮验证

- 最终前端全量 Vitest 33 文件、100 项通过，包含筛选保留、卡片详情、客户通知及连续刷新回归。Vue 类型检查及生产构建通过；构建仍有既有大块与第三方注释提示。
- SQLite 相关后端回归 181 项通过（通知补齐、巡检、设备、工单、计时、备份）；早期夹具失败已修正并完成复跑。不是全项目 pytest 全量通过声明。
- Ruff 与 Git diff 空白检查通过。PostgreSQL 通知补齐/修正专项 10 项通过；前序已完成通知 outbox/管理核心事务和并发回归。
- 浏览器为本地隔离 QA 服务与虚构数据，不使用生产库或真实机器人。实际 iframe 内容宽度 390px、390px scrollWidth；手机设备筛选展开/收起保留输入、客户通知弹窗、任务安排、搜索打开/关闭均抽查。
- 客户通知弹窗 footer 实测 bottom=816px，位于 844px 高视口内；长名称不挤出保存入口。任务统计卡改为网格后不再需要横滑统计区。
- 已补查主要桌面基准 1920×1080：设备列表、任务安排和通知中心实际视口均为 1920×1080，页面 scrollWidth=1920，无页面级横向溢出；设备与任务筛选保持显示。此前 1440px 为窄窗口兼容抽查，继续保留。浅/深色主题抽查通过。深色卡片 rgb(31,41,55) 与 #1f2937 token 一致，浅色 rgb(255,255,255) 与 #ffffff 一致；表单项恢复 18px 默认间距。当前验收页未记录浏览器 error。
- 这是代表页面的 Chromium 浏览器窄屏检查，不是所有 65 个页面逐像素验收；真实 iOS/Android 键盘、安全区、文件选择和弱网体验未实机验收。机柜、拓扑、抓包等专用高密度工具的进一步移动视图仍在 P3 Backlog。
- 本地未提交/未推送；生产部署、真实群联调、离线包安装及恢复演练均未执行，不标为完成。
