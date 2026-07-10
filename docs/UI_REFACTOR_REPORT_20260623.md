# UI 风格统一与可读性重构 - 验证报告

## 改造概览（commit ad3594a..f34ec04，共 13 个 commit）

| # | Commit | 内容 |
|---|---|---|
| 1 | ad3594a | 扩展 design token 体系 + 新增 utility 类 |
| 2 | d1fe908 | body 升 14px + style.css 字体/颜色走 token |
| 3 | 3819588 | theme-pages.css 重构（--bs-* 重映射 + 去 !important）|
| 4 | ff39bbe | 任务排期模块 - bg-light → .surface-muted |
| 5 | 6301eaf | 设备资产模块 - 字体/颜色 token 化 |
| 6 | b25c564 | 巡检/工单模块 - bg-light + 删除按钮字号 |
| 7 | 9f0c403 | 机柜模块 - 硬编码色与小字 token 化 |
| 8 | 2c7b407 | 权限/RBAC 模块 - 硬编码色全部 token 化 |
| 9 | 69a4005 | 知识库/工具/系统/调度模块 - bg-light 替换 |
| 10 | b0d544a | 报表/工作台/AI 配置/_ui - 收口剩余 bg-light + inline |
| 10b | 9b32346 | 补提 reports/list.html（被 .gitignore 通配匹配） |
| 11 | bb8ac4a | 抽 theme.js + login.html 规范化 |
| 12 | f34ec04 | 清理 style.css 与局部 style 重复定义 |

## 关键指标对比

| 指标 | 改造前 | 改造后 | 备注 |
|---|---|---|---|
| theme-pages.css `!important` | ~60 | **5** | 剩余 5 处用于 inline style 兜底 |
| theme-pages.css 行数 | 386 | 263 | 删 30% 冗余 |
| 模板硬编码 `color:#fff` 文字 | 11+ | **0** | 全走 `--text-on-primary` |
| 模板 `bg-light` / `--bs-tertiary-bg` | 25+ | **0** | 全替换为 `.surface-muted` |
| 模板 inline `font-family:monospace` | 7 | **0** | 全走 `var(--font-mono)` 或 `font-monospace` |
| 模板 inline `font-size` | 30+ | **10** | 剩余为图标尺寸(em)、错误页 96px 等预期 |
| Design token 总数 | 55 | **90+** | 新增 typography/text/utility token |

## 新增能力

- **Typography token 层**：`--fs-xs..3xl`、`--fs-code`、`--lh-*`、`--fw-*`、`--font-sans/mono`
- **Text 语义色**：`--text-primary/body/secondary/muted/disabled/on-primary`，浅深各一套
- **Surface 层级修正**：
  - 浅色 `--surface-strong` 由 `#ffffff` 改为 `#fbfcfd`（与 `--surface` 区分）
  - 深色 `--surface-muted` 由 `#0d1117` 改为 `#161b22`（介于 `--background` 与 `--surface` 之间，有真正层级）
- **Bootstrap 根变量重映射**：深色块新增 `--bs-body-bg/--bs-tertiary-bg` 等，让 BS 组件自动跟随
- **Utility 类**：`.surface-{muted,strong,soft}`、`.bordered{,-soft}`、`.fs-xs..3xl`、`.text-on-primary` 等
- **公共 theme.js**：base.html 与 login.html 共用同一套主题切换逻辑

## 静态验证

- Jinja 语法：74 个模板全部通过（2 个 `from_json` 报错是应用自定义过滤器，与本次改造无关）
- Flask 启动 + 登录 + 8 个核心页面（`/`、`/devices`、`/rack`、`/permissions`、`/reports`、
  `/inspections`、`/tools`、`/system/backup`）全部 200 渲染成功

## 已知遗留 / 未动

- `errors/error.html` 96px 大错误码 — 视觉占位，保留
- `spare_parts/list.html` 24px、`spare_parts/detail.html` 96px 等 — 图标尺寸，非字号语义
- `tickets/form.html` 0.6em、`customers/detail.html` 1.2em、`topologies/list.html` 1.25em
  — 都是图标相对尺寸，保留
- 机柜颜色选择器默认值 `#0d6efd` — 是用户可改的色值，无法走 token
- `.gitignore` 里 `reports/` 通配匹配把 `templates/reports/` 也忽略了，commit 10b 用 `-f`
  强制提交。**建议后续把 .gitignore 改为 `/reports/` 仅排除根目录**

## 验证建议（人工，需启动应用）

启动应用后浏览以下页面，浅色 + 深色 各看一次：

1. `/login` — 字号/防闪/主题切换
2. `/` — 工作台 greeting/卡片/指标
3. `/devices` — 表格密度、城市/客户折叠头
4. `/devices/<id>/config_backups` — code/diff 字体
5. `/rack` — 极小字对比度、原硬编码白字
6. `/task_schedule`（按工程师/状态/客户三种视图） — 卡片色条、看板背景
7. `/permissions` — 原硬编码绿/红/蓝改变量后一致性
8. `/inspections/new` — 表单控件深色（`!important` 减少后）
9. `/knowledge_base/<id>` — 富文本预览背景
10. `/reports` — accordion + 多个 bg-light 头

## 回滚

完整备份在：`D:\CODE\itsm-system_20260525.backup_20260623_230724_ui-refactor`

单 commit 回滚：`git revert <hash>`
回到改造前：`git reset --hard 91e3b6e`（注意：会丢弃所有 13 个 commit）
