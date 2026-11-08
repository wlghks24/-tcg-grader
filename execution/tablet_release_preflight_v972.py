#!/usr/bin/env python3
"""V972 read-only device-to-release change-scope preflight.

Never fetch, checkout, reset, copy, signal, start, install or rewrite a device
file. The existing V897 installer is authoritative about its own allowlist;
this report does not approve bypassing it, even for CI-only changes.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

SHA = re.compile(r'[0-9a-f]{40}\Z')
V897_EXACT = frozenset({
    'integrity_manifest.json',
    '.github/workflows/v887-image-reciprocity-offline.yml',
})
MAX_OUTPUT = 2_000_000


class PreflightHold(ValueError):
    """Source may not be compared safely; no action was attempted."""


def _git(repo: Path, *args: str, allow_one: bool = False) -> tuple[int, bytes]:
    """Bounded, offline git read command; only inspect in a real repo."""
    try:
        p = subprocess.run(
            ['git', '-C', str(repo), *args], check=False,
            capture_output=True, stdin=subprocess.DEVNULL, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreflightHold('GIT_READ_UNAVAILABLE') from exc
    if p.returncode not in ((0, 1) if allow_one else (0,)):
        raise PreflightHold('GIT_READ_FAILED: ' + str(args[0]))
    if len(p.stdout) > MAX_OUTPUT:
        raise PreflightHold('GIT_RESPONSE_OVERSIZED')
    return p.returncode, p.stdout


def _text(raw: bytes) -> str:
    try:
        return raw.decode('utf-8', errors='strict').strip()
    except UnicodeError as exc:
        raise PreflightHold('INVALID_GIT_OUTPUT_ENCODING') from exc


def _paths(raw: bytes) -> list[str]:
    if not raw:
        return []
    if not raw.endswith(b'\0'):
        raise PreflightHold('MALFORMED_GIT_PATH_LIST')
    items = []
    for part in raw[:-1].split(b'\0'):
        try:
            path = part.decode('utf-8', errors='strict')
        except UnicodeError as exc:
            raise PreflightHold('INVALID_GIT_PATH_ENCODING') from exc
        if not path or path.startswith('/') or '\\' in path or any(
            p in ('', '.', '..') for p in path.split('/')
        ):
            raise PreflightHold('UNSAFE_GIT_PATH')
        items.append(path)
    return items


def _changes(raw: bytes) -> list[tuple[str, str]]:
    if not raw:
        return []
    if not raw.endswith(b'\0'):
        raise PreflightHold('MALFORMED_GIT_CHANGE_LIST')
    parts = raw[:-1].split(b'\0')
    if len(parts) % 2:
        raise PreflightHold('MALFORMED_GIT_CHANGE_PAIR')
    result = []
    for i in range(0, len(parts), 2):
        status = _text(parts[i])
        path = _paths(parts[i + 1] + b'\0')[0]
        if status not in ('A', 'M', 'D', 'T'):
            raise PreflightHold('UNREVIEWED_CHANGE_TYPE')
        result.append((status, path))
    return result


def _mode(repo: Path, sha: str, path: str) -> str:
    _, raw = _git(repo, 'ls-tree', '-z', sha, '--', path)
    if not raw.endswith(b'\0') or raw.count(b'\0') != 1:
        raise PreflightHold('TARGET_TREE_PATH_UNAVAILABLE')
    meta, sep, name = raw[:-1].partition(b'\t')
    if not sep or _text(name) != path:
        raise PreflightHold('TARGET_TREE_PATH_MISMATCH')
    columns = _text(meta).split(' ')
    if len(columns) != 3 or columns[1] != 'blob':
        raise PreflightHold('UNSUPPORTED_TARGET_GIT_OBJECT')
    return columns[0]


def _v897_allowed(path: str) -> bool:
    return path.startswith('execution/') or path in V897_EXACT


def _outside_category(path: str) -> str:
    if path.startswith('.github/workflows/'):
        return 'WORKFLOW_REVIEW_REQUIRED'
    if path.startswith('.github/'):
        return 'EVIDENCE_CONTRACT_REVIEW_REQUIRED'
    if path.startswith('tests/') or path.startswith('test_') or path.startswith('sync_'):
        return 'HISTORICAL_TEST_REVIEW_REQUIRED'
    return 'UNKNOWN_SOURCE_REVIEW_REQUIRED'


def inspect(repo: Path, base: str, target: str) -> dict:
    if any(not isinstance(x, str) or not SHA.fullmatch(x) for x in (base, target)):
        raise PreflightHold('EXACT_FULL_COMMIT_SHAS_REQUIRED')
    if repo.is_symlink() or not repo.is_dir() or not (repo / '.git').is_dir():
        raise PreflightHold('REGULAR_CHECKOUT_REQUIRED')
    repo = repo.resolve(strict=True)
    _, root = _git(repo, 'rev-parse', '--show-toplevel')
    if Path(_text(root)).resolve() != repo:
        raise PreflightHold('EXACT_REPOSITORY_ROOT_REQUIRED')
    _, actual = _git(repo, 'rev-parse', 'HEAD')
    actual_sha = _text(actual)
    if actual_sha != base:
        raise PreflightHold('DEVICE_HEAD_CHANGED_NO_ACTION')
    if base == target:
        raise PreflightHold('SOURCE_TARGET_IDENTICAL_NO_ACTION')
    _, candidate = _git(repo, 'rev-parse', '--verify', target + '^{commit}')
    if _text(candidate) != target:
        raise PreflightHold('TARGET_IS_NOT_EXACT_COMMIT')
    rc, _ = _git(repo, 'merge-base', '--is-ancestor', base, target, allow_one=True)
    if rc != 0:
        raise PreflightHold('TARGET_NOT_DESCENDANT_NO_ACTION')

    _, raw = _git(repo, 'diff', '--no-renames', '--name-status', '-z', base, target)
    changes = _changes(raw)
    _, staged = _git(repo, 'diff', '--cached', '--name-only', '-z')
    _, unstaged = _git(repo, 'diff', '--name-only', '-z')
    staged_paths = _paths(staged)
    unstaged_paths = _paths(unstaged)
    _, untracked = _git(repo, 'ls-files', '--others', '--exclude-standard', '-z')
    untracked_paths = _paths(untracked)
    candidate_paths = {path for _, path in changes}
    untracked_overlaps = sorted(candidate_paths.intersection(untracked_paths))
    data_modified = sorted(
        path for path in staged_paths + unstaged_paths
        if '/' not in path and path.endswith('.json') and path != 'integrity_manifest.json'
    )
    outside = sorted(({
        'path': path,
        'category': _outside_category(path),
    } for _, path in changes if not _v897_allowed(path)),
        key=lambda x: x['path'])
    deleted = sorted(path for status, path in changes if status == 'D')
    mutable_json_changes = sorted(path for _, path in changes
                                  if path.endswith('.json') and path != 'integrity_manifest.json')
    unsafe_modes = sorted(path for status, path in changes
                          if status != 'D' and _mode(repo, target, path) not in ('100644', '100755'))
    overlaps = sorted(candidate_paths.intersection(staged_paths + unstaged_paths))
    non_data_dirty = sorted(set(
        path for path in staged_paths + unstaged_paths
        if '/' in path or not path.endswith('.json') or path == 'integrity_manifest.json'
    ))

    # READ-ONLY: no action is permitted by this report. Even a scope-clean
    # candidate still requires V897's separate owner, photo and process gates.
    blocking = []
    if outside:
        blocking.append('OUT_OF_V897_SCOPE')
    if deleted:
        blocking.append('REMOVED_SOURCE_FILE')
    if mutable_json_changes:
        blocking.append('CHANGED_JSON_EVIDENCE_OR_RUNTIME')
    if unsafe_modes:
        blocking.append('SYMLINK_OR_UNSUPPORTED_GIT_MODE')
    if staged_paths:
        blocking.append('STAGED_DEVICE_EDITS')
    if overlaps:
        blocking.append('OVERLAPPING_LOCAL_CHANGES')
    if untracked_overlaps:
        blocking.append('OVERLAPPING_UNTRACKED_FILES')
    if non_data_dirty:
        blocking.append('UNEXPECTED_LOCAL_SOURCE_DIRTY')
    if not changes:
        blocking.append('NO_CANDIDATE_CHANGES')

    return {
        'status': 'HOLD_RELEASE_INTEGRATION' if blocking else 'SCOPE_ONLY_REVIEW_PASSED',
        'base': base,
        'target': target,
        'tracked_change_count': len(changes),
        'outside_v897_scope': outside,
        'excluded_scope_count': len(outside),
        'mutated_candidate_json_paths': mutable_json_changes,
        'deleted_paths': deleted,
        'unsafe_target_tree_modes': unsafe_modes,
        'staged_path_count': len(staged_paths),
        'modified_tracked_json_count': len(set(data_modified)),
        'local_source_dirty_count': len(non_data_dirty),
        'overlap_count': len(overlaps),
        'untracked_overlap_count': len(untracked_overlaps),
        'untracked_overlap_paths': untracked_overlaps,
        'blocking': blocking,
        'installation_permitted': False,
        'device_restarted': False,
        'photos_touched': False,
        'network_used': False,
        'next_action': 'REVIEW ONLY: no install, no branch switch and no guard expansion',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--expected-base', required=True)
    parser.add_argument('--target-sha', required=True)
    args = parser.parse_args()
    try:
        result = inspect(args.repo, args.expected_base, args.target_sha)
    except PreflightHold as exc:
        result = {'status': 'HOLD_PREFLIGHT',
                  'reason': str(exc), 'installation_permitted': False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result['status'] == 'SCOPE_ONLY_REVIEW_PASSED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
