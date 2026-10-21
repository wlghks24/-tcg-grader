"""One-time local update recovery; archive source edits and retain live JSON bytes.

Does not train, upload, reset HEAD, pop a stash, or interpret runtime data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

OFFICIAL = "https://github.com/wlghks24/-tcg-grader.git"
ORIGINS = {OFFICIAL, OFFICIAL.removesuffix('.git'),
           'git@github.com:wlghks24/-tcg-grader.git',
           'ssh://git@github.com/wlghks24/-tcg-grader.git'}
SOURCE_PATHS = frozenset('''TABLET_SCHEDULED_UPDATE.sh event_collection_hardening_v140.py
feature_category_nav.css index.html multi_route_event_discovery.py social_event_discovery.py
sw.js tablet_autonomous_evolution_v382.py tablet_runtime_manifest.py tcg_local_collection_v505.js
tcg_market_expanded_v487.js tcg_updater.py tcg_updater_v135.py test_multi_route_event_discovery.py
update_market_watch.py update_releases.py'''.split())
RUNTIME_PATHS = frozenset('''tcg_live_data.json releases.json market_watch.json market_prices.json
tcg_game_registry.json promo_events.json purchase_sources.json purchase_signals.json
social_stock_signals.json exchange_rates.json grading_company_updates.json graded_photo_candidates.json
supplementary_candidates.json social_event_candidates.json social_source_registry.json
web_discovery_candidates.json link_health_report.json auto_update_report.json auto_update_issues.json
auto_repair_memory.json adaptive_collection_stats.json adaptive_collection_stats.json.bak
verified_certifications.json learning_store.json vision_self_learning_report.json vision_calibration.json
ebay_grader_candidates.json card_identity_learning.json source_collection_stats.json
source_collection_stats.json.bak precollect_status.json graded_photo_reference_learning.json
library_verified_slab_references.json graded_photo_source_learning.json verified_slab_raw_learning_v155.json
verified_slab_training_archive.json event_gap_learning.json existing_photo_revalidation_v160.json
manual_collected_pair_queue.json manual_official_proof_references.json market_public_crosscheck_state.json
pending_official_candidate_rejections.json box_hit_market_candidates.json box_hit_market_learning.json
collector_self_heal_memory.json graded_file_learning_report.json graded_photo_official_cache.json
release_history_progress.json manual_event_evidence.json release_parser_learning.json'''.split())


class Hold(RuntimeError):
    pass


def git(repo: Path, *args: str, timeout: int = 120) -> str:
    run = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                         timeout=timeout, check=True)
    return run.stdout.decode('utf-8', errors='strict').rstrip('\n')


def digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise Hold('UNSAFE_OR_OVERSIZED_FILE')
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            value.update(chunk)
    return value.hexdigest()


def safe_directory(path: Path) -> None:
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise Hold('UNSAFE_DIRECTORY')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)


def changes(repo: Path) -> list[str]:
    rows = git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=no')
    paths = []
    for row in rows.split('\0'):
        if not row:
            continue
        if len(row) < 4 or row[:2] not in {' M', 'M ', 'MM'} or row[2] != ' ':
            raise Hold('UNSUPPORTED_INDEX_STATE')
        name = row[3:]
        if name not in SOURCE_PATHS | RUNTIME_PATHS:
            raise Hold('UNKNOWN_CHANGED_PATH: ' + name)
        digest(repo / name)
        paths.append(name)
    if len(paths) > 128 or len(paths) != len(set(paths)):
        raise Hold('INVALID_CHANGE_COUNT')
    return sorted(paths)


def receipt(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if json.loads(path.read_text(encoding='utf-8')) != value:
        raise Hold('RECEIPT_READBACK_FAILED')


def verify_candidate(repo: Path, target: str, backup: Path) -> None:
    candidate = Path(tempfile.mkdtemp(prefix='candidate-', dir=backup))
    added = False
    try:
        git(repo, 'worktree', 'add', '--detach', '--quiet', str(candidate), target)
        added = True
        environment = dict(os.environ, TCG_FINAL_SKIP_HEAD_MATCH='1', TCG_CANDIDATE_PREFLIGHT='1')
        with (backup / 'candidate-verification.log').open('xb') as log:
            subprocess.run(['bash', 'VERIFY_TABLET_FINAL.sh'], cwd=candidate,
                           env=environment, stdout=log, stderr=subprocess.STDOUT,
                           timeout=300, check=True)
    finally:
        if added:
            git(repo, 'worktree', 'remove', '--force', str(candidate))
        elif candidate.exists():
            candidate.rmdir()


def repair(repo: Path, backup_root: Path, *, apply: bool = False) -> dict:
    if repo.is_symlink() or not (repo / '.git').is_dir() or (repo / '.git').is_symlink():
        raise Hold('REGULAR_GIT_CHECKOUT_REQUIRED')
    repo = repo.resolve()
    if git(repo, 'remote', 'get-url', 'origin') not in ORIGINS:
        raise Hold('OFFICIAL_ORIGIN_REQUIRED')
    if git(repo, 'branch', '--show-current') != 'main':
        raise Hold('MAIN_BRANCH_REQUIRED')
    if git(repo, 'diff', '--name-only', '--diff-filter=U'):
        raise Hold('UNMERGED_INDEX')
    before, target = git(repo, 'rev-parse', 'HEAD'), git(repo, 'rev-parse', 'refs/remotes/origin/main')
    git(repo, 'merge-base', '--is-ancestor', before, target)
    dirty = changes(repo)
    sources, runtime = sorted(set(dirty) & SOURCE_PATHS), sorted(set(dirty) & RUNTIME_PATHS)
    if git(repo, 'diff', '--name-only', before, target, '--', *sorted(RUNTIME_PATHS)):
        raise Hold('REMOTE_RUNTIME_CHANGE_REQUIRES_REVIEW')
    result = dict(status='PLAN_ONLY', before=before, target=target,
                  source_paths=sources, runtime_paths=runtime,
                  source_edits_auto_reapplied=False, physical_tablet_verified=False)
    if not apply:
        return result
    if backup_root.resolve().is_relative_to(repo):
        raise Hold('BACKUP_MUST_BE_OUTSIDE_CHECKOUT')
    sizes = git(repo, 'ls-tree', '-r', '-l', target).splitlines()
    checkout_bytes = sum(int(row.split('\t', 1)[0].split()[-1]) for row in sizes
                         if row.split('\t', 1)[0].split()[-1].isdigit())
    required_bytes = 2 * checkout_bytes + 3 * sum((repo / name).stat().st_size for name in dirty) + 16 * 1024 * 1024
    if shutil.disk_usage(repo).free < required_bytes:
        raise Hold('INSUFFICIENT_FREE_SPACE_FOR_VERIFIED_BACKUP')
    safe_directory(backup_root)
    lock = repo / '.tcg_android_update.lock'
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise Hold('UPDATE_LOCK_BUSY') from exc
    lock_pid = lock / 'pid'
    backup = None
    archived = None
    mutating = False
    original_index = None
    try:
        lock_pid.write_text(str(os.getpid()), encoding='ascii')
        moment = datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d-%H%M%S')
        token = moment + '-' + uuid.uuid4().hex[:12]
        backup = backup_root / token
        backup.mkdir(mode=0o700)
        result['backup_directory'] = str(backup)
        verify_candidate(repo, target, backup)
        if before != git(repo, 'rev-parse', 'HEAD') or dirty != changes(repo):
            raise Hold('CHECKOUT_CHANGED_DURING_PREFLIGHT')
        hashes = {name: digest(repo / name) for name in sources}
        original_index = git(repo, 'write-tree')
        if dirty:
            archived = git(repo, '-c', 'user.name=TCG Local Recovery',
                           '-c', 'user.email=local-recovery@localhost',
                           '-c', 'commit.gpgsign=false', 'stash', 'create', 'tcg-preserved-' + token)
            if not archived or git(repo, 'rev-parse', archived + '^2^{tree}') != original_index:
                raise Hold('INDEX_BACKUP_VERIFICATION_FAILED')
            reference = 'refs/tcg-recovery/' + token
            git(repo, 'update-ref', reference, archived, '0' * 40)
            if git(repo, 'rev-parse', reference) != archived:
                raise Hold('BACKUP_REF_VERIFICATION_FAILED')
            result.update(backup_ref=reference, backup_commit=archived, original_index_tree=original_index)
            raw_sources = backup / 'source-files'
            raw_sources.mkdir(mode=0o700)
            for name in sources:
                shutil.copy2(repo / name, raw_sources / name)
                if digest(raw_sources / name) != hashes[name]:
                    raise Hold('SOURCE_BACKUP_VERIFICATION_FAILED')
        result['status'] = 'BACKED_UP'
        receipt(backup / 'receipt.json', result)
        if original_index != git(repo, 'write-tree') or before != git(repo, 'rev-parse', 'HEAD'):
            raise Hold('INDEX_OR_HEAD_CHANGED_AFTER_BACKUP')
        if any(digest(repo / name) != hashes[name] for name in sources):
            raise Hold('SOURCE_CHANGED_AFTER_BACKUP')
        runtime_before = {name: digest(repo / name) for name in runtime}
        mutating = True
        if sources:
            git(repo, 'restore', '--source=HEAD', '--staged', '--worktree', '--', *sources)
        if runtime:
            git(repo, 'restore', '--source=HEAD', '--staged', '--', *runtime)
        git(repo, 'diff', '--cached', '--quiet')
        git(repo, 'merge', '--ff-only', target, timeout=180)
        if git(repo, 'rev-parse', 'HEAD') != target:
            raise Hold('POSTCHECK_HEAD_MISMATCH')
        if sources:
            git(repo, 'diff', '--quiet', target, '--', *sources)
        with (backup / 'installed-runtime-verification.log').open('xb') as log:
            subprocess.run([sys.executable, 'tablet_runtime_manifest.py', '--check', '--compile'],
                           cwd=repo, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
        runtime_after = {name: digest(repo / name) for name in runtime}
        result.update(status='UPDATED', installed_sha=target,
                      runtime_before_sha256=runtime_before, runtime_after_sha256=runtime_after,
                      runtime_changed_during_operation=[n for n in runtime if runtime_before[n] != runtime_after[n]])
        receipt(backup / 'receipt.json', result)
        return result
    except (Hold, OSError, ValueError, subprocess.SubprocessError) as exc:
        result.update(status='HOLD', error_type=type(exc).__name__, reason=str(exc) if isinstance(exc, Hold) else type(exc).__name__)
        if mutating and archived and git(repo, 'rev-parse', 'HEAD') == before:
            try:
                git(repo, 'restore', '--source=' + archived + '^2', '--staged', '--', *dirty)
                for name in sources:
                    temporary = repo / ('.tcg-recover-' + uuid.uuid4().hex)
                    try:
                        shutil.copy2(backup / 'source-files' / name, temporary)
                        os.replace(temporary, repo / name)
                    finally:
                        temporary.unlink(missing_ok=True)
                if git(repo, 'write-tree') != original_index:
                    raise Hold('INDEX_ROLLBACK_MISMATCH')
                result['rollback'] = 'ORIGINAL_INDEX_AND_SOURCE_RESTORED'
            except (Hold, OSError, subprocess.SubprocessError):
                result['rollback'] = 'MANUAL_RECOVERY_REQUIRED'
        if backup is not None:
            receipt(backup / 'receipt.json', result)
        return result
    finally:
        if lock_pid.is_file() and lock_pid.read_text(encoding='ascii') == str(os.getpid()):
            lock_pid.unlink()
            lock.rmdir()
        elif not lock_pid.exists():
            lock.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--start', action='store_true')
    args = parser.parse_args()
    if args.start and not args.apply:
        parser.error('--start requires --apply')
    previous_mask = os.umask(0o077)
    try:
        repo = args.repo.absolute()
        # Refuse an altered origin before fetching a fixed canonical URL.
        if git(repo, 'remote', 'get-url', 'origin') not in ORIGINS:
            raise Hold('OFFICIAL_ORIGIN_REQUIRED')
        git(repo, 'fetch', OFFICIAL, 'refs/heads/main:refs/remotes/origin/main', timeout=180)
        result = repair(repo, Path.home() / '.local/state/tcg-grader/preserved-update', apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        if result['status'] == 'HOLD':
            return 2
        if args.start:
            subprocess.run(['bash', 'ANDROID_AUTO_START_INSTALL.sh'], cwd=repo, check=True)
            # Use the already verified launchers without a second source update.
            subprocess.run(['bash', 'TABLET_SCHEDULED_UPDATE.sh', 'ensure'], cwd=repo, check=False)
            return subprocess.run(['bash', 'START_TCG_UPDATER_ANDROID.sh'], cwd=repo, check=False).returncode
        return 0
    except (Hold, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'HOLD', 'reason': str(exc) if isinstance(exc, Hold) else type(exc).__name__}))
        return 2
    finally:
        os.umask(previous_mask)


if __name__ == '__main__':
    raise SystemExit(main())
