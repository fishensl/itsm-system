"""CI gate: released Alembic revisions may not be edited, deleted, or renamed."""
from __future__ import annotations

import os
import subprocess
import sys


ZERO_SHA = '0' * 40


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ('git', *args), check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def main() -> int:
    base_ref = (os.environ.get('MIGRATION_BASE_REF') or '').strip()
    if not base_ref or base_ref == ZERO_SHA:
        print('No prior release baseline; migration immutability check skipped.')
        return 0
    if _git('cat-file', '-e', f'{base_ref}^{{commit}}').returncode != 0:
        print(f'Cannot resolve migration baseline {base_ref}; use fetch-depth: 0.', file=sys.stderr)
        return 2

    diff = _git(
        'diff', '--name-status', '--find-renames', base_ref, 'HEAD', '--',
        'migrations/versions',
    )
    if diff.returncode != 0:
        print(diff.stderr.strip(), file=sys.stderr)
        return 2

    violations = []
    additions = []
    for raw_line in diff.stdout.splitlines():
        fields = raw_line.split('\t')
        status = fields[0]
        if status == 'A' and len(fields) == 2:
            additions.append(fields[1])
            continue
        # A rename/copy still changes the released source path and is forbidden.
        violations.append(raw_line)

    if violations:
        print('Published migration files are immutable. Add a new revision instead:', file=sys.stderr)
        for item in violations:
            print(f'  {item}', file=sys.stderr)
        return 1
    print(f'Migration immutability check passed; {len(additions)} new revision(s).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
