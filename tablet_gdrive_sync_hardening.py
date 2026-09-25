#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile

import tablet_gdrive_sync as core

RUNNER_LOCK = "runner.lock"
INFLIGHT = "inflight_transaction.json"
LEGACY_LOCK = "sync.lock"

_ORIGINAL_BACKUP_CURRENT = core.backup_current
_ORIGINAL_RESTORE_BACKUP = core.restore_backup
_ORIGINAL_STOP_SERVER = core.stop_server
_ORIGINAL_WRITE_RECEIPT = core.write_receipt


def state_root() -> Path:
    return Path.home() / ".local" / "state" / "tcg-grader" / "gdrive-sync"


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def acquire_runner_lock(state: Path):
    if state.is_symlink():
        raise RuntimeError("sync state directory is a symlink")
    state.mkdir(parents=True, exist_ok=True)
    if state.is_symlink() or not state.is_dir():
        raise RuntimeError("sync state directory is unsafe")
    path = state / RUNNER_LOCK
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("runner lock open failed safely") from exc
    handle = None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise RuntimeError("runner lock is not a private regular file")
        try:
            os.fchmod(descriptor, 0o600)
        except OSError:
            pass
        handle = os.fdopen(descriptor, "r+", encoding="utf-8")
        descriptor = -1
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return None
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} started_at={dt.datetime.now(dt.timezone.utc).isoformat()}\n")
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
        return handle
    except BaseException:
        if handle is not None and not handle.closed:
            handle.close()
        elif descriptor >= 0:
            os.close(descriptor)
        raise

def release_runner_lock(handle) -> None:
    if handle is None:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def remove_legacy_lock(state: Path) -> None:
    lock = state / LEGACY_LOCK
    if not lock.exists() and not lock.is_symlink():
        return
    if lock.is_symlink():
        raise RuntimeError("legacy sync lock is a symlink")
    if not lock.is_dir():
        raise RuntimeError("legacy sync lock has unexpected type")
    shutil.rmtree(lock)


def rotate_existing_backup(backup: Path) -> Path | None:
    if not backup.exists() and not backup.is_symlink():
        return None
    if backup.is_symlink() or not backup.is_dir():
        raise RuntimeError("existing backup path is unsafe")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    rotated = backup.with_name(f"{backup.name}.previous.{stamp}.{os.getpid()}")
    os.replace(backup, rotated)
    return rotated


def verify_backup(backup: Path) -> dict[str, str]:
    if backup.is_symlink() or not backup.is_dir():
        raise RuntimeError("backup directory is missing or unsafe")
    manifest_path = backup / "backup_manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise RuntimeError("backup manifest is missing or unsafe")
    raw = manifest_path.read_bytes()
    if len(raw) > 1_000_000:
        raise RuntimeError("backup manifest is too large")
    data = core.strict_json_loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("backup manifest must be an object")
    hashes = data.get("sha256")
    if not isinstance(hashes, dict) or set(hashes) != set(core.OUTPUTS):
        raise RuntimeError("backup manifest does not cover exact runtime outputs")
    trusted: dict[str, str] = {}
    for name in core.OUTPUTS:
        path = backup / name
        expected = hashes.get(name)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"backup file missing or unsafe: {name}")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise RuntimeError(f"backup hash invalid: {name}")
        if core.sha256(path) != expected:
            raise RuntimeError(f"backup hash mismatch: {name}")
        trusted[name] = expected
    return trusted

def transaction_path(state: Path) -> Path:
    return state / INFLIGHT


