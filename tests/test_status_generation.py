from pathlib import Path
import subprocess
import sys

from utils.constants import (
    QUOTATION_STATUSES,
    QUOTATION_TRANSITIONS,
    STATUS_CATALOG,
    TASK_STATUSES,
    TASK_STATUS_TAG,
    TASK_TRANSITIONS,
    TICKET_STATUSES,
    TICKET_TRANSITIONS,
)


ROOT = Path(__file__).resolve().parents[1]


def test_status_catalog_tags_cover_every_value():
    for name, definition in STATUS_CATALOG.items():
        values = set(definition['values'].values())
        assert values == set(definition['tags']), f'{name} status/tag keys drifted'


def test_task_board_uses_canonical_complete_status_map():
    assert set(TASK_STATUS_TAG) == set(TASK_STATUSES)


def test_transition_tables_only_reference_canonical_statuses():
    for statuses, transitions in (
        (TICKET_STATUSES, TICKET_TRANSITIONS),
        (TASK_STATUSES, TASK_TRANSITIONS),
        (QUOTATION_STATUSES, QUOTATION_TRANSITIONS),
    ):
        assert set(transitions) == set(statuses)
        assert all(set(targets) <= set(statuses) for targets in transitions.values())


def test_frontend_status_generated_file_is_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'generate_frontend_status.py'), '--check'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
