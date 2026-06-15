# ITSM 运维管理系统

基于 Python Flask 的 IT 运维管理系统，覆盖客户管理、设备资产管理、巡检任务、故障工单、备件库存、销售管线、知识库、机柜可视化等全流程，支持自动生成 Word 报告。

---

## 目录

- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [部署到 Ubuntu 24](#部署到-ubuntu-24)
- [在线更新](#在线更新)
- [项目结构](#项目结构)
- [模块说明](#模块说明)
- [数据库模型](#数据库模型)
- [角色与权限](#角色与权限)
- [报告生成](#报告生成)
- [安全](#安全)
- [备份与回滚](#备份与回滚)
- [常见问题](#常见问题)

---

## 环境要求

| 依赖 | 版本 |
|------|------|
| Python | ≥ 3.10 |
| Flask | 3.1.1 |
| Flask-Login | 0.6.3 |
| Flask-SQLAlchemy | 3.1.1 |
| Flask-WTF | 1.3.0 |
| Flask-Limiter | 4.1.1 |
| python-docx | 1.1.2 |
| cryptography | 44.0.3 |
| openpyxl | ≥ 3.1.0 |
| psutil | ≥ 5.9.0 |
| gunicorn | ≥ 23.0.0（生产环境） |

完整依赖见 `requirements.txt`。

---

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/fishensl/itsm-system.git
cd itsm-system
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动

```bash
python app.py
```

首次启动会自动：
- 创建 SQLite 数据库 `instance/itsm.db`
- 创建默认管理员账号 `admin / admin123`
- 预置设备类型、故障类型等种子数据

### 4. 访问

浏览器打开 `http://127.0.0.1:5000`

---

## 部署到 Ubuntu 24

### 一键部署

```bash
# 在 Ubuntu 24 上执行
export ITSM_REPO_URL=https://github.com/fishensl/itsm-system.git
sudo bash scripts/deploy.sh
```

脚本自动完成：
1. 安装系统依赖（Python、git 等）
2. 克隆代码到 `/opt/itsm`
3. 创建 Python 虚拟环境并安装依赖
4. 生成密钥文件（`.env`、`.secret.key`）
5. 初始化数据库
6. 创建 `itsm` 系统用户
7. 安装 systemd 服务并启动

部署后访问 `http://<服务器IP>:5000`

### 已有手动部署的迁移

如果之前在 Ubuntu 24 上已经手动部署了旧版本（直接复制文件），执行以下命令平滑切换到 GitHub 更新模式：

```bash
export ITSM_REPO_URL=https://github.com/fishensl/itsm-system.git
sudo bash scripts/migrate-to-github.sh
```

脚本会自动：
1. 备份现有数据（数据库、密钥、上传文件）
2. 初始化 git 并关联 GitHub 仓库
3. 拉取最新代码
4. 恢复本地运行时数据
5. 安装/更新 Python 依赖
6. 安装 systemd 服务
7. 停止旧的手动进程，启动 systemd 服务

迁移完成后，后续更新只需 `sudo bash /opt/itsm/scripts/update.sh`。

### 目录结构

```
/opt/itsm/                    # 应用根目录（Git 工作树）
├── app.py                    # Flask 主应用
├── wsgi.py                   # Gunicorn 生产入口
├── models.py                 # 数据库模型
├── config.py                 # 应用配置
├── requirements.txt
├── blueprints/               # Flask 蓝图模块（13 个）
├── services/                 # 服务层（8 个）
├── utils/                    # 工具模块（11 个）
├── templates/                # Jinja2 模板（40+ 目录）
├── static/                   # CSS/JS/图片/第三方库
├── scripts/                  # 部署运维脚本
│   ├── deploy.sh             # 首次部署
│   ├── update.sh             # 在线更新
│   ├── backup.sh             # 定时备份
│   ├── rollback.sh           # 紧急回滚
│   ├── migrate.sh            # 数据库迁移
│   ├── itsm.service          # systemd 单元文件
│   └── .env.example          # 环境变量模板
├── instance/                 # SQLite 数据库（运行时）
├── logs/                     # 应用日志（运行时）
├── reports/                  # 生成的 Word 报告（运行时）
├── uploads/                  # 用户上传文件（运行时）
├── backups/                  # 备份文件（运行时）
├── .secret.key               # AES 加密密钥（运行时生成）
├── .env                      # 环境变量（运行时生成）
└── venv/                     # Python 虚拟环境（运行时生成）
```

### 生产环境建议：Nginx 反代

```nginx
server {
    listen 443 ssl;
    server_name itsm.example.com;
    ssl_certificate     /etc/ssl/certs/itsm.pem;
    ssl_certificate_key /etc/ssl/private/itsm.key;

    location /static/ {
        alias /opt/itsm/static/;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 在线更新

```bash
# 开发者推送代码后，服务器执行
sudo bash /opt/itsm/scripts/update.sh
```

更新流程：
1. 自动备份当前数据库
2. 暂存本地修改
3. `git pull` 拉取最新代码
4. 更新 Python 依赖
5. 执行数据库迁移（如有）
6. Gunicorn 优雅重启（零停机）

### 常用运维命令

```bash
sudo systemctl status itsm          # 查看服务状态
sudo journalctl -u itsm -f          # 查看实时日志
sudo systemctl restart itsm         # 重启服务
sudo bash /opt/itsm/scripts/backup.sh   # 手动备份
```

---

## 项目结构

```
itsm-system/
├── app.py                        # 主应用入口（登录、首页、拓扑、用户管理、系统设置）
├── wsgi.py                       # Gunicorn 生产入口
├── models.py                     # 数据库模型（46 个模型类，45 张表）
├── config.py                     # 应用配置（密钥、数据库、日志）
├── requirements.txt              # Python 依赖
├── .gitignore                    # Git 忽略规则
│
├── blueprints/                   # Flask 蓝图（业务路由）
│   ├── __init__.py               # 蓝图注册
│   ├── asset.py                  # 设备资产管理
│   ├── categories.py             # 客户单位分类
│   ├── contract_tasks.py         # 合同自动巡检任务
│   ├── customer.py               # 客户管理
│   ├── departments.py            # 部门管理
│   ├── drafts.py                 # 表单草稿 API
│   ├── ops.py                    # 巡检/故障/工单/知识库/模板
│   ├── rack.py                   # 机柜管理
│   ├── sales.py                  # 销售管线
│   ├── spare.py                  # 备件管理
│   ├── task_dispatch.py          # 工单调度
│   └── tools.py                  # 网络常用工具
│
├── services/                     # 服务层（业务逻辑）
│   ├── base.py                   # 基类（事务装饰器）
│   ├── customer_service.py       # 客户（自动分级）
│   ├── device_service.py         # 设备（密码历史）
│   ├── fault_service.py          # 故障记录
│   ├── inspection_service.py     # 巡检（审核→生成报告）
│   ├── sales_service.py          # 销售管线
│   ├── spare_service.py          # 备件（FIFO 出库）
│   └── ticket_service.py         # 工单（状态机）
│
├── utils/                        # 工具模块
│   ├── ai_client.py              # 多厂商 AI 客户端
│   ├── auto_task_generator.py    # 合同自动任务生成
│   ├── cert_options.py           # 认证证书选项
│   ├── crypto.py                 # AES 密码加密/解密
│   ├── excel_export.py           # Excel 导出
│   ├── pagination.py             # 分页工具
│   ├── permission.py             # 权限系统（50+ 权限码）
│   ├── report_generator.py       # Word 报告生成
│   ├── sidebar_config.py         # 侧边栏配置
│   └── upload.py                 # 文件上传校验
│
├── templates/                    # Jinja2 模板（40+ 业务目录）
├── static/                       # 静态资源
│   ├── css/                      # 样式
│   ├── js/                       # 脚本
│   ├── img/                      # 图片
│   ├── vendor/                   # 第三方库（Bootstrap 5, Chart.js）
│   └── uploads/                  # 用户上传（运行时）
│
├── scripts/                      # 部署运维脚本
├── instance/                     # SQLite 数据库（运行时）
├── logs/                         # 日志（运行时）
├── reports/                      # Word 报告（运行时）
├── uploads/                      # 上传文件（运行时）
└── backups/                      # 备份（运行时）
```

---

## 模块说明

### 1. 首页仪表盘

- 统计卡片：根据角色展示不同指标
- 快捷入口：常用操作直达
- 用户可自定义仪表盘偏好

### 2. 客户管理

- 按地市 → 单位分类 → 客户三级树形展示
- 客户自动分级（核心客户 / 重点客户 / 普通客户）
- 客户详情页展示关联设备、巡检记录、故障工单
- 支持 Excel 批量导入导出
- 字段：名称、联系人、电话、邮箱、所属地市、地址、备注

### 3. 设备资产管理

- 按地市 → 客户 → 设备三级下钻，横向滚动浏览
- 设备字段：名称、类型、品牌、型号、IP、序列号、系统版本、规则库版本、授权截止日期、登录方式、接口（JSON 数组）、端口、用户名、密码（AES 加密）
- 固件版本库管理
- 设备配置备份管理
- 拓扑图管理
- Excel 批量导入导出

### 4. 巡检管理

- **巡检模板**：按设备类型配置检查项
- **任务模板**：按客户配置巡检频率和人员
- **巡检任务**：合同自动生成或手动创建
- **巡检记录**：填写检查结果，支持表单草稿自动保存
- **审核流程**：提交审核 → 审核通过自动生成 Word 报告
- 报告包含封面、设备明细、检查结果、巡检结论

### 5. 故障工单

- **工单状态机**：待派单 → 待受理 → 处理中 → 待审核 → 待验收 → 已关闭
- **派单调度**：按部门分配操作员
- **工单日志**：全程操作记录
- **故障类型**：可自定义分类和排序
- 支持关联知识库文章

### 6. 知识库

- 文章增删改查，支持附件上传
- 从工单一键生成知识库文章
- 按分类浏览和搜索

### 7. 备件管理

- 备件档案管理（名称、型号、规格、单位）
- 库存管理（入库/出库，FIFO 出库）
- 采购订单（自动入库）
- 销售订单（自动出库）
- 库存预警

### 8. 销售管线

- **商机** → **报价** → **合同** → **项目** 全流程跟踪
- 合同支持自动巡检频率配置（月度/季度/半年/年度）
- 合同到期自动生成巡检任务

### 9. 机柜管理

- 机房位置管理
- 机柜增删改查，自定义 U 位数量
- 设备上架可视化（占用 U 位显示）
- 支持拖拽调整设备位置

### 10. 部门管理

- 部门树形结构
- 部门负责人指派
- 关联用户归属

### 11. 用户与权限

- 4 种角色：管理员 / 操作员 / 销售 / 只读
- 50+ 细粒度权限码
- 用户关联巡检人员、部门
- 支持手机号、邮箱、认证证书等扩展字段（V13）
- 自助修改密码

### 12. 网络常用工具

- IP 地址计算（子网掩码、网络地址、广播地址）
- MAC 地址格式化
- 进制转换
- 时间戳转换
- Base64 编解码
- MTU 计算
- 带宽换算

### 13. AI 集成

- 支持 OpenAI / Anthropic / Ollama 多种后端
- 巡检结果智能分析
- 故障原因辅助诊断

### 14. 系统设置

- 设备类型管理
- 故障类型管理
- 品牌管理
- 网络类型管理
- 客户单位分类
- 区域管理
- 自定义字段
- AI 配置
- 侧边栏自定义

---

## 数据库模型

系统当前包含 46 个模型类，45 张数据表：

| 分类 | 表名 | 说明 |
|------|------|------|
| **系统** | `users` | 系统用户 |
| | `departments` | 部门 |
| | `permissions` / `user_permissions` | 权限 / 用户权限关联 |
| | `form_drafts` | 表单草稿 |
| | `user_dashboard_preferences` | 仪表盘偏好 |
| **客户** | `regions` | 区域（地市） |
| | `customers` | 客户 |
| | `customer_categories` | 客户单位分类 |
| **设备** | `devices` | 网络设备 |
| | `device_types` / `device_sub_types` | 设备类型 / 子类型 |
| | `device_firmwares` | 固件版本 |
| | `device_credentials` | 设备凭证 |
| | `device_interfaces` | 设备接口 |
| | `device_config_backups` | 配置备份 |
| | `device_collect_tasks` | 采集任务 |
| | `custom_fields` | 自定义字段 |
| | `password_history` | 密码历史 |
| | `brands` | 品牌 |
| | `network_types` | 网络类型 |
| | `topologies` | 拓扑图 |
| **巡检** | `inspection_device_templates` | 设备检查模板 |
| | `inspection_task_templates` | 任务模板 |
| | `inspection_templates` | 巡检模板（旧） |
| | `inspection_tasks` | 巡检任务 |
| | `inspections` | 巡检记录 |
| | `inspectors` | 巡检人员 |
| **工单** | `tickets` | 工单 |
| | `ticket_logs` | 工单日志 |
| | `faults` | 故障记录（旧） |
| | `fault_types` | 故障类型 |
| **知识库** | `knowledge_base` | 知识库文章 |
| | `knowledge_attachments` | 知识库附件 |
| **备件** | `spare_parts` | 备件档案 |
| | `spare_stocks` | 库存 |
| | `purchase_orders` | 采购订单 |
| | `sales_orders` | 销售订单 |
| **销售** | `opportunities` | 商机 |
| | `quotations` | 报价 |
| | `contracts` | 合同 |
| | `projects` | 项目 |
| **机柜** | `rack_locations` | 机房位置 |
| | `racks` | 机柜 |
| | `rack_installs` | 设备安装 |
| **AI** | `ai_config` | AI 配置 |

---

## 角色与权限

| 角色 | 说明 | 典型权限 |
|------|------|----------|
| `admin` | 系统管理员 | 全部权限 |
| `operator` | 运维工程师 | 设备/巡检/工单/知识库管理 |
| `sales` | 销售人员 | 客户/销售管线/备件查看 |
| `viewer` | 只读用户 | 所有模块只读 |

系统支持 50+ 细粒度权限码，可按模块和操作（查看/新增/编辑/删除）精确控制。

---

## 报告生成

使用 `python-docx` 生成 Word 文档。

### 巡检报告

- 文件名：`巡检报告_{标题}_{时间戳}.docx`
- 内容：封面 → 基本信息表 → 设备检查明细（按设备分组） → 巡检结论
- 审核通过后自动生成

### 故障报告

- 文件名：`故障报告_{标题}_{时间戳}.docx`
- 内容：封面 → 基本信息 → 故障描述 → 原因分析 → 解决方案

### 封面格式

```
客户名称 + 报告分类 + 报告       ← 宋体 26pt 居中
（空行）
江西丰功信息技术有限公司         ← 宋体 16pt 居中
中文大写日期                    ← 宋体 16pt 居中
--- 分页 ---
正文...
```

---

## 安全

### 密码加密

- 设备密码使用 `cryptography` Fernet 对称加密（AES-128-CBC + HMAC-SHA256）
- 密钥存储在 `.secret.key` 文件
- **密钥文件与数据库必须同时备份，否则所有设备密码永久不可恢复**

### 会话与 CSRF

- Flask-Login 会话管理
- Flask-WTF CSRF 保护
- 生产环境 `secure` Cookie 自动启用
- `ITSM_SECRET_KEY` 必须配置强随机密钥

### 访问控制

- `@login_required` 保护所有页面
- `@require_permission` 细粒度权限控制
- Flask-Limiter 速率限制

### 安全头

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Strict-Transport-Security`（HSTS）

---

## 备份与回滚

### 定时备份

建议加入 crontab，每天凌晨自动备份：

```bash
0 3 * * * /opt/itsm/scripts/backup.sh
```

备份内容：`instance/itsm.db` + `.secret.key` + `.env`，保留最近 30 份。

### 紧急回滚

```bash
# 查看可用备份
sudo bash /opt/itsm/scripts/rollback.sh

# 回滚到指定备份
sudo bash /opt/itsm/scripts/rollback.sh backups/itsm.db.pre_update_20260615_120000
```

---

## 常见问题

**Q：端口被占用？**
> 修改 `app.py` 最后的端口号，或修改 `scripts/itsm.service` 中 Gunicorn 的 `--bind` 参数。

**Q：数据库在哪里？**
> `instance/itsm.db`，SQLite 单文件，无需安装数据库服务。

**Q：想清空数据从头开始？**
> 删除 `instance/itsm.db` 和 `.secret.key`，重启自动重建。

**Q：批量导入 Excel 格式？**
> 在设备列表页点击「下载模板」获取标准格式。

**Q：密钥丢了怎么办？**
> `.secret.key` 丢失后所有已加密的设备密码将永久无法解密。务必定期备份 `.secret.key` 和数据库。

**Q：如何从旧版本迁移数据？**
> 将旧环境的 `instance/itsm.db` 和 `.secret.key` 复制到新环境的对应位置即可。

**Q：Ubuntu 24 部署后外网无法访问？**
> Gunicorn 绑定 `0.0.0.0:5000`，检查防火墙是否放行 5000 端口。生产环境建议配置 Nginx 反代。

---

## 技术栈

| 技术 | 用途 |
|------|------|
| Python 3.10+ | 运行环境 |
| Flask 3.1 | Web 框架 |
| Flask-SQLAlchemy | ORM |
| Flask-Login | 用户认证 |
| Flask-WTF | CSRF 保护 |
| Flask-Limiter | 速率限制 |
| SQLite | 数据库 |
| Jinja2 | 模板引擎 |
| Bootstrap 5 | 前端 UI |
| Gunicorn | 生产 WSGI 服务器 |
| systemd | 进程管理 |
| python-docx | Word 报告生成 |
| cryptography | AES 密码加密 |
| openpyxl | Excel 导入导出 |
| psutil | 系统监控 |

---

*最后更新: 2026-06-15*
