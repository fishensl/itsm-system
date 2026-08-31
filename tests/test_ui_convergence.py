from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _view_source(relative_path: str) -> str:
    return (ROOT / 'frontend' / 'src' / 'views' / relative_path).read_text(encoding='utf-8')


def test_audited_top_level_lists_use_data_table():
    pages = (
        'contractTasks/index.vue',
        'firmwares/index.vue',
        'rack/index.vue',
        'taskTemplates/index.vue',
        'topology/index.vue',
        'system/exportReviews.vue',
        'system/notifyRules.vue',
        'devices/DictTable.vue',
        'system/ReviewChecklist.vue',
    )

    missing = [page for page in pages if '<DataTable' not in _view_source(page)]
    assert not missing, f'审计清单中的顶层列表尚未迁入 DataTable：{missing}'


def test_packet_analyzer_keeps_dense_desktop_table_with_mobile_cards():
    source = _view_source('tools/PacketAnalyzer.vue')

    assert '<el-table v-else' in source
    assert source.count('v-if="isMobile" class="packet-cards"') == 2


def test_theme_defines_semantic_tokens_for_light_and_dark_modes():
    source = (ROOT / 'frontend' / 'src' / 'styles' / 'index.css').read_text(encoding='utf-8')
    required = (
        '--itsm-primary', '--itsm-success', '--itsm-warning', '--itsm-danger',
        '--itsm-info', '--itsm-scheduled', '--itsm-text-inverse', '--itsm-overlay',
        '--itsm-shadow-sm',
    )
    root_block, dark_block = source.split('html.dark', maxsplit=1)
    for token in required:
        assert token in root_block, f'浅色主题缺少 {token}'
        assert token in dark_block, f'深色主题缺少 {token}'
    assert '--el-color-primary: var(--itsm-primary)' in source
    assert '--el-bg-color: var(--itsm-card-bg)' in source


def test_dialogs_have_mobile_tablet_and_desktop_viewport_guards():
    source = (ROOT / 'frontend' / 'src' / 'styles' / 'index.css').read_text(encoding='utf-8')
    assert '@media (max-width: 768px)' in source
    assert '@media (min-width: 769px) and (max-width: 1023px)' in source
    assert 'max-width: calc(100vw - 32px)' in source
    assert 'max-height: calc(100dvh - 168px)' in source
    assert '.el-dialog__footer .el-button' in source


def test_theme_aware_vue_views_do_not_embed_semantic_hex_colors():
    """机柜颜色是用户数据，除此之外 Vue 视图的业务色必须引用语义 token。"""
    color_literal = re.compile(r'#[0-9a-fA-F]{3,8}\b|rgba?\(')
    offenders = []
    for path in (ROOT / 'frontend' / 'src').rglob('*.vue'):
        relative = path.relative_to(ROOT).as_posix()
        for match in color_literal.finditer(path.read_text(encoding='utf-8')):
            if relative == 'frontend/src/views/rack/index.vue' and match.group().lower() == '#0d6efd':
                continue
            offenders.append(f'{relative}:{match.group()}')
    assert not offenders, f'Vue 视图仍有硬编码语义色：{offenders}'


def test_layout_has_only_one_page_title_source():
    """页面标题由内容页渲染一次；顶栏仅保留全局工具，避免全站双标题。"""
    source = (ROOT / 'frontend' / 'src' / 'layouts' / 'MainLayout.vue').read_text(
        encoding='utf-8')
    assert 'topbar-title' not in source
    assert '{{ route.meta.title }}' not in source


def test_task_schedule_kpis_stay_in_one_row():
    """10 个任务 KPI 固定为单行；窄屏通过横向滚动保持指标不换行。"""
    source = _view_source('taskSchedule/index.vue')
    assert 'grid-template-columns: repeat(10, minmax(100px, 1fr))' in source
    assert 'overflow-x: auto' in source
    assert '<el-row v-if="data"' not in source


