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
        '--itsm-info', '--itsm-text-inverse', '--itsm-overlay', '--itsm-shadow-sm',
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
