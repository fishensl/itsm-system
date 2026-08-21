# -*- coding: utf-8 -*-
"""发布脚本的可恢复失败注入测试。"""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


def _find_bash():
    found = shutil.which('bash')
    if found:
        return found
    for candidate in (
        Path(r'C:\Program Files\Git\bin\bash.exe'),
        Path(r'C:\Program Files\Git\usr\bin\bash.exe'),
    ):
        if candidate.is_file():
            return str(candidate)
    return None


BASH = _find_bash()
LIB = Path(__file__).resolve().parents[1] / 'scripts' / 'lib-release.sh'
ROOT = Path(__file__).resolve().parents[1]


def _run_restore(current, previous, failed, *, inject=False):
    if not BASH:
        pytest.skip('当前环境无 bash')
    env = dict(os.environ)
    if inject:
        env['ITSM_RELEASE_FAIL_AFTER_ARCHIVE'] = '1'
    script = (
        'set -euo pipefail; source "$1"; '
        'restore_previous_frontend "$2" "$3" "$4"'
    )
    return subprocess.run(
        [BASH, '-c', script, 'bash', LIB.as_posix(), current.as_posix(),
         previous.as_posix(), failed.as_posix()],
        env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False,
    )


def _write_frontend(path, marker):
    path.mkdir()
    (path / 'index.html').write_text(marker, encoding='utf-8')


def _run_wait_for_readyz(succeed_on, attempts=4):
    if not BASH:
        pytest.skip('当前环境无 bash')
    env = dict(os.environ)
    script = (
        'set -uo pipefail; source "$1"; target="$2"; attempts="$3"; count=0; '
        'curl() { count=$((count + 1)); [ "$count" -ge "$target" ]; }; '
        'wait_for_readyz test "$attempts" 0; rc=$?; '
        'printf "CALLS=%s\\n" "$count"; exit "$rc"'
    )
    result = subprocess.run(
        [BASH, '-c', script, 'bash', LIB.as_posix(), str(succeed_on), str(attempts)],
        env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False,
    )
    calls = int(result.stdout.rsplit('CALLS=', 1)[1].strip())
    return result, calls


def test_restore_previous_frontend_success(tmp_path):
    current = tmp_path / 'app'
    previous = tmp_path / 'app.previous'
    failed = tmp_path / 'app.failed'
    _write_frontend(current, 'new')
    _write_frontend(previous, 'old')

    result = _run_restore(current, previous, failed)

    assert result.returncode == 0, result.stderr
    assert (current / 'index.html').read_text(encoding='utf-8') == 'old'
    assert (failed / 'index.html').read_text(encoding='utf-8') == 'new'
    assert not previous.exists()


def test_restore_rejects_missing_previous_without_touching_current(tmp_path):
    current = tmp_path / 'app'
    previous = tmp_path / 'app.previous'
    failed = tmp_path / 'app.failed'
    _write_frontend(current, 'new')

    result = _run_restore(current, previous, failed)

    assert result.returncode != 0
    assert (current / 'index.html').read_text(encoding='utf-8') == 'new'
    assert not failed.exists()


def test_restore_failure_injection_rolls_current_back(tmp_path):
    current = tmp_path / 'app'
    previous = tmp_path / 'app.previous'
    failed = tmp_path / 'app.failed'
    _write_frontend(current, 'new')
    _write_frontend(previous, 'old')

    result = _run_restore(current, previous, failed, inject=True)

    assert result.returncode != 0
    assert (current / 'index.html').read_text(encoding='utf-8') == 'new'
    assert (previous / 'index.html').read_text(encoding='utf-8') == 'old'
    assert not failed.exists()


def test_wait_for_readyz_retries_until_service_is_ready():
    result, calls = _run_wait_for_readyz(succeed_on=3, attempts=5)
    assert result.returncode == 0, result.stderr
    assert calls == 3


def test_wait_for_readyz_fails_after_bounded_attempts():
    result, calls = _run_wait_for_readyz(succeed_on=99, attempts=2)
    assert result.returncode != 0
    assert calls == 2


def test_release_script_requires_clean_matching_source():
    script = (ROOT / 'scripts' / 'make-release.sh').read_text(encoding='utf-8')
    assert 'git diff --quiet' in script
    assert 'git ls-files --others --exclude-standard' in script
    assert 'RELEASE_COMMIT=$(git rev-parse HEAD)' in script
    assert 'MASTER_COMMIT=$(git rev-parse master)' in script
    assert 'PY="${PYTHON:-}"' in script
    assert '请设置 PYTHON=/path/to/python' in script


def test_offline_update_does_not_require_zip_or_pypi():
    script = (ROOT / 'scripts' / 'update.sh').read_text(encoding='utf-8')
    assert 'dpkg -s unzip zip' not in script
    assert 'pip" install --no-index' in script
    assert 'git status --porcelain --untracked-files=no' in script
    assert "git ls-files '.secret.key.bak.*'" in script
    assert 'backups/key-archive' in script


def test_backup_timer_units_are_installed_and_hardened():
    installer = (ROOT / 'scripts' / 'lib-install.sh').read_text(encoding='utf-8')
    service = (ROOT / 'scripts' / 'itsm-backup.service').read_text(encoding='utf-8')
    timer = (ROOT / 'scripts' / 'itsm-backup.timer').read_text(encoding='utf-8')
    assert 'systemctl enable --now itsm-backup.timer' in installer
    assert 'systemctl disable --now itsm-backup-failsafe.timer' in installer
    assert 'User=itsm' in service
    assert 'UMask=0077' in service
    assert 'run_scheduled_backup.py' in service
    assert 'OnCalendar=*:0/5' in timer
    assert 'Persistent=true' in timer
    web_service = (ROOT / 'scripts' / 'itsm.service').read_text(encoding='utf-8')
    assert 'UMask=0077' in web_service
