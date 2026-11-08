#!/usr/bin/env python3
"""V971 read-only Lenovo/Termux updater hold diagnosis.

The frozen legacy scheduler is intentionally NOT modified. This utility never
fetches Git, switches branches, updates refs, touches photos, or writes files.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


STATUS_RE = re.compile(r'^RESULT=([A-Z][A-Z0-9_]*)$')


def _git(repo: Path, *args: str, optional: bool = False) -> str | None:
    """Run one fixed, bounded Git inspection; optional permits missing refs."""
    try:
        result = subprocess.run(
            ['git', '-C', str(repo), *args], capture_output=True, text=True,
            timeout=12, check=False, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Git 읽기 전용 점검 실패') from exc
    if result.returncode:
        if optional and result.returncode == 1:
            return None
        raise RuntimeError('Git 검사 실패: ' + ' '.join(args))
    return result.stdout.strip()


def _diff(repo: Path, *args: str) -> bool:
    """0 means unchanged, 1 means changed; other errors must fail closed."""
    try:
        r = subprocess.run(
            ['git', '-C', str(repo), 'diff', *args], capture_output=True,
            text=True, timeout=12, stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Git 변경 검사 실패') from exc
    if r.returncode not in (0, 1):
        raise RuntimeError('Git 변경 검사 실패: ' + ' '.join(args))
    return r.returncode == 1


def _reported_status(path: Path | None) -> str:
    if path is None or path.is_symlink() or not path.is_file():
        return 'UNAVAILABLE'
    try:
        if path.stat().st_size > 65536:
            return 'UNAVAILABLE'
        raw = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        return 'UNAVAILABLE'
    for line in raw.splitlines():
        match = STATUS_RE.fullmatch(line)
        if match:
            return match.group(1)
    return 'UNAVAILABLE'


def diagnose(repo: Path, status_file: Path | None = None) -> dict:
    """Classify local safety conditions, not whether deployment is authorized."""
    repo = repo.expanduser().resolve()
    if not repo.is_dir():
        raise RuntimeError('Git 저장소 폴더가 없습니다')
    root = _git(repo, 'rev-parse', '--show-toplevel')
    if Path(root).resolve() != repo:
        raise RuntimeError('Git 저장소의 최상위 폴더를 지정하세요')

    head = _git(repo, 'rev-parse', 'HEAD')
    # Git show-ref --verify --quiet returns 1 when the ref is missing.
    # show-ref --verify --hash instead returns 128 on Git 2.x. Probe
    # existence first, then read only existing refs with rev-parse.
    def optional_ref(name: str) -> str | None:
        exists = _git(repo, 'show-ref', '--verify', '--quiet', name,
                      optional=True)
        if exists is None:
            return None
        return _git(repo, 'rev-parse', '--verify', name)

    local_main = optional_ref('refs/heads/main')
    origin_main = optional_ref('refs/remotes/origin/main')
    branch = _git(repo, 'symbolic-ref', '--quiet', '--short', 'HEAD',
                  optional=True)
    staged = _diff(repo, '--cached', '--quiet', '--ignore-submodules', '--')
    modified = _diff(repo, '--quiet', '--ignore-submodules', '--')

    ahead = None
    behind = None
    if local_main:
        ahead = int(_git(repo, 'rev-list', '--count', 'refs/heads/main..HEAD'))
        behind = int(_git(repo, 'rev-list', '--count', 'HEAD..refs/heads/main'))

    if branch is None:
        classification = 'DETACHED_HEAD_HOLD'
    elif branch != 'main':
        classification = 'NON_MAIN_BRANCH_HOLD'
    elif staged:
        classification = 'STAGED_CHANGES_HOLD'
    elif modified:
        classification = 'MAIN_DIRTY_REVIEW_REQUIRED'
    else:
        classification = 'MAIN_CLEAN_REVIEW_REQUIRED'

    reported = _reported_status(status_file)
    return {
        'classification': classification,
        'branch': branch if branch is not None else '(detached)',
        'head': head,
        'local_main': local_main,
        'origin_main_cached': origin_main,
        'ahead_of_local_main': ahead,
        'behind_local_main': behind,
        'tracked_modified': modified,
        'staged_changes': staged,
        'scheduled_reported_status': reported,
        'scheduled_status_mismatch': (
            reported == 'LOCAL_CHANGES_HOLD' and branch is None),
        'installation_permitted': False,
        'next_action': 'HOLD: do not reset/switch/merge on device',
        'source': 'LOCAL_READ_ONLY_NO_NETWORK',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--status-file', type=Path, default=(
        Path.home() / '.local/state/tcg-grader/scheduled-update/status.env'))
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        report = diagnose(args.repo, args.status_file)
    except (RuntimeError, ValueError) as exc:
        print('HOLD: ' + str(exc))
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        for key, value in report.items():
            print(key.upper() + '=' + str(value))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
