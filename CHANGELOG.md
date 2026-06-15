# 变更日志

本文档记录 ITSM 运维管理系统的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [v1.0.0] — 2026-06-15

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