def test_task_schedule_separates_contract_deadline_and_execution_timing():
    """合同时效、任务期限、实施时效分开，日期范围不溢出卡片。"""
    source = _view_source('taskSchedule/index.vue')
    assert 'v-model="inlineScheduleRange" type="daterange"' not in source
    assert source.count('v-model="inlineScheduleRange[0]" type="date"') == 2
    assert source.count('v-model="inlineScheduleRange[1]" type="date"') == 2
    assert source.count('v-model="inlineContractRange[0]" type="date"') == 2
    assert source.count('v-model="inlineContractRange[1]" type="date"') == 2
    assert source.count('@change="inlineContractChanged = true"') == 4
    assert 'patch.planned_start = plannedStart' in source
    assert 'patch.planned_end = plannedEnd' in source
    assert source.count('任务期限 {{ taskDeadlineText(t) }}') == 2
    assert source.count('class="task-period-label">实施时效') == 2
    assert source.count('开始：{{ t.actual_start }}') == 2
    assert 'grid-template-columns: minmax(0, 1fr)' in source
    assert source.count('class="inline-schedule-date" style="width: 95px"') == 8
    assert 'flex: 0 0 95px' in source
    assert 'width: 95px !important' in source
    assert source.count(":class=\"{ 'with-check': bulkMode }\"") == 4
    assert 'margin-top: 3px; padding-left: 15px' in source
    assert 'margin-top: 2px; padding-left: 15px' in source
    assert '.task-schedule-summary.with-check { padding-left: 35px; }' in source
    # 最窄 310px 看板列中，任务期限标签独占一行，日期区仍有 250px。
    minimum_date_area = 310 - 2 - 20 - 2 - 20 - 16
    date_controls_width = 95 * 2 + 14 + 6 * 2
    assert date_controls_width <= minimum_date_area
    inline_schedule_style = re.search(r'\.inline-schedule-dates\s*\{([^}]+)\}', source)
    assert inline_schedule_style is not None
    assert 'overflow' not in inline_schedule_style.group(1)
    assert ':shortcuts="rangeDateShortcuts"' not in source
    assert '<el-form-item label="任务期限">' in source
    assert 'v-model="exportStatuses" multiple' in source
    assert ':shortcuts="exportDateShortcuts"' in source
    assert "{ text: '本周', value: currentWeekDates }" in source
    assert "{ text: '本月', value: currentMonthDates }" in source
    assert 'params.scheduled_from = exportDateRange.value[0]' in source
    assert 'params.scheduled_to = exportDateRange.value[1]' in source
    assert source.count(':shortcuts="dateShortcuts"') == 12
    assert "planned_start: today, planned_end: today" in source
    assert "scheduled_start: today, scheduled_end: today" in source
    assert source.count('popper-class="task-date-today-popper"') == 13
    assert ':global(.task-date-today-popper .el-picker-panel__sidebar)' in source
    assert 'inset: 8px 72px auto auto' in source
    assert source.count('grid-template-columns: minmax(0, 1fr)') >= 2
    assert ':deep(.inline-schedule-date .el-input__prefix) { display: none; }' in source


def test_device_edit_uses_shared_network_types_and_editable_rack_fields():
    source = _view_source('devices/index.vue')
    assert 'v-for="name in networkTypes"' in source
    assert '<el-option label="内网" value="内网"' not in source
    assert 'v-for="option in rackSelectOptions"' in source
    assert ':label="option.name" :value="option.value"' in source
    assert 'option.detail' not in source
    assert "presetRackNames = ['1', '2', '3', '4']" in source
    assert "localeCompare(right.name, 'zh-CN', { numeric: true })" in source
    assert '<el-option label="自定义…" value="__custom__"' in source
    assert "fieldLabel('device', 'rack_slot', '起始U位', 'form')" in source
    assert source.count('controls-position="right" class="w-full"') >= 2
    assert ':disabled="!form.rack_id"' not in source
    assert 'v-if="form.id && !changePasswordEnabled"' in source
    assert 'if (form.id && !changePasswordEnabled.value) delete payload.password' in source
    assert "{ key: 'ip_port', label: 'IP / 端口'" in source
    assert 'return ip && port ? `${ip}:${port}`' in source
    assert "if (key === 'ip_address') result.push('ip_port')" in source
    assert "else if (key !== 'port') result.push(key)" in source


def test_all_batch_import_pages_expose_template_and_import_actions():
    """所有已有批量导入后端的表格页同时提供显式模板与导入入口。"""
    expected = {
        'devices/index.vue': ("downloadImportTemplate('device')", 'importVisible = true'),
        'customers/index.vue': ("downloadImportTemplate('customer')", 'importVisible = true'),
        'inspections/index.vue': ("downloadImportTemplate('inspection')", ':import-request="importInspections"'),
        'faults/index.vue': ("downloadImportTemplate('fault')", ':import-request="importFaults"'),
        'spare/index.vue': (
            "downloadImportTemplate('spare')",
            "downloadImportTemplate('stock')",
            ':import-request="importSpareParts"',
            ':import-request="importSpareStocks"',
        ),
        'taskSchedule/index.vue': ('>导入模板</el-button>', '>批量导入</el-button>'),
    }
    for page, markers in expected.items():
        source = _view_source(page)
        for marker in markers:
            assert marker in source, f'{page} 缺少入口：{marker}'


def test_wecom_notification_channel_uses_group_webhook():
    source = _view_source('system/notifyChannels.vue')
    assert '使用企业微信群机器人 Webhook' in source
    assert "ch.channel_type === 'wecom' ? 'webhook_url'" in source
    assert 'ch.config.corpid' not in source
    assert '<el-form-item label="企业 ID">' not in source
    assert '<el-form-item label="应用 AgentId">' not in source
    assert '应用 Secret' not in source
    assert 'ch.channel_type !== \'wecom\'' in source
    assert '测试消息直接发送到该 Webhook 对应的企业微信群' in source
    users_source = _view_source('system/users.vue')
    assert 'wecom_account' not in users_source
    assert '企业微信账号' not in users_source
