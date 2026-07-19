# 变更日志

本文档记录 ITSM 运维管理系统的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [未发布] — 2026-07-19

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
