# 兼容端点退役清单

更新日期：2026-08-13

下列端点尚未直接删除。访问会返回 `Deprecation: true`、`Link: <successor>; rel="successor-version"`，并写入 `compat_endpoint_access` 结构化日志。只有生产连续 30 天零调用且调用方已完成迁移后，才进入删除批次。

| 兼容范围 | 后继契约 | 当前调用方证据 | 删除条件 |
|---|---|---|---|
| `/api/rack/*` | `/api/v2/rack/*` | Vue 已全部使用 v2；测试仍覆盖 v1 兼容 | 生产 30 天零调用，删除 `blueprints/rack.py` 及 v1 测试 |
| `/api/devices/<id>/reveal-password`、`password-history` | `/api/v2/devices/<id>/*` | Vue 已全部使用 v2；安全回归仍覆盖旧契约 | 生产 30 天零调用，删除 `blueprints/asset/devices.py` |
| `/task-dispatch/*` | `/app/task-schedule`、`/task-schedule/*` | 侧栏已无入口 | 生产 30 天零调用 |
| `/inspection-tasks*` | `/app/task-schedule`、`/task-schedule/*` | Vue 已使用任务安排 API | 生产 30 天零调用 |
| `/api/dashboard/preferences*` | 无 API 后继；工作台入口为 `/app/` | Vue 无引用；仅兼容测试引用 | 确认卡片自定义功能不再需要且生产 30 天零调用 |
| `/api/dashboard/opportunity-stages` | `/api/dashboard/overview` | Vue 无引用 | 生产 30 天零调用 |
| `/system/ui-version` | `/api/system/ui-version` | Vue 已使用 JSON API | 生产 30 天零调用 |
| `/api/sidebar/reset` | `/api/system/sidebar/reset` | Vue 已使用 `/api/system/*` | 生产 30 天零调用 |

日志查询建议按 `compat_endpoint_access` 聚合 `path`、`method`、`user_id` 和最近访问时间；确认无外部脚本、旧书签或第三方调用后，再单独提交删除与回滚方案。
