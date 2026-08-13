from pathlib import Path


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
