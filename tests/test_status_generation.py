from pathlib import Path
import subprocess
import sys

from utils.constants import STATUS_CATALOG, TASK_STATUSES, TASK_STATUS_TAG


ROOT = Path(__file__).resolve().parents[1]


def test_status_catalog_tags_cover_every_value():
    for name, definition in STATUS_CATALOG.items():
        values = set(definition['values'].values())
        assert values == set(definition['tags']), f'{name} status/tag keys drifted'


def test_task_board_uses_canonical_complete_status_map():
    assert set(TASK_STATUS_TAG) == set(TASK_STATUSES)


def test_frontend_status_generated_file_is_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'generate_frontend_status.py'), '--check'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
