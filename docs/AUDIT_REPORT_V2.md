# ITSM 全面缺陷审查与改进方案（V2）

> 审查时间：2026-06-20 · 范围：全量代码（~1 万行 Python + 模板）
> 方法：4 路并行审查 + 关键问题逐条实测验证（标 ✅ 已实测）

---

## 一、致命缺陷：模块完全不可用（P0，立即修）

这一类是「保存即崩」或「流程走不下去」，影响日常使用。

### 1. 故障(Fault)新增/编辑 100% 崩溃 ✅已实测
- 位置：[services/fault_service.py:20-56](services/fault_service.py#L20)
- 根因：`Fault(...)` 传入了模型**不存在的列** `device_id`、`fault_level`、`description`、`reporter`、`remark`。实测 `TypeError: 'device_id' is an invalid keyword argument for Fault`。
- 模型真实列（[models.py:737](models.py#L737)）：`fault_description / fault_cause / impact_range / recovery_time / solution / result / handler`，无上述列。
- 修法：service 字段名对齐模型与表单 `templates/faults/form.html`（`fault_description`/`fault_cause`/`impact_range`/`recovery_time`），删除 `device_id`/`fault_level`/`description`/`reporter`/`remark`。`recovery_time` 是 `datetime-local`，按 `%Y-%m-%dT%H:%M` 解析。

### 2. 报价单 / 合同 / 项目 新增/编辑 100% 崩溃 ✅已实测
- 位置：[services/sales_service.py:50-171](services/sales_service.py#L50)
- 根因（实测均抛 TypeError）：
  - `Quotation` 传 `title/amount/creator/content/remark` → 模型只有 `number/items_json/total_amount/...`
  - `Contract` 传 `owner/content/remark` → 模型只有 `content_json/file_path/...`（`title/amount` 是有的）
  - `Project` 传 `description/remark` → 模型无；且模板的 `budget` 从未被写入
- 修法：三个 create/update 按 [models.py:910-969](models.py#L910) 的真实列重写；报价单去掉 `title` 必填校验、金额改用 `total_amount`；项目补 `budget=float(...)`。

### 3. 巡检记录保存丢失全部检查数据 + 报告空白 ✅已实测
- 位置：[services/inspection_service.py:36-62](services/inspection_service.py#L36)
- 根因：`create_inspection` 只读 `title/customer_id/inspector/...`，**丢弃** `task_id`、`field_values_json`、`sections_json`、`location`、`skip_reasons_json`、`content_json`；还给不存在的 `content`/`remark` 属性赋值（静默不落库）。
- 连锁：① 任务→记录联动断裂（`task_id` 永不写入）；② 审核通过后 `generate_inspection_report_v4` 从 `field_values_json`/`sections_json` 取数 → **报告内容空白**。
- 同时 [blueprints/ops.py:79-93](blueprints/ops.py#L79) GET 分支未把 `request.args.get('task_id')` 作为 `preselected_task_id` 传模板，隐藏域永远为空。
- 第 47 行 `date.today() if False else None` 引用了未导入的 `date`（死代码隐患）。
- 修法：补全字段读写 + 传 `preselected_task_id` + 清理死代码。

### 4. 工单状态机与模板/路由三处错位，流程全程卡死 ✅已实测
- 状态名不一致：service 用 `已派单/已接单/已验收`（[ticket_service.py:8-25](services/ticket_service.py#L8)），但 [templates/tickets/detail.html:59,77](templates/tickets/detail.html#L59) 只判断 `待接单/待验收`。→ **派单后「接单」按钮、审核后「验收」按钮永不出现。**
- 审核字段错位：模板提交 `action=通过/拒绝` + `comment`，路由 [ops.py:533](blueprints/ops.py#L533) 读 `approved=='1'` + `remark`。→ **审核永远走「拒绝」分支**，意见丢失。验收同理。
- 处理结果丢失：模板有 `diagnosis`/`solution`（required），但 [ops.py:518-521](blueprints/ops.py#L518) 与 `submit_ticket` 都只传 `remark`，二者不保存。
- 修法：统一状态枚举（以 service 为准，改模板 `待接单→已派单`、`待验收→已验收`、colors 字典）；路由改读 `action`/`comment`；`submit_ticket` 增 `diagnosis`/`solution` 入参。顺带回填状态机时间戳/操作人（`assigned_by/assigned_at/...` 详情页恒空）。

### 5. 工作台「我的巡检待办」永远为空 ✅已实测
- 位置：[app.py:289-291](app.py#L289)
- 根因：V13 后 `Inspector.name` 是 `@property` 不是列，`Inspector.query.filter_by(name=...)` 生成 `WHERE 0=1`，静默匹配不到。
- 修法：改为 `Inspector.query.filter_by(user_id=me.id).first()`。

### 6. 巡检 Excel 导出 500 崩溃 ✅已实测
- 位置：[blueprints/ops.py:178](blueprints/ops.py#L178) `i.customer.name`
- 根因：`Inspection` 只有 `customer_rel`，无 `customer` 属性 → AttributeError。
- 修法：改 `i.customer_rel`。

---

## 二、安全缺陷（P0/P1）

### 7. 设备明文密码越权泄露（高）
- 位置：[blueprints/asset.py:208-238](blueprints/asset.py#L208)，`/api/devices/<id>` 仅 `@login_required`，漏挂 `@require_permission('device:view')`，且返回体含 `decrypt_password(...)` 明文。
- 影响：任意登录用户（含只读 viewer）`GET /api/devices/1` 即得明文密码。
- 修法：补 `@require_permission('device:view')`；建议拆出「查看密码」细粒度权限 + 审计。

### 8. 停用账号(`is_active=False`)仍可登录（高）
- 位置：[app.py:498-512](app.py#L498) login 与 [app.py:196](app.py#L196) load_user 均不检查 `is_active`。
- 修法：login 加 `and user.is_active`；`load_user` 改 `filter_by(id=..., is_active=True)`。

### 9. RBAC 蓝图整体 CSRF 豁免 → 可被诱导提权（中）
- 位置：[blueprints/__init__.py:25](blueprints/__init__.py#L25) `csrf_ext.exempt(rbac_bp)`，而其下全是改角色/权限的写操作。
- 修法：移除整蓝图豁免（前端 fetch 已自动带 `X-CSRFToken`），如个别端点需豁免则逐路由处理。

### 10. 删除操作走 GET 链接，无 CSRF（中）
- 位置：拓扑 [app.py:601](app.py#L601)、AI 配置 [app.py:1033](app.py#L1033)、用户 [app.py:720](app.py#L720) 等仍是 `<a href>` GET 删除。
- 修法：统一改 POST + CSRF（参考已改造的 rbac 删除 commit `b7c0766`）。

### 11. 启动 seed 重建默认弱口令/回滚安全配置（中）
- `init_db` 若 admin 被改名/删除则重建 `admin/admin123`（[app.py:1283](app.py#L1283)）；`seed_all` 每次启动把系统权限/角色强制 `is_active=True`，覆盖管理员的停用（[utils/seed_permissions.py:138](utils/seed_permissions.py#L138)）。
- 修法：按「是否存在任意 admin 角色用户」判断；seed 仅在新建时设 `is_active`，不覆盖既有值。

### 12. AES 密钥文件无 0600 权限 + 解密失败静默（中/低）
- [utils/crypto.py:12-40](utils/crypto.py#L12)：写 key 未设权限（同主机他人可读），并发首启可能生成两把 key；解密失败返回 `【解密失败】` 无日志。
- 修法：`os.open(..., 0o600)`、启动期一次性生成、失败记日志。

---

## 三、数据完整性与业务逻辑（P1）

### 13. 库存账实不符（中）
- [services/spare_service.py:79-120](services/spare_service.py#L79)：采购单/销售单 `total` 从不计算（恒 0）；删除采购/销售单不冲销库存；库存可手填负数；销售扣减无行锁（TOCTOU，可超扣为负）。
- 死代码：[spare_service.py:124](services/spare_service.py#L124) 含 `quantity__gt=0`（Django 风格，SQLAlchemy 会崩）的 `if False` 分支，一旦误删 `if False` 即崩。
- 修法：`total=qty*unit_price`；删单冲销库存；库存非负校验；扣减 `with_for_update()`；删死代码。

### 14. 删除客户/设备产生孤儿数据（中）
- `Customer.devices` 是 `delete-orphan`（删客户级联删设备），但 `Ticket/Inspection/Fault` 的 `customer_id`/`related_device_id` 无 `ondelete`，SQLite 又未开 `PRAGMA foreign_keys=ON` → 悬挂外键。`delete_fault` 不清 `KnowledgeBase.related_fault_id`。
- 修法：删除前校验/置空关联，或配 `ondelete='SET NULL'` + 启用 SQLite FK pragma。

### 15. 关键唯一约束缺失（中）
- `Customer.name`（[models.py:217](models.py#L217)）、`Ticket.number`（[models.py:673](models.py#L673)）无 `unique`。导入按客户名反查会归属错乱；工单号并发可重复。
- 修法：加 `unique=True`（先清重）或服务端唯一校验。

### 16. 自动任务生成跳期（中）
- [utils/auto_task_generator.py:137](utils/auto_task_generator.py#L137)：`last_generated_date=to_date`（今天）而非最后生成周期起点，配合 `>=` 判断会漏生成后续周期；频率无法识别时静默跳过。
- 修法：记录为最后成功周期的 cursor；无法识别频率记日志。

### 17. 导入边界 / dispatch 路由错误（低）
- 设备导入 `int(row.get('port',22))` 遇 `"22.0"` 抛错丢整行；逐行 commit 性能差；`MAX_IMPORT_ROWS` 导入未用。
- [task_dispatch.py:97](blueprints/task_dispatch.py#L97) `url_for('inspection_add')` 缺蓝图前缀 → `BuildError`；[task_dispatch.py:64](blueprints/task_dispatch.py#L64) 自赋值空操作。
- 草稿 `related_id` 存(字符串)/取(int)类型不一致可致恢复失败（[drafts.py:21,54](blueprints/drafts.py#L21)）。

---

## 四、部署/运行健壮性（P2）

- **限流失效**：`Limiter` 用 `memory://`（[app.py:50](app.py#L50)），gunicorn 4 worker 下登录限流阈值实际 ×4；`ProxyFix` 未配 `x_for`。→ 换 Redis 存储 / 正确配 ProxyFix。
- **角色权限缓存跨进程不同步**：`_role_cache` 进程级（[utils/permission.py:16](utils/permission.py#L16)），多 worker 下收回权限不及时。→ 加 TTL 或共享失效。
- **角色停用 fallback 到 viewer**（[permission.py:210](utils/permission.py#L210)）= 隐性提权 → 改为返回空权限集。
- **拓扑上传双入口校验不一致**：[app.py:531](app.py#L531) 内联分支无扩展名白名单（存储型 XSS 面），而 [app.py:611](app.py#L611) 有 → 统一走带白名单的入口或删冗余分支。
- **拓扑删除不删磁盘文件** → 文件孤儿堆积、已删图仍可经 `/static` 访问。
- `ai_client` `temperature or 0.7` 吞掉显式 `0`（[utils/ai_client.py:13](utils/ai_client.py#L13)）。
- 多处 `except:` 裸捕获（`from_json`、`check_password`）→ 改 `except Exception:`。

---

## 五、建议执行顺序

| 批次 | 内容 | 理由 |
|------|------|------|
| **第 1 批** | §一 1-6（故障/销售/巡检/工单/工作台/导出） | 核心模块当前不可用，纯代码改动、不动 schema，风险低 |
| **第 2 批** | §二 7-11（密码越权、停用登录、RBAC CSRF、GET删除、seed后门） | 安全，多数为加装饰器/改判断 |
| **第 3 批** | §三 13-16（库存、孤儿数据、唯一约束、任务生成） | 涉及 schema/迁移，需配合 `init_db` 与数据清理 |
| **第 4 批** | §四（部署健壮性、缓存、上传、清理） | 多 worker / 生产加固 |

第 1 批可立即开工：全部是 service/template/路由的字段名与状态名对齐，无数据库结构变更。

---

## 六、验证方式

- 单测式快速验证：`python -c "from models import Fault; Fault(...)"` 确认构造器不再抛错（已用此法定位本轮 4 个崩溃）。
- 端到端：`python app.py` → 走「新建故障 / 新建报价单 / 执行巡检任务并审核出报告 / 工单 派单→接单→处理→审核→验收」全链路，确认每步按钮出现且数据落库。
- 安全：以 viewer 账号 `GET /api/devices/1` 应 403；停用某用户后其无法登录、已有会话失效。

---

# 附录 A：全局配置 + 数据导出/导入（服务器迁移快速恢复）

> 形态：**Web 页面一键导出/导入**（admin 权限）；范围：**全量业务数据 + 上传文件 + 加密密钥**。

## A.1 为什么需要 + 关键洞察

现有 [scripts/backup.sh](scripts/backup.sh) 只是 SQLite 文件级 tar 打包，**仅适用 SQLite、需 SSH 登录、无法跨库**。需求是迁移到新服务器后一键恢复。

**核心洞察（已验证）**：设备/AI 的密码字段在 DB 里以 **AES 密文**存储（[models.py:261,305,343,982](models.py#L261)），加解密依赖 [utils/crypto.py](utils/crypto.py) 的 `.secret.key`。因此：
- 只要导出 DB 数据（密文原样带出）**且导入端用同一把 `.secret.key`**，密码即可正常解密；
- → **导出包必须包含 `.secret.key`** → 导出/导入是**高敏感操作，必须 admin 权限 + 二次确认 + CSRF 保护**。

另一关键点：`db.metadata.sorted_tables` 已能给出**外键依赖排序**（48 张表），导入时按此序插入、清空时反序删除，无需手写表顺序。

## A.2 设计：一个新蓝图 `blueprints/backup.py`

挂到现有系统设置页 [/system](app.py#L832)，在 `templates/system/index.html` 加「数据备份/恢复」卡片（或新增 `system/backup.html`）。

### 导出 `GET /system/backup/export`（admin）
生成一个 `.zip`（流式 `send_file`），结构：
```
itsm_backup_20260620_153000.zip
├── manifest.json        # {version, app_version, db_dialect, exported_at, table_counts, sha256}
├── data.json            # 全量业务数据：{表名: [行dict, ...]}，按 sorted_tables 顺序
├── secret.key           # AES 密钥副本（解密设备密码必需）
└── files/
    ├── reports/...      # 巡检报告 Word
    ├── uploads/...      # 通用上传
    └── static_uploads/... # 拓扑图/备件图/知识库附件
```
- `data.json` 生成：遍历 `db.metadata.sorted_tables`，对每表 `SELECT *`，用 `dict(row._mapping)` 序列化；`date/datetime` 转 ISO 字符串、`bytes` 转 base64（写进 manifest 标注类型）。
- 文件用 `utils/upload.py` 已知的目录常量收集；大包用 `zipfile` 流式写临时文件再 `send_file`。

### 导入 `POST /system/backup/import`（admin + 二次确认）
- 上传 `.zip` → 校验 `manifest.json`（版本/sha256/表名集合与当前 schema 对齐，缺表/多表给警告）。
- 事务内：按 `sorted_tables` **反序 `DELETE`** 清空 → **正序 `INSERT`** 回灌（保留原始主键 id，迁移后 FK 关系不变）；ISO 字符串/base64 按 manifest 反序列化。
- 还原 `files/` 到对应目录（覆盖）；把 `secret.key` 写回 `.secret.key`（**仅当用户勾选「同时恢复密钥」**，否则保留本机密钥并提示设备密码将无法解密）。
- 全程 `db.session` 单事务，失败整体 `rollback`；成功后 `expire_all()`。
- SQLite 需在导入事务前 `PRAGMA foreign_keys=OFF`（回灌期间），完成后校验。

### 「仅配置」子选项（可选增强）
manifest 里给表分组（`CONFIG_TABLES` = roles/permissions/各模板/AI配置/侧栏偏好 vs `BUSINESS_TABLES`），导出页可勾选「仅配置」——复用同一套序列化逻辑，只是表清单子集。便于「把一台调好的配置克隆到新环境」而不带业务数据。

## A.3 复用与新增

| 复用 | 新增 |
|------|------|
| `db.metadata.sorted_tables`（FK 排序） | `blueprints/backup.py`（export/import 路由） |
| [utils/crypto.py](utils/crypto.py) 密钥路径 `KEY_FILE` | `utils/data_io.py`（序列化/反序列化核心，Web 与未来 CLI 共用） |
| `@admin_required`+`@require_permission`（[app.py](app.py)） | `system/backup.html` 卡片 + 二次确认 |
| `send_file` / `zipfile`（标准库） | manifest 校验逻辑 |

## A.4 风险与注意

- **密钥泄露面**：导出包含明文密钥，下载链接必须 admin + 不可被 `<img>` GET 触发（用 POST 或带一次性 token）。文档提示妥善保管备份包。
- **schema 漂移**：导入包来自旧版本、表结构不一致 → manifest 比对给出「缺列/多列」警告，缺失列用默认值、多余列丢弃，不硬失败。
- **大包**：reports 23M + uploads 12M，zip 可达 ~50M；用流式避免内存峰值，`MAX_CONTENT_LENGTH` 当前 100M 够用（上传导入时注意该上限）。
- 导入会**清空并覆盖现有数据**，必须二次确认 + 导入前自动 `backup.sh` 兜底。

---

# 附录 B：迁移 PostgreSQL 可行性评估

> 仅评估，不实施。结论：**技术可行、价值明确，但有 1 个必须先解决的硬障碍。**

## B.1 可行性：好的基础

- 全程用 SQLAlchemy ORM + `ITSM_DATABASE_URI` 配置项（[config.py:30](config.py#L30)）**已支持切换**，换 `postgresql://...` 即可，业务代码基本不用改。
- 无原生 SQL 拼接的业务查询（查询都走 ORM），方言耦合低。

## B.2 硬障碍（必须先改）

**自研的 schema 自动迁移绑死 SQLite**：[utils/seed_permissions.py:40-88](utils/seed_permissions.py#L40) 用 `PRAGMA table_info` / `PRAGMA index_list` 做「启动时自动 ADD COLUMN」。PG 没有 PRAGMA，这套机制在 PG 上直接失效 → **schema 演进会断**。

- 解决方向：引入 **Alembic（flask-migrate）** 替代手写 PRAGMA 迁移，这是迁移 PG 的前置条件，也顺带解决「`init_db` 每次启动 seed」的混乱（见正文 §二 11）。

## B.3 次要适配点

| 项 | SQLite 现状 | PG 注意 |
|----|------------|---------|
| JSON 字段（25 个 `_json`） | `Text` 存 JSON 字符串 | 可保留 Text，或升级为 PG 原生 `JSONB`（可索引、可查询，长期优势大） |
| `Device.interface` | `String(128)` 存 JSON（正文 L5） | PG 严格校验长度，**会截断/报错**，迁移前必须改 `Text` |
| 布尔/日期 | SQLite 宽松 | PG 严格类型，`int(float())` 容错（正文 M4）等需先修 |
| 自增主键 | rowid | 序列(sequence)，全量回灌保留 id 后需 `setval` 重置序列，否则新插入主键冲突 |
| `func.sum` 等聚合 | OK | 行为一致，无需改 |

## B.4 迁移 PG 的优势

1. **并发写**：SQLite 写时全库锁，多 worker（当前 gunicorn 4 worker）高并发写会 `database is locked`。PG 行级锁，根治。也使正文 §三 13 的「库存扣减加 `with_for_update()` 行锁」成为可能（SQLite 不支持）。
2. **数据完整性**：PG 默认强制外键约束，直接消灭正文 §三 14 的「孤儿数据」隐患（SQLite 默认 FK off）。
3. **真正的备份/复制**：`pg_dump` / 流复制 / PITR，比文件级 tar 可靠得多；附录 A 的导出导入仍可作为「跨环境克隆」的应用层补充。
4. **扩展性**：全文检索、`JSONB` 索引、并发分析查询，为知识库检索 / 报表打基础。

## B.5 推荐路径（分阶段，低风险）

1. **先修正文致命 bug**（第 1-3 批），尤其 schema 相关的唯一约束/类型问题，避免带病迁移。
2. **引入 Alembic**：把现有 schema 固化为初始 migration，废弃 PRAGMA 自动迁移。
3. **开发环境起 PG**：`ITSM_DATABASE_URI=postgresql://...`，跑 Alembic 建表，用附录 A 的导出/导入把 SQLite 数据灌进 PG（天然的跨库迁移工具！），验证全功能。
4. **小流量验证 → 切换**：reports/uploads 等文件不在 DB，不受影响。
5. `requirements.txt` 加 `psycopg2-binary`、`flask-migrate`。

**结论**：建议作为正文修复之后的中期目标。附录 A 的导出/导入恰好能复用为 SQLite→PG 的迁移搬运工具，两个需求天然协同。
