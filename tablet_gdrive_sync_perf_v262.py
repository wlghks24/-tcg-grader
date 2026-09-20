#!/usr/bin/env python3
"""v262 performance/reliability layer for the tablet Google Drive sync.

This module deliberately wraps the verified contextual/hardening stack instead
of weakening any gate.  It only removes avoidable local/remote work:
- bound remote manifest discovery to the same freshness horizon the manifest
  validator already accepts;
- use the universal /api/health endpoint once per probe instead of two serial
  HTTP probes;
- parse the rollback manifest once per restore verification;
- prune old local receipts/completed markers/last-good copies with strict path
  and symlink checks so long-running tablets do not accumulate unbounded state.

All bundle hashes, 17-output exactness, transaction rollback, fail-closed
collection gates, rclone retries, and receipt semantics remain owned by the
existing hardened runtime.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import urllib.request

import tablet_gdrive_sync as core
import tablet_gdrive_sync_hardening as hard
import tablet_gdrive_sync_hardening_contextual as contextual

PATCH_ID = 262
REMOTE_MANIFEST_MAX_AGE = "8d"
HEALTH_TIMEOUT_SECONDS = 1.25
RECEIPT_KEEP = 64
COMPLETED_KEEP = 128
LAST_GOOD_KEEP = 8


def bounded_list_manifests(remote: str, remote_root: str) -> list[str]:
    """List only manifests that could still pass the 7-day freshness gate."""
    target = f"{remote}:{remote_root}/to_tablet"
    out = core.run(
        [
            "rclone", "lsf", target,
            "--files-only", "--include", "manifest_*.json",
            "--max-age", REMOTE_MANIFEST_MAX_AGE,
        ],
        capture=True,
        timeout=30,
    )
    names = [
        line.strip()
        for line in out.splitlines()
        if core.MANIFEST_RE.fullmatch(line.strip())
    ]
    return sorted(set(names))


def fast_health_ok() -> bool:
    """Probe the universal runtime health endpoint once with bounded payload."""
    try:
        request = urllib.request.Request(
            "http://127.0.0.1:8765/api/health",
            headers={"Accept": "application/json", "Connection": "close"},
        )
        with urllib.request.urlopen(request, timeout=HEALTH_TIMEOUT_SECONDS) as resp:
            if not (200 <= int(getattr(resp, "status", 200)) < 300):
                return False
            raw = resp.read(64 * 1024 + 1)
        if len(raw) > 64 * 1024:
            return False
        payload = json.loads(raw.decode("utf-8"))
        return isinstance(payload, dict) and payload.get("ok") is True
    except Exception:
        return False


def optimized_hardened_restore_backup(repo: Path, backup: Path) -> None:
    """Verify once, restore once, and reuse one parsed backup manifest."""
    hard.verify_backup(backup)
    manifest_path = backup / "backup_manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = data["sha256"]
    hard._ORIGINAL_RESTORE_BACKUP(repo, backup)
    for name in core.OUTPUTS:
        if core.sha256(repo / name) != hashes[name]:
            raise RuntimeError(f"rollback readback mismatch: {name}")


def _safe_age_key(path: Path) -> tuple[int, str]:
    try:
        return (path.stat().st_mtime_ns, path.name)
    except OSError:
        return (0, path.name)


def _remove_regular(path: Path) -> None:
    if path.is_symlink():
        return
    try:
        if path.is_file():
            path.unlink()
    except FileNotFoundError:
        pass


def _prune_regular_files(folder: Path, pattern: str, keep: int) -> int:
    if not folder.exists() or folder.is_symlink() or not folder.is_dir():
        return 0
    files = [p for p in folder.glob(pattern) if p.is_file() and not p.is_symlink()]
    files.sort(key=_safe_age_key, reverse=True)
    removed = 0
    for path in files[max(0, keep):]:
        _remove_regular(path)
        removed += 1
    return removed


def _inflight_backup(state: Path) -> Path | None:
    marker = hard.transaction_path(state)
    try:
        if marker.is_symlink() or not marker.is_file():
            return None
        data = json.loads(marker.read_text(encoding="utf-8"))
        raw = data.get("backup")
        if not isinstance(raw, str) or not raw:
            return None
        backup = Path(raw).expanduser().resolve()
        root = (state / "last_good").resolve()
        return backup if hard._is_within(backup, root) else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _prune_last_good(state: Path, keep: int = LAST_GOOD_KEEP) -> int:
    root = state / "last_good"
    if not root.exists() or root.is_symlink() or not root.is_dir():
        return 0
    preserve = _inflight_backup(state)
    rows = [p for p in root.iterdir() if p.is_dir() and not p.is_symlink()]
    rows.sort(key=_safe_age_key, reverse=True)
    retained = 0
    removed = 0
    root_resolved = root.resolve()
    for path in rows:
        resolved = path.resolve()
        if not hard._is_within(resolved, root_resolved):
            continue
        if preserve is not None and resolved == preserve:
            continue
        if retained < max(0, keep):
            retained += 1
            continue
        shutil.rmtree(path)
        removed += 1
    return removed


def prune_state(state: Path) -> dict:
    """Bound local sync history without touching any active transaction."""
    state = state.expanduser().resolve()
    state.mkdir(parents=True, exist_ok=True)
    receipts = state / "receipts"

    # Keep the newest receipt JSONs.  A .sent marker is only useful while its
    # receipt exists, so remove orphan markers after the JSON retention pass.
    removed_receipts = _prune_regular_files(
        receipts, "TABLET_SYNC_RECEIPT_*.json", RECEIPT_KEEP
    )
    removed_sent = 0
    if receipts.exists() and receipts.is_dir() and not receipts.is_symlink():
        for sent in receipts.glob("TABLET_SYNC_RECEIPT_*.json.sent"):
            if sent.is_symlink() or not sent.is_file():
                continue
            receipt = sent.with_suffix("")
            if not receipt.exists():
                _remove_regular(sent)
                removed_sent += 1

    removed_completed = _prune_regular_files(
        state / "completed", "*", COMPLETED_KEEP
    )
    removed_last_good = _prune_last_good(state)
    return {
        "patch": PATCH_ID,
        "receipts": removed_receipts,
        "sent_markers": removed_sent,
        "completed": removed_completed,
        "last_good": removed_last_good,
    }


def apply_runtime_patch() -> None:
    core.list_manifests = bounded_list_manifests
    core.health_ok = fast_health_ok
    hard.hardened_restore_backup = optimized_hardened_restore_backup


def main() -> int:
    apply_runtime_patch()
    rc = contextual.main()
    if rc == 0:
        try:
            prune_state(hard.state_root())
        except (OSError, ValueError, RuntimeError):
            # Retention is a performance aid only.  Never convert a verified
            # sync into failure because optional cleanup could not run.
            pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
