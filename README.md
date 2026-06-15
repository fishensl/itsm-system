# ITSM 简易运维管理系统

基于 Python Flask 的轻量级 IT 运维管理系统，集成了客户管理、设备密码管理、巡检管理、故障管理等功能，支持自动生成 Word 报告。

---

## 目录

- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [模块说明](#模块说明)
  - [1. 首页概览](#1-首页概览)
  - [2. 登录/认证](#2-登录认证)
  - [3. 客户管理](#3-客户管理)
  - [4. 设备管理](#4-设备管理)
  - [5. 巡检管理](#5-巡检管理)
  - [6. 故障管理](#6-故障管理)
  - [7. 巡检人员管理](#7-巡检人员管理)
  - [8. 设备类型管理](#8-设备类型管理)
  - [9. 故障类型管理](#9-故障类型管理)
  - [10. 用户管理](#10-用户管理)
- [数据库模型](#数据库模型)
- [API 接口](#api-接口)
- [报告生成](#报告生成)
- [安全](#安全)
- [安装为 Windows 服务](#安装为-windows-服务)
- [数据迁移](#数据迁移)
- [常见问题](#常见问题)

---

## 环境要求

| 依赖 | 版本 |
|------|------|
| Python | ≥ 3.10 |
| Flask | 3.1.1 |
| Flask-Login | 0.6.3 |
| Flask-SQLAlchemy | 3.1.1 |
| python-docx | 1.1.2 |
| cryptography | 44.0.3 |
| openpyxl | 3.1+ |

完整依赖见 `requirements.txt`。

---

## 快速开始

### 1. 克隆项目

```bash
git clone <repo-url> itsm-system
cd itsm-system
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
pip install openpyxl   # 批量导入/导出需要
```

### 3. 启动

```bash
python app.py
```

首次启动会自动：
- 创建 SQLite 数据库 `instance/itsm.db`
- 创建默认管理员账号 `admin / admin123`
- 预置设备类型和故障类型种子数据

### 4. 访问

浏览器打开 http://127.0.0.1:5000

---

## 项目结构

```
itsm-system/
├── app.py                    # 主应用（路由、视图）
├── models.py                 # 数据库模型
├── requirements.txt          # Python 依赖
├── .secret.key               # AES 加密密钥（⚠️ 勿泄露！）
├── install_service.ps1       # Windows 计划任务安装脚本
├── instance/
│   └── itsm.db               # SQLite 数据库文件
├── utils/
│   ├── __init__.py
│   ├── crypto.py              # AES-256 密码加密/解密
│   └── report_generator.py    # Word 报告生成器
├── templates/
│   ├── base.html              # 后台布局（侧边栏）
│   ├── login.html             # 登录页
│   ├── index.html             # 首页概览
│   ├── customers/             # 客户管理模板
│   │   ├── list.html
│   │   ├── form.html
│   │   └── detail.html
│   ├── devices/               # 设备管理模板
│   │   └── list.html          （含新增/编辑弹窗、导入导出弹窗）
│   ├── device_types/          # 设备类型
│   │   └── list.html
│   ├── inspections/           # 巡检管理
│   │   ├── list.html
│   │   ├── form.html
│   │   └── detail.html
│   ├── faults/                # 故障管理
│   │   ├── list.html
│   │   ├── form.html
│   │   └── detail.html
│   ├── fault_types/           # 故障类型
│   │   └── list.html
│   ├── inspectors/            # 巡检人员
│   │   └── list.html
│   └── users/                 # 用户管理
│       └── list.html
├── reports/                   # 生成的 Word 报告
└── static/
    └── css/
```

---

## 模块说明

### 1. 首页概览

- 统计卡片：客户总数、设备总数、巡检记录、故障记录
- 快捷入口：新增客户、管理设备、新建巡检、新建故障单
- 系统信息

### 2. 登录/认证

- Flask-Login 会话管理
- 管理员角色（admin）和操作员角色（operator）
- 用户管理需要管理员权限

### 3. 客户管理

**功能：**
- 增删改查客户
- 字段：客户名称、联系人、电话、邮箱、**所属地市**（下拉选择江西省 11 个市）、地址、备注
- 客户详情页查看关联的设备、巡检记录、故障记录
- 支持按名称/联系人/电话搜索

**路由：**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/customers` | 客户列表 |
| GET/POST | `/customers/add` | 新增客户 |
| GET/POST | `/customers/edit/<id>` | 编辑客户 |
| GET | `/customers/delete/<id>` | 删除客户 |
| GET | `/customers/<id>` | 客户详情 |

### 4. 设备管理

**功能：**
- 按地市 → 客户 → 设备三级下钻展示（默认收起设备详情）
- 设备拖拽滚动 + 横向滚轮
- 新增/编辑设备弹窗（AJAX 加载，不刷新页面）
- 批量导入（Excel）
- 批量导出（Excel，自由选择导出列）

**设备字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| 所属客户 | 下拉选择 | 必填 |
| 设备名称 | 文本 | 必填 |
| 设备类型 | 下拉选择 | 从设备类型管理 |
| 品牌 | 文本 | |
| 型号 | 文本 | |
| IP地址 | 文本 | |
| 序列号 | 文本 | |
| 系统版本 | 文本 | 如 V200R021C10 |
| 规则库版本 | 文本 | 如 IPS-20260521 |
| 授权截止日期 | 日期 | |
| 登录方式 | 下拉 | SSH/Telnet/Web/Console/API/其他 |
| 接口 | 多输入框 | 默认2个，可增删，存储为 JSON 数组 |
| 端口 | 数字 | 默认 22 |
| 登录用户名 | 文本 | |
| 登录密码 | 文本 | AES-256 加密存储 |
| 是否有过维修 | 复选框 | |
| 是否在用 | 复选框 | 默认勾选 |
| 备注 | 多行文本 | |

**密码安全：**
- 密码 AES-256 加密存储（`cryptography` Fernet）
- 修改密码自动保存旧密码到历史表
- 查看历史密码弹窗，支持复制

**路由：**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/devices` | 设备列表（地市→客户→设备） |
| POST | `/devices/add` | 新增设备 |
| POST | `/devices/edit/<id>` | 编辑设备 |
| GET | `/devices/delete/<id>` | 删除设备 |
| POST | `/devices/export` | 批量导出 Excel |
| POST | `/devices/import` | 批量导入 Excel |
| GET | `/api/devices/<id>` | 获取设备 JSON（AJAX 编辑用） |
| GET | `/api/devices/<id>/password-history` | 密码修改历史 |

### 5. 巡检管理

**功能：**
- 新建巡检：选择客户 → 自动加载该客户所有设备 → 填写检查项 → 填写结论 → 保存
- 自动生成 Word 巡检报告
- 每个设备默认检查项：运行状态、CPU使用率、内存使用率、端口状态、告警检查
- 巡检结论必填（前端 + 后端双重校验）

**报告封面格式：**
```
                    （空5行）
       客户名称巡检标题报告        ← 宋体一号 26pt 居中
            （空11行 四号14pt）
      江西丰功信息技术有限公司     ← 宋体三号 16pt 居中
      二〇二六年五月二十一日       ← 宋体三号 16pt 居中
            （分页）
一、巡检明细
  设备1
  设备2
二、巡检结论
```

**路由：**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/inspections` | 巡检列表 |
| GET/POST | `/inspections/add` | 新建巡检 |
| GET/POST | `/inspections/edit/<id>` | 编辑巡检 |
| GET | `/inspections/delete/<id>` | 删除巡检 |
| GET | `/inspections/<id>` | 巡检详情 |
| GET | `/api/customers/<id>/devices` | 获取客户设备列表（巡检表单用） |

### 6. 故障管理

**功能：**
- 增删改查故障记录
- 自动生成 Word 故障处理报告
- 报告封面格式与巡检报告一致

**路由：**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/faults` | 故障列表 |
| GET/POST | `/faults/add` | 新建故障 |
| GET/POST | `/faults/edit/<id>` | 编辑故障 |
| GET | `/faults/delete/<id>` | 删除故障 |
| GET | `/faults/<id>` | 故障详情 |

### 7. 巡检人员管理

- 增删改查巡检人员
- 关联系统用户

### 8. 设备类型管理

- 新增/删除设备类型
- 可排序

### 9. 故障类型管理

- 新增/删除故障类型
- 可排序

### 10. 用户管理

**功能：**
- 管理员权限保护
- 新增/编辑/删除用户
- 关联巡检人员
- 编辑密码支持显示/隐藏切换和复制
- 新增用户自动创建同名巡检人员

**路由：**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/users` | 用户列表 |
| POST | `/users/add` | 新增用户 |
| POST | `/users/edit/<id>` | 编辑用户 |
| GET | `/users/delete/<id>` | 删除用户 |

---

## 数据库模型

![ER 图]

| 表名 | 说明 | 主要字段 |
|------|------|---------|
| `users` | 系统用户 | username, password, role(admin/operator), inspector_id |
| `customers` | 客户 | name, city, contact_person, phone, email, address |
| `devices` | 网络设备 | customer_id, device_name, ip_address, password_encrypted, interface(JSON), login_method, os_version, rule_version, is_maintenance, is_in_use |
| `inspections` | 巡检记录 | customer_id, title, content_json(JSON), conclusion, report_file |
| `faults` | 故障记录 | customer_id, title, fault_time, fault_description, solution, result |
| `inspectors` | 巡检人员 | name, phone, email, is_active |
| `device_types` | 设备类型 | name, sort_order |
| `fault_types` | 故障类型 | name, sort_order |
| `password_history` | 密码历史 | device_id, password_encrypted, changed_by |

### 关系

- Customer 1:N Device
- Customer 1:N Inspection
- Customer 1:N Fault
- Device 1:N PasswordHistory
- User N:1 Inspector

---

## API 接口

| 方法 | 路径 | 说明 | 返回 |
|------|------|------|------|
| GET | `/api/devices/<id>` | 获取设备 JSON | `{id, device_name, password, ...}` |
| GET | `/api/devices/<id>/password-history` | 密码修改历史 | `[{password, changed_by, created_at}, ...]` |
| GET | `/api/customers/<id>/devices` | 客户设备列表 | `[{id, device_name, ip_address, ...}]` |

---

## 报告生成

使用 `python-docx` 库生成 Word 文档。

### 巡检报告

- 文件名：`巡检报告_{标题}_{时间戳}.docx`
- 内容：封面 → 基本信息表 → 设备检查明细（按设备分组，含检查项表） → 巡检结论

### 故障报告

- 文件名：`故障报告_{标题}_{时间戳}.docx`
- 内容：封面 → 基本信息表 → 故障描述 → 故障原因分析 → 解决方案

### 封面格式

```
客户名称+报告分类+报告    ← 宋体 26pt 居中
（空行）
江西丰功信息技术有限公司  ← 宋体 16pt 居中
中文大写日期             ← 宋体 16pt 居中
--- 分页 ---
正文...
```

---

## 安全

### 密码加密

- 使用 `cryptography` 库的 `Fernet` 对称加密（AES-128-CBC + HMAC-SHA256）
- 密钥存储在 `.secret.key` 文件
- 密钥文件与数据库必须同时备份，否则密码无法解密

### 会话

- Flask 签名 Cookie 会话
- `SECRET_KEY` 固定值确保重启后会话持续

### 权限

- `@login_required` 保护所有页面
- `@admin_required` 保护用户管理页面
- 操作员角色无法访问用户管理

---

## 安装为 Windows 服务

使用任务计划程序实现开机自启：

```powershell
# 管理员 PowerShell
Set-ExecutionPolicy Bypass -Scope Process
.\install_service.ps1
```

建议：复制项目后手动编辑 `install_service.ps1` 中的路径。

**管理命令：**

```powershell
schtasks /end /tn ITSM_App            # 停止
schtasks /run /tn ITSM_App            # 启动
schtasks /delete /tn ITSM_App /f      # 删除任务
```

---

## 数据迁移

### 移植到其他电脑

1. 安装 Python 3.10+
2. 复制整个 `itsm-system` 文件夹
3. 安装依赖：`pip install -r requirements.txt`
4. 启动：`python app.py`
5. 访问 http://127.0.0.1:5000

**⚠️ 必须复制以下文件：**
- `instance/itsm.db` — 所有业务数据
- `.secret.key` — 密码加密密钥（丢了密码全废）

---

## 常见问题

**Q：端口被占用？**
> 修改 `app.py` 最后一行的端口号，或结束占用进程。

**Q：数据库在哪里？**
> `instance/itsm.db`，SQLite 单文件，无需数据库服务。

**Q：想清空数据从头开始？**
> 删除 `instance/itsm.db` 和 `.secret.key`，重启自动重建。

**Q：批量导入的 Excel 格式？**
> 第一行表头，支持列：所属客户、设备名称（必填）、设备类型、品牌、型号、序列号、IP地址、端口、登录用户名、登录密码、登录方式、接口、系统版本、规则库版本、授权截止日期、备注。

**Q：接口字段怎么用？**
> 新增/编辑设备时，接口默认显示 2 个输入框，可点「添加接口」增加，右侧 × 删除。存储为 JSON 数组。

---

## 技术栈

| 技术 | 用途 |
|------|------|
| Python 3.14+ | 运行环境 |
| Flask | Web 框架 |
| Flask-SQLAlchemy | ORM / 数据库 |
| Flask-Login | 用户会话 |
| SQLite | 数据库 |
| Jinja2 | 模板引擎 |
| Bootstrap 5 | 前端 UI |
| python-docx | Word 报告生成 |
| cryptography | AES 密码加密 |
| openpyxl | Excel 导入/导出 |

---

*文档生成时间: 2026-05-22*