def write_transaction(state: Path, repo: Path, backup: Path) -> None:
    root = (state / "last_good").resolve()
    resolved_backup = backup.resolve()
    if not _is_within(resolved_backup, root):
        raise RuntimeError("backup path escaped last_good")
    core.atomic_write_json(
        transaction_path(state),
        {
            "schema_version": 1,
            "repo": str(repo.resolve()),
            "backup": str(resolved_backup),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
    )


def clear_transaction(state: Path) -> None:
    path = transaction_path(state)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def hardened_backup_current(repo: Path, backup: Path) -> None:
    rotate_existing_backup(backup)
    _ORIGINAL_BACKUP_CURRENT(repo, backup)
    verify_backup(backup)
    write_transaction(state_root(), repo, backup)


def hardened_restore_backup(repo: Path, backup: Path) -> None:
    hashes = verify_backup(backup)
    _ORIGINAL_RESTORE_BACKUP(repo, backup)
    for name in core.OUTPUTS:
        if core.sha256(repo / name) != hashes[name]:
            raise RuntimeError(f"rollback readback mismatch: {name}")

def hardened_stop_server(repo: Path) -> None:
    pid = core.read_launcher_pid(repo)
    if pid is None and core.health_ok():
        raise RuntimeError("runtime is healthy but launcher PID is missing; refuse live data replacement")
    _ORIGINAL_STOP_SERVER(repo)


def hardened_write_receipt(state: Path, manifest: dict, status: str, details: dict) -> Path:
    path = _ORIGINAL_WRITE_RECEIPT(state, manifest, status, details)
    if status in {"TABLET_SYNC_OK", "FAILED_ROLLED_BACK"}:
        clear_transaction(state)
    return path


def patch_core() -> None:
    core.backup_current = hardened_backup_current
    core.restore_backup = hardened_restore_backup
    core.stop_server = hardened_stop_server
    core.write_receipt = hardened_write_receipt


def recover_incomplete(repo: Path, state: Path) -> bool:
    marker = transaction_path(state)
    if not marker.exists():
        return False
    if marker.is_symlink() or not marker.is_file():
        raise RuntimeError("inflight transaction marker is unsafe")
    raw = marker.read_bytes()
    if len(raw) > 1_000_000:
        raise RuntimeError("inflight transaction marker is too large")
    data = core.strict_json_loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("inflight transaction marker must be an object")
    marker_repo = Path(str(data.get("repo", ""))).expanduser().resolve()
    if marker_repo != repo.resolve():
        raise RuntimeError("inflight transaction repo mismatch")
    backup = Path(str(data.get("backup", ""))).expanduser().resolve()
    last_good = (state / "last_good").resolve()
    if not _is_within(backup, last_good):
        raise RuntimeError("inflight backup path escaped last_good")
    verify_backup(backup)
    was_healthy = core.health_ok()
    if was_healthy:
        hardened_stop_server(repo)
    hardened_restore_backup(repo, backup)
    if was_healthy:
        core.start_server(repo, state)
        if not core.health_ok():
            raise RuntimeError("runtime health failed after crash recovery")
    clear_transaction(state)
    print("[복구] 중단된 Google Drive 자료 적용을 last-good으로 되돌렸습니다.")
    return True


def run_sync(repo: Path, remote: str, remote_root: str, recover_only: bool = False) -> int:
    state = state_root()
    state.mkdir(parents=True, exist_ok=True)
    handle = acquire_runner_lock(state)
    if handle is None:
        print("[OK] Google Drive 동기화가 이미 실행 중입니다.")
        return 0
    try:
        patch_core()
        recover_incomplete(repo, state)
        remove_legacy_lock(state)
        if recover_only:
            print("[OK] 미완료 Google Drive 적용 복구 점검 완료")
            return 0
        return core.sync_once(repo, remote, remote_root)
    finally:
        release_runner_lock(handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote", default=os.environ.get("TCG_GDRIVE_REMOTE", core.DEFAULT_REMOTE))
    parser.add_argument("--remote-root", default=os.environ.get("TCG_GDRIVE_ROOT", core.DEFAULT_REMOTE_ROOT))
    parser.add_argument("--repo", default=os.environ.get("TCG_REPO_DIR"))
    parser.add_argument("--recover-only", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).expanduser().resolve() if args.repo else Path(__file__).resolve().parent
    try:
        remote = core.safe_remote_name(args.remote)
        remote_root = args.remote_root.strip("/")
        if not remote_root or ".." in Path(remote_root).parts or any(c in remote_root for c in "\r\n"):
            raise ValueError("invalid Google Drive remote root")
        return run_sync(repo, remote, remote_root, args.recover_only)
    except subprocess.TimeoutExpired as exc:
        print(f"[DEFERRED] timeout: {exc}", file=sys.stderr)
        return 75
    except subprocess.CalledProcessError as exc:
        print(f"[DEFERRED] external command failed: {exc}", file=sys.stderr)
        return 75
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, tarfile.TarError) as exc:
        print(f"[HOLD] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
