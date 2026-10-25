#!/usr/bin/env python3
"""Fail-closed, source-only PR814 successor preflight; never a merge/device approval.

Git history, frozen candidate bytes and current worktree bytes must ALL agree.
Historical V645/V653 immutable proofs are not changed by this script.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF_PATH = '.github/tablet-autonomy/pr814_source_preflight_v665.json'
BASE = 'c5bf5608b87b19d72e5b9f73a3aa0a466230f397'
CANDIDATE = '48c3481915342e59bca91a306be1778cf24d9352'
REVIEWED = {
    'tcg_reliability/china_official_catalog_v571.py': {
        'before': '34457a1d6baeabb9d33dc6b5084f5d96786e427da331f82b15ce441985aef192',
        'after': '5321afb65d990ccdab8ba300fa3ea3181a2e32742a2b78f9dc66e8ef8a5f3cd2',
    },
    'update_promo_events.py': {
        'before': '02959b8c5868ea6c6f188b8a8ac13614d17633d4f6e858bc46d0e5629558a024',
        'after': '86c6fca020d22d92b176d26199fd4543bdc1294a6e851805caf199d95fc6e843',
    },
}
CHANGED = [
    '.github/workflows/china-catalog-regression.yml',
    'docs/tablet/CHINA_COVERAGE_RECOVERY_ACCEPTANCE_20261025.md',
    'docs/tablet/RECORDING_AUDIT_20261025.md',
    'integrity_manifest.json',
    'tcg_reliability/china_multi_tcg_adapter_20261025.py',
    'tcg_reliability/china_official_catalog_v571.py',
    'tcg_reliability/test_china_catalog_retry_20261025.py',
    'tcg_reliability/test_china_multi_tcg_adapter_20261025.py',
    'tcg_reliability/test_event_title_date_safety_20261025.py',
    'tcg_reliability/test_job_neural_postflight_20261025.py',
    'tcg_reliability/test_neural_label_safety_20261025.py',
    'update_promo_events.py',
]
EXPECTED = {
    'schema': 'tcg-source-preflight/v665',
    'base_commit': BASE,
    'candidate_commit': CANDIDATE,
    'changed_paths': CHANGED,
    'reviewed_sha256': REVIEWED,
    'physical_tablet_verified': False,
    'deployment_allowed': False,
    'legacy_successor_ci_repaired': False,
}

class Hold(Exception):
    pass


def _unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise Hold('duplicate_json_key')
        out[k] = v
    return out


def load(root: Path):
    p = root / PROOF_PATH
    if p.is_symlink() or not p.is_file() or p.stat().st_size > 8192:
        raise Hold('invalid_contract_path')
    try:
        result = json.loads(p.read_text(encoding='utf-8'), object_pairs_hook=_unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(Hold('nonfinite_json')))
    except (ValueError, UnicodeError, RecursionError) as e:
        raise Hold('invalid_contract_json') from e
    if result != EXPECTED:
        raise Hold('contract_not_pinned')
    return result


def git(root: Path, *args: str):
    try:
        return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True,
                              timeout=20).stdout
    except (OSError, subprocess.SubprocessError) as e:
        raise Hold('git_proof_failure:' + args[0]) from e


def sha256(data: bytes):
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=32)
def _immutable_scope(root_text: str, base: str, candidate: str, changed: tuple[str, ...]):
    root=Path(root_text)
    git(root, 'merge-base', '--is-ancestor', base, candidate)
    actual=git(root, 'diff', '--name-only', '--no-renames', base, candidate).decode('utf-8').splitlines()
    if sorted(actual)!=sorted(changed) or len(actual)!=len(changed):
        raise Hold('changed_scope_not_exact')


@lru_cache(maxsize=128)
def _immutable_source_digest(root_text: str, ref: str, path: str):
    return sha256(git(Path(root_text), 'show', ref+':'+path))


def _reviewed_v666_descendant(root: Path, path: str, old_digest: str) -> bool:
    """Accept only an exact, independently pinned later review in this checkout."""
    try:
        import unittest
        import sync_v376_successor_test_support as successor
        if root.resolve() != successor.ROOT.resolve():
            return False
        proof = successor.V666_PROOF
        if proof['baseline_sha256'].get(path) != old_digest:
            return False
        successor.assert_v666_successor(unittest.TestCase())
        return True
    except (AssertionError, AttributeError, ImportError, KeyError, OSError, ValueError, subprocess.SubprocessError):
        return False


def verify(root: Path, proof: dict):
    if proof != EXPECTED:
        raise Hold('contract_not_pinned')
    if git(root, 'rev-parse', '--show-toplevel').decode('utf-8').strip() != str(root.resolve()):
        raise Hold('wrong_repository_root')
    _immutable_scope(str(root.resolve()), BASE, CANDIDATE, tuple(CHANGED))
    # HEAD ancestry, descendant changes, dirty state and current bytes are never cached.
    git(root, 'merge-base', '--is-ancestor', CANDIDATE, 'HEAD')
    paths = sorted(REVIEWED)
    changed = git(root, 'diff', '--name-only', CANDIDATE, 'HEAD', '--', *paths).decode('utf-8').splitlines()
    if any(not _reviewed_v666_descendant(root, path, REVIEWED[path]['after']) for path in changed):
        raise Hold('unreviewed_descendant_source')
    if git(root, 'diff', '--name-only', '--', *paths).strip() or git(root, 'diff', '--cached', '--name-only', '--', *paths).strip():
        raise Hold('dirty_watched_source')
    for path, pins in REVIEWED.items():
        f = root / path
        if f.is_symlink() or not f.is_file() or f.stat().st_size > 2_000_000:
            raise Hold('unsafe_or_missing_source:' + path)
        if _immutable_source_digest(str(root.resolve()), BASE, path) != pins['before']:
            raise Hold('baseline_hash_mismatch:' + path)
        if _immutable_source_digest(str(root.resolve()), CANDIDATE, path) != pins['after']:
            raise Hold('candidate_hash_mismatch:' + path)
        if sha256(f.read_bytes()) != pins['after'] and not _reviewed_v666_descendant(root, path, pins['after']):
            raise Hold('live_hash_mismatch:' + path)
    return {'decision': 'SOURCE_PREFLIGHT_ONLY', 'reviewed_sources': paths,
            'legacy_successor_ci_repaired': False, 'physical_tablet_verified': False,
            'deployment_allowed': False}


def main():
    try:
        result = verify(ROOT, load(ROOT))
    except (Hold, OSError) as e:
        result = {'decision': 'HOLD', 'reasons': [str(e)], 'deployment_allowed': False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result['decision'] == 'SOURCE_PREFLIGHT_ONLY' else 2


if __name__ == '__main__':
    sys.exit(main())
