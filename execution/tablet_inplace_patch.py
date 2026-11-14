"""Explicit local adoption of reviewed origin/main for a detached tablet checkout.

Plan by default. No network except the CLI's canonical fetch; no process killing,
training, data restoration, hard reset, or automatic release approval.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import uuid

try:
    from . import tablet_preserved_update as support
except ImportError:
    import tablet_preserved_update as support

Hold = support.Hold


def git(repo, *args, timeout=120):
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_LITERAL_PATHSPECS='1')
    run = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                         check=True, timeout=timeout, env=environment)
    return run.stdout.decode('utf-8', errors='strict').rstrip('\n')


def changes(repo):
    rows = git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=no')
    names = []
    for row in rows.split('\0'):
        if not row:
            continue
        if len(row) < 4 or row[:2] not in {' M', 'M ', 'MM'} or row[2] != ' ':
            raise Hold('UNSUPPORTED_INDEX_STATE')
        name = row[3:]
        if name not in support.SOURCE_PATHS | support.RUNTIME_PATHS:
            raise Hold('UNKNOWN_CHANGED_PATH: ' + name)
        fingerprint(checked_path(repo, name))
        names.append(name)
    if len(names) > 128 or len(names) != len(set(names)):
        raise Hold('INVALID_CHANGE_COUNT')
    return sorted(names)


def checked_path(root, name):
    parts = PurePosixPath(name).parts
    if not parts or name != '/'.join(parts) or any(p in ('.', '..', '.git') for p in parts) or '\\' in name:
        raise Hold('UNSAFE_PATH')
    path = root.joinpath(*parts)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise Hold('SYMLINK_PATH')
    return path


def tree(repo, revision):
    result = {}
    for row in git(repo, 'ls-tree', '-rz', '--full-tree', revision).split('\0'):
        if row:
            meta, name = row.split('\t', 1)
            mode, kind, sha = meta.split()
            checked_path(repo, name)
            if mode not in ('100644', '100755') or kind != 'blob':
                raise Hold('UNSUPPORTED_TREE_ENTRY: ' + name)
            result[name] = (mode, sha)
    return result


def fingerprint(path):
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise Hold('NOT_REGULAR_FILE')
    before = path.stat()
    value = support.digest(path)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise Hold('FILE_CHANGED_DURING_READ')
    return [value, stat.S_IMODE(after.st_mode)]


def idle(repo, proc=Path('/proc')):
    """Never reuse a stored PID or send a signal. A busy installation must wait."""
    for name in ('.tcg_android_start.lock', '.tcg_scheduled_update.lock'):
        if (repo / name).exists() or (repo / name).is_symlink():
            raise Hold('RUNTIME_LOCK_BUSY: ' + name)
    for entry in proc.iterdir():
        if not entry.name.isdecimal() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            cwd = (entry / 'cwd').resolve(strict=True)
            raw = (entry / 'cmdline').read_bytes()
            if raw and not raw.endswith(b'\0'):
                raise Hold('PROCESS_COMMAND_UNAVAILABLE')
            args = raw[:-1].split(b'\0') if raw else []
            command_uses_repo = any(os.fsdecode(a) == str(repo) or os.fsdecode(a).startswith(str(repo) + '/') for a in args)
            if cwd != repo and repo not in cwd.parents and not command_uses_repo:
                continue
            # A login shell with only -l/--login has no script or -c command.
            # Its active children are still inspected independently below.
            shell = bool(args) and Path(os.fsdecode(args[0])).name in ('bash', 'sh', 'zsh')
            prompt_only = shell and (len(args) == 1 or (
                len(args) == 2 and args[1] in (b'-l', b'--login')))
            if args and not prompt_only:
                raise Hold('REPO_PROCESS_BUSY: ' + entry.name)
        except FileNotFoundError:
            continue  # exited during inspection
        except PermissionError as exc:
            raise Hold('PROCESS_STATE_UNAVAILABLE') from exc


def atomic_copy(source, destination, mode):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.patch-' + uuid.uuid4().hex)
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as dst, source.open('rb') as src:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def patch(repo: Path, backup_root: Path, expected_target: str, *, apply=False):
    repo = repo.absolute()
    if any(p.is_symlink() for p in (repo, *repo.parents)) or not (repo / '.git').is_dir() or (repo / '.git').is_symlink():
        raise Hold('REGULAR_CHECKOUT_REQUIRED')
    if git(repo, 'remote', 'get-url', 'origin') not in support.ORIGINS:
        raise Hold('UNEXPECTED_ORIGIN')
    if not re.fullmatch('[0-9a-f]{40}', expected_target):
        raise Hold('EXACT_RELEASE_SHA_REQUIRED')
    target = git(repo, 'rev-parse', 'refs/remotes/origin/main^{commit}')
    if target != expected_target:
        raise Hold('RELEASE_SHA_MISMATCH')
    branch = subprocess.run(['git', '-C', str(repo), 'symbolic-ref', '-q', 'HEAD'], capture_output=True)
    if branch.returncode == 0:
        raise Hold('DETACHED_CHECKOUT_REQUIRED_USE_NORMAL_UPDATER_FOR_MAIN')
    if branch.returncode != 1:
        raise Hold('HEAD_STATE_UNAVAILABLE')
    if 'branch refs/heads/main' in git(repo, 'worktree', 'list', '--porcelain', '-z').split('\0'):
        raise Hold('MAIN_CHECKED_OUT_IN_ANOTHER_WORKTREE')
    before = git(repo, 'rev-parse', 'HEAD')
    old_main_run = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--verify', 'refs/heads/main'], capture_output=True)
    old_main = old_main_run.stdout.decode().strip() if old_main_run.returncode == 0 else '0' * 40
    if old_main_run.returncode not in (0, 128):
        raise Hold('MAIN_REF_UNAVAILABLE')
    dirty = changes(repo)
    old, new = tree(repo, before), tree(repo, target)
    # Data files retain their exact working bytes even if the new Git base differs.
    paths = sorted(({p for p in old.keys() | new.keys() if old.get(p) != new.get(p)} | set(dirty)) - support.RUNTIME_PATHS)
    if not paths or len(paths) > 4096:
        raise Hold('EMPTY_OR_OVERSIZED_PATCH')
    snapshots = {}
    for name in paths:
        path = checked_path(repo, name)
        snapshots[name] = fingerprint(path)
        if name not in old and snapshots[name] is not None:
            raise Hold('UNTRACKED_COLLISION: ' + name)
    runtime = {p: fingerprint(checked_path(repo, p)) for p in sorted(support.RUNTIME_PATHS) if (repo / p).exists()}
    plan = {'status': 'PLAN_ONLY', 'before': before, 'target': target,
            'source_files': len(paths), 'runtime_files_preserved': len(runtime),
            'physical_tablet_verified': False}
    if not apply:
        return plan
    backup_root = backup_root.absolute()
    if backup_root == repo or repo in backup_root.parents:
        raise Hold('BACKUP_MUST_BE_OUTSIDE_CHECKOUT')
    idle(repo)
    support.safe_directory(backup_root)
    lock = repo / '.tcg_android_update.lock'
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise Hold('UPDATE_LOCK_BUSY') from exc
    (lock / 'pid').write_text(str(os.getpid()) + '\n', encoding='ascii')
    backup = backup_root / ('inplace-' + uuid.uuid4().hex)
    mutated = False
    created_dirs = []
    result = dict(plan, status='HOLD', backup=str(backup))
    try:
        backup.mkdir(mode=0o700)
        support.verify_candidate(repo, target, backup)
        idle(repo)
        index = repo / '.git/index'
        if index.is_symlink() or (repo / '.git/index.lock').exists():
            raise Hold('INDEX_BUSY_OR_UNSAFE')
        index_hash = support.digest(index)
        shutil.copy2(index, backup / 'index')
        for name in paths:
            path = checked_path(repo, name)
            if snapshots[name] is not None:
                saved = checked_path(backup / 'original', name)
                atomic_copy(path, saved, snapshots[name][1])
                if fingerprint(saved) != snapshots[name]:
                    raise Hold('BACKUP_READBACK_FAILED')
            if name in new:
                staged = checked_path(backup / 'incoming', name)
                staged.parent.mkdir(parents=True, exist_ok=True)
                with staged.open('xb') as stream:
                    subprocess.run(['git', '-C', str(repo), 'cat-file', 'blob', new[name][1]], stdout=stream, check=True, timeout=30)
                if git(repo, 'hash-object', str(staged)) != new[name][1]:
                    raise Hold('INCOMING_BLOB_MISMATCH')
        token = 'refs/tcg-recovery/inplace-' + uuid.uuid4().hex
        git(repo, 'update-ref', token, before, '0' * 40)
        if old_main != '0' * 40:
            git(repo, 'update-ref', token + '-main', old_main, '0' * 40)
        result['backup_ref'] = token
        # A copied index alone does not keep its staged blobs alive through GC.
        # Create the archive through a separate index, leaving the live index exact.
        stash_index = backup / 'stash-index'
        shutil.copy2(backup / 'index', stash_index)
        archive_env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_INDEX_FILE=str(stash_index))
        archive = subprocess.run(['git', '-C', str(repo), 'stash', 'create', 'tablet-inplace-preserve'],
                                 capture_output=True, check=True, timeout=120, env=archive_env).stdout.decode().strip()
        if dirty and not re.fullmatch('[0-9a-f]{40}', archive):
            raise Hold('STAGED_OBJECT_ARCHIVE_REQUIRED')
        if archive:
            git(repo, 'update-ref', token + '-index', archive, '0' * 40)
            result['index_archive_ref'] = token + '-index'
        support.receipt(backup / 'receipt.json', dict(result, phase='BACKED_UP', paths=paths,
                        original_main=old_main, original_files=snapshots))
        def unchanged():
            if git(repo, 'rev-parse', 'HEAD') != before or support.digest(index) != index_hash:
                raise Hold('CHECKOUT_CHANGED')
            if changes(repo) != dirty or any(fingerprint(checked_path(repo, p)) != v for p, v in snapshots.items()):
                raise Hold('SOURCE_CHANGED')
            if any(fingerprint(checked_path(repo, p)) != v for p, v in runtime.items()):
                raise Hold('RUNTIME_CHANGED')
        unchanged()
        idle(repo)
        mutated = True
        for name in paths:
            path = checked_path(repo, name)
            if name in new:
                missing = []
                parent = path.parent
                while not parent.exists():
                    missing.append(parent)
                    parent = parent.parent
                created_dirs.extend(reversed(missing))
                atomic_copy(backup / 'incoming' / name, path, int(new[name][0], 8) & 0o777)
            else:
                path.unlink(missing_ok=True)
        for name in paths:
            path = checked_path(repo, name)
            if name in new:
                if git(repo, 'hash-object', str(path)) != new[name][1]:
                    raise Hold('INSTALLED_SOURCE_MISMATCH')
            elif path.exists():
                raise Hold('OBSOLETE_SOURCE_REMAINS')
        if any(fingerprint(checked_path(repo, p)) != v for p, v in runtime.items()):
            raise Hold('RUNTIME_CHANGED')
        idle(repo)
        if support.digest(index) != index_hash or git(repo, 'rev-parse', 'HEAD') != before:
            raise Hold('CHECKOUT_CHANGED')
        git(repo, 'read-tree', target)  # index only: never rewrite live JSON
        git(repo, 'update-ref', 'refs/heads/main', target, old_main)
        git(repo, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        if git(repo, 'rev-parse', 'HEAD') != target:
            raise Hold('FINAL_HEAD_MISMATCH')
        if any(fingerprint(checked_path(repo, p)) != v for p, v in runtime.items()):
            raise Hold('RUNTIME_CHANGED')
        result.update(status='PATCHED_SOURCE_ONLY', rollback='NOT_NEEDED')
        support.receipt(backup / 'receipt.json', dict(result, phase='COMPLETE', paths=paths,
                        original_main=old_main, original_files=snapshots))
        return result
    except (Exception, KeyboardInterrupt) as exc:
        result['status'] = 'HOLD'
        result['reason'] = str(exc) if isinstance(exc, Hold) else type(exc).__name__
        if mutated:
            try:
                current_head = git(repo, 'rev-parse', 'HEAD')
                if current_head not in (before, target):
                    raise Hold('CONCURRENT_HEAD_CHANGE_KEEP_BACKUP')
                attached = subprocess.run(['git', '-C', str(repo), 'symbolic-ref', '-q', 'HEAD'], capture_output=True)
                if attached.returncode == 0:
                    if attached.stdout.decode().strip() != 'refs/heads/main':
                        raise Hold('CONCURRENT_BRANCH_CHANGE_KEEP_BACKUP')
                    git(repo, 'update-ref', '--no-deref', 'HEAD', before)
                current_main = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--verify', 'refs/heads/main'], capture_output=True)
                main_now = current_main.stdout.decode().strip() if current_main.returncode == 0 else '0' * 40
                if main_now not in (old_main, target):
                    raise Hold('CONCURRENT_MAIN_CHANGE_KEEP_BACKUP')
                if main_now != old_main:
                    if old_main == '0' * 40:
                        git(repo, 'update-ref', '-d', 'refs/heads/main', target)
                    else:
                        git(repo, 'update-ref', 'refs/heads/main', old_main, target)
                for name in reversed(paths):
                    path = checked_path(repo, name)
                    if snapshots[name] is None:
                        path.unlink(missing_ok=True)
                    else:
                        atomic_copy(backup / 'original' / name, path, snapshots[name][1])
                atomic_copy(backup / 'index', repo / '.git/index', 0o600)
                for directory in reversed(created_dirs):
                    directory.rmdir()
                if git(repo, 'rev-parse', 'HEAD') != before or support.digest(repo / '.git/index') != index_hash:
                    raise Hold('ROLLBACK_READBACK_FAILED')
                if any(fingerprint(checked_path(repo, p)) != v for p, v in snapshots.items()):
                    raise Hold('ROLLBACK_READBACK_FAILED')
                result['rollback'] = 'ORIGINAL_SOURCE_HEAD_INDEX_RESTORED'
            except (Exception, KeyboardInterrupt):
                result['rollback'] = 'MANUAL_RECOVERY_REQUIRED_KEEP_BACKUP'
        return result
    finally:
        if (lock / 'pid').read_text(encoding='ascii').strip() == str(os.getpid()):
            (lock / 'pid').unlink()
            lock.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.home() / '-tcg-grader')
    parser.add_argument('--backup-root', type=Path, default=Path.home() / 'tcg-inplace-patch-backups')
    parser.add_argument('--expected-target', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        if git(args.repo, 'remote', 'get-url', 'origin') not in support.ORIGINS:
            raise Hold('UNEXPECTED_ORIGIN')
        git(args.repo, 'fetch', '--no-tags', support.OFFICIAL, '+refs/heads/main:refs/remotes/origin/main', timeout=180)
        result = patch(args.repo, args.backup_root, args.expected_target, apply=args.apply)
    except (Hold, OSError, ValueError, subprocess.SubprocessError) as exc:
        result = {'status': 'HOLD', 'reason': str(exc) if isinstance(exc, Hold) else type(exc).__name__}
    messages = {'PLAN_ONLY': '적용 전 계획 확인입니다. 운영 코드는 변경하지 않았습니다.',
                'PATCHED_SOURCE_ONLY': '기존 폴더의 코드 패치를 완료했습니다. 서버 시작·태블릿 화면 확인은 별도입니다.',
                'HOLD': '적용을 중단했습니다. 사유와 복구 결과를 확인하세요.'}
    result['안내'] = messages[result['status']]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] in ('PLAN_ONLY', 'PATCHED_SOURCE_ONLY') else 2


if __name__ == '__main__':
    raise SystemExit(main())
