# 备份页紧凑化 + 导入前自动备份

## 一、界面紧凑化（backup.vue 重写为三卡并排）

**布局**（按已确认决策「三功能并排一卡三列」）：
- 页头：标题 + 自动备份状态 tag（保留）
- **数据概览**：8 统计卡保留（统一风格，非"乱"来源）
- **操作区改单行三卡**（`el-row :md="8"`，窄屏 xs=24 自动堆叠），每卡内表单紧凑化：
  - `label-width="72px" label-position="left"`（96→72，对齐 taskSchedule 最密模式）
  - 控件 `size="small"`；字段用 `el-row` 行内化（如调度配置的 时刻/保留份数 同列）
  - **按钮并入字段行**（不再单独占一整行空 label）
  - 冗余 `.field-hint` 合并为单行 tooltip/简短文案
  - 卡 `height:100%` 对齐
- **三卡内容**：
  1. 导出备份：范围（radio 行内）+ 加密密码 + [导出]
  2. 导入恢复（红色标题）：备份文件 + 还原密钥 ☐ + 加密密码 + 二次确认 + [执行导入]（warn 单行）
  3. 调度配置：每日备份 switch + 备份时刻 + 保留份数（三字段行内）+ [保存配置]
- **信息区折叠**（已确认）：页面底部 `el-collapse` 一项「备份产物与恢复（文件命名 / restore / rollback 命令）」默认收起；内含两列 `el-descriptions :column="2"` + 密钥备份警示。常驻页面高度大幅缩短。

## 二、导入前自动备份（服务端自动落盘，已确认）

**后端 `api_backup_import`（blueprints/vue_api_sys.py:666-715）**：
- 在 `f.save(tmp_path)` 之后、`perform_import` 之前插入：
  - `build_export_zip(config_only=False)` 生成临时全量 zip（含密钥+文件）
  - `shutil.move` 落盘 `backups/pre_import_<ts>.zip`（`ts=utcnow %Y%m%d_%H%M%S`，与 backup.sh 命名风格一致）
  - 目录取 `current_app.config.get('BACKUP_DIR') or os.path.join(current_app.root_path,'backups')`（**BACKUP_DIR 可配置**，供测试隔离、避免污染工作区 backups/）
  - 写 `audit_log('backup:pre_import', ...)`；备份失败仅 warning 不阻断导入（兜底不失效）
- **消息携带**：
  - 成功：`导入成功：…。导入前已自动备份当前数据到 backups/pre_import_<ts>.zip`
  - 失败：`导入失败：<e>（已自动备份当前数据到 backups/pre_import_<ts>.zip，可据此恢复）`

**前端**：
- `frontend/src/api/system.ts` `importBackup` 返回类型加 `pre_import_file?: string`
- `backup.vue onImport()`：成功 toast 追加"导入前已自动备份：<文件名>"；失败 toast 亦提示备份文件名

## 三、测试

`tests/test_vue_api_backup.py` 新增 `test_import_creates_pre_backup`：
- `create_app` 传 `BACKUP_DIR=str(tmp_path)`（走 test_config 覆盖，不污染项目 backups/）
- 先造数据（Customer）→ 上传一份备份包 → 断言响应 `message` 含 `pre_import_` 且 `tmp_path` 目录下存在 `pre_import_*.zip`
- 已有导入用例不受影响（断言不变）

## 四、验证与部署
- 后端：`pytest tests/test_vue_api_backup.py`（嵌入式 PG）
- 前端：`npx vue-tsc --noEmit` + `npm run build`
- 部署：含后端改动（导入端点）→ 出双包 → `update.sh` 停机发布（约 5 分钟）→ 验证导入前备份提示

## 范围
- `blueprints/vue_api_sys.py`（导入前备份逻辑）
- `frontend/src/api/system.ts`（类型）
- `frontend/src/views/system/backup.vue`（重写布局）
- `tests/test_vue_api_backup.py`（新用例）
- 不改：数据概览统计卡、备份配置/导出/下载端点、scripts/