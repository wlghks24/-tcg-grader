#!/usr/bin/env python3
"""v262 performance/reliability layer for the tablet Google Drive sync.

This module deliberately wraps the verified contextual/hardening stack instead
of weakening any gate.  It only removes avoidable local/remote work and carries
successor-safe receipt completion hardening:
- bound remote manifest discovery to the same freshness horizon the manifest
  validator already accepts;
- use the universal /api/health endpoint once per probe instead of two serial
  HTTP probes;
- parse the rollback manifest once per restore verification;
- prune old local receipts/completed markers/last-good copies with strict path
  and symlink checks so long-running tablets do not accumulate unbounded state;
- pin Android code updates to the exact main SHA carried by the verified Drive
  manifest, eliminating the producer-to-tablet race when main advances later;
- never mark a sync completed until its TABLET_SYNC_OK receipt is remotely
  uploaded and locally marked sent; pending receipt delivery fails closed.

All bundle hashes, 17-output exactness, transaction rollback, fail-closed
collection gates, rclone retries, and receipt trust remain owned by the
existing hardened runtime.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

import tablet_gdrive_sync as core
import tablet_gdrive_sync_hardening as hard
import tablet_gdrive_sync_hardening_contextual as contextual

PATCH_ID = 362
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


def pinned_ensure_exact_main(repo: Path, expected_sha: str) -> None:
    """Move only to the manifest-pinned official main commit, never a later tip."""
    if not (repo / ".git").exists():
        raise ValueError("TCG repository not found")
    origin = core.run(["git", "remote", "get-url", "origin"], cwd=repo, capture=True)
    ok = origin.rstrip("/") in {
        "https://github.com/wlghks24/-tcg-grader",
        "https://github.com/wlghks24/-tcg-grader.git",
        "git@github.com:wlghks24/-tcg-grader.git",
    }
    if not ok:
        raise ValueError("untrusted git origin")
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("invalid expected main sha")

    head = core.run(["git", "rev-parse", "HEAD"], cwd=repo, capture=True)
    if head == expected_sha:
        return

    env = os.environ.copy()
    env["TCG_UPDATE_ONLY"] = "1"
    env["TCG_TARGET_MAIN_SHA"] = expected_sha
    cp = subprocess.run(
        ["bash", "ANDROID_UPDATE_AND_START.sh"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        timeout=300,
    )
    if cp.returncode != 0:
        raise RuntimeError("tablet code update failed:\n" + cp.stdout[-4000:])
    head = core.run(["git", "rev-parse", "HEAD"], cwd=repo, capture=True)
    if head != expected_sha:
        raise ValueError(f"manifest/main mismatch: local={head} manifest={expected_sha}")


def fast_health_ok() -> bool:
    """Probe one bounded endpoint and verify the expected TCG service identity."""
    payload = core._read_health_json("/api/health", timeout=HEALTH_TIMEOUT_SECONDS)
    return bool(
        isinstance(payload, dict)
        and payload.get("ok") is True
        and payload.get("service") == core.EXPECTED_HEALTH_SERVICE
    )


def optimized_hardened_restore_backup(repo: Path, backup: Path) -> None:
    """Verify once, restore once, and reuse the verified hash map."""
    hashes = hard.verify_backup(backup)
    hard._ORIGINAL_RESTORE_BACKUP(repo, backup)
    for name in core.OUTPUTS:
        if core.sha256(repo / name) != hashes[name]:
            raise RuntimeError(f"rollback readback mismatch: {name}")


def _receipt_paths(state: Path, run_id: str) -> tuple[Path, Path]:
    receipt = state / "receipts" / f"TABLET_SYNC_RECEIPT_{run_id}.json"
    return receipt, receipt.with_suffix(receipt.suffix + ".sent")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise RuntimeError(f"unsafe state marker path: {path.name}")
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _mark_receipt_sent(receipt: Path) -> Path:
    sent = receipt.with_suffix(receipt.suffix + ".sent")
    _atomic_write_text(sent, dt.datetime.now(dt.timezone.utc).isoformat() + "\n")
    return sent


def strict_flush_pending_receipts(remote: str, remote_root: str, state: Path) -> None:
    """Deliver every pending receipt or propagate the delivery failure.

    Receipt delivery is part of the cross-device verification boundary.  A failed
    upload must not be hidden behind a later "no new manifest" or "already applied"
    success message.
    """
    folder = state / "receipts"
    if not folder.exists():
        return
    if folder.is_symlink() or not folder.is_dir():
        raise RuntimeError("receipt state directory is unsafe")
    for receipt in sorted(folder.glob("TABLET_SYNC_RECEIPT_*.json")):
        if receipt.is_symlink() or not receipt.is_file():
            raise RuntimeError(f"unsafe receipt path: {receipt.name}")
        sent = receipt.with_suffix(receipt.suffix + ".sent")
        if sent.exists():
            if sent.is_symlink() or not sent.is_file():
                raise RuntimeError(f"unsafe sent marker: {sent.name}")
            continue
        core.rclone_upload(remote, receipt, f"{remote_root}/receipts/{receipt.name}")
        _mark_receipt_sent(receipt)


def _require_secured_completed_receipt(state: Path, manifest: dict) -> None:
    """Reject legacy/incomplete completed markers without exact receipt evidence."""
    receipt, sent = _receipt_paths(state, str(manifest["run_id"]))
    if receipt.is_symlink() or not receipt.is_file():
        raise RuntimeError("completed sync is missing its local TABLET_SYNC_OK receipt")
    if sent.is_symlink() or not sent.is_file():
        raise RuntimeError("completed sync receipt is not confirmed sent")
    raw = receipt.read_bytes()
    if len(raw) > core.MAX_MANIFEST_SIZE:
        raise RuntimeError("completed sync receipt is too large")
    payload = core.strict_json_loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("completed sync receipt is invalid")
    expected = {
        "schema_version": core.SCHEMA,
        "repository": core.REPO,
        "run_id": manifest["run_id"],
        "manifest_name": manifest["_manifest_name"],
        "main_sha": manifest["main_sha"],
        "bundle_sha256": manifest["bundle"]["sha256"],
        "status": "TABLET_SYNC_OK",
    }
    mismatched = [key for key, value in expected.items() if payload.get(key) != value]
    if mismatched:
        raise RuntimeError("completed sync receipt evidence mismatch: " + ",".join(mismatched))
    if payload.get("runtime_health") is not True or payload.get("runtime_main_sha_verified") is not True:
        raise RuntimeError("completed sync receipt lacks verified runtime health/main evidence")


def _finalize_success_delivery(
    remote: str,
    remote_root: str,
    completed: Path,
    manifest_name: str,
    receipt: Path,
) -> None:
    """Commit completion only after remote receipt delivery succeeds."""
    core.rclone_upload(remote, receipt, f"{remote_root}/receipts/{receipt.name}")
    _mark_receipt_sent(receipt)
    _atomic_write_text(completed, manifest_name + "\n")


def sync_once_receipt_fail_closed(repo: Path, remote: str, remote_root: str) -> int:
    """Core sync with receipt-secured completion ordering.

    This mirrors the verified core transaction while changing only the receipt
    boundary: pending receipts are mandatory, and a completed marker is written
    strictly after remote TABLET_SYNC_OK receipt delivery.
    """
    remote = core.safe_remote_name(remote)
    remote_root = core.safe_remote_root(remote_root)
    state = Path.home() / ".local" / "state" / "tcg-grader" / "gdrive-sync"
    state.mkdir(parents=True, exist_ok=True)
    lock = state / "sync.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        print("[OK] Google Drive 동기화가 이미 실행 중입니다.")
        return 0
    try:
        strict_flush_pending_receipts(remote, remote_root, state)
        manifests = core.list_manifests(remote, remote_root)
        if not manifests:
            print("[OK] 새 GPT→태블릿 manifest가 없습니다.")
            return 0
        manifest_name = manifests[-1]
        temp = Path(tempfile.mkdtemp(prefix="tcg-gdrive-sync-", dir=state))
        try:
            manifest_path = temp / manifest_name
            core.rclone_copyto(remote, f"{remote_root}/to_tablet/{manifest_name}", manifest_path)
            manifest = core.load_manifest(manifest_path)
            manifest["_manifest_name"] = manifest_name
            expected_manifest = rf"manifest_\d{{8}}T\d{{6}}Z_{re.escape(manifest['run_id'])}\.json"
            if not re.fullmatch(expected_manifest, manifest_name):
                raise ValueError("manifest filename/run_id mismatch")
            completed = state / "completed" / manifest["run_id"]
            if completed.is_symlink():
                raise RuntimeError("completed marker is unsafe")
            if completed.exists():
                _require_secured_completed_receipt(state, manifest)
                print(f"[OK] 이미 반영·receipt 확인된 run_id입니다: {manifest['run_id']}")
                return 0
            core.ensure_exact_main(repo, manifest["main_sha"])

            bundle_path = temp / manifest["bundle"]["name"]
            core.rclone_copyto(remote, f"{remote_root}/to_tablet/{manifest['bundle']['name']}", bundle_path)
            if bundle_path.stat().st_size != manifest["bundle"]["size"]:
                raise ValueError("bundle size mismatch")
            if core.sha256(bundle_path) != manifest["bundle"]["sha256"]:
                raise ValueError("bundle sha256 mismatch")

            stage = temp / "stage"
            stage.mkdir()
            core.extract_bundle(bundle_path, stage, manifest)
            core.run_project_gates(repo, stage)

            backup = state / "last_good" / manifest["run_id"]
            core.backup_current(repo, backup)
            was_healthy = core.health_ok()
            if was_healthy:
                core.stop_server(repo)
            try:
                core.apply_stage(repo, stage)
                for item in manifest["files"]:
                    path = repo / item["name"]
                    if path.stat().st_size != item["size"] or core.sha256(path) != item["sha256"]:
                        raise RuntimeError(f"post-apply readback mismatch: {item['name']}")
                core.start_server(repo, state)
                if not core.health_ok():
                    raise RuntimeError("post-apply runtime health failed")
                if not core.runtime_matches_main(manifest["main_sha"]):
                    raise RuntimeError("post-apply runtime build SHA mismatch")
            except Exception as exc:
                core.restore_backup(repo, backup)
                try:
                    core.start_server(repo, state)
                except Exception:
                    pass
                receipt = core.write_receipt(
                    state,
                    manifest,
                    "FAILED_ROLLED_BACK",
                    {"error": f"{type(exc).__name__}: {exc}", "runtime_health": core.health_ok()},
                )
                try:
                    core.rclone_upload(remote, receipt, f"{remote_root}/receipts/{receipt.name}")
                    _mark_receipt_sent(receipt)
                except Exception as receipt_exc:
                    print(
                        f"[DEFERRED] rollback receipt upload pending: "
                        f"{type(receipt_exc).__name__}: {receipt_exc}",
                        file=sys.stderr,
                    )
                raise

            receipt = core.write_receipt(
                state,
                manifest,
                "TABLET_SYNC_OK",
                {"runtime_health": True, "runtime_main_sha_verified": True, "file_count": len(core.OUTPUTS)},
            )
            _finalize_success_delivery(remote, remote_root, completed, manifest_name, receipt)
            print(f"[OK] GPT 검증자료 태블릿 반영·receipt 확인 완료: {manifest['run_id']}")
            return 0
        finally:
            shutil.rmtree(temp, ignore_errors=True)
    finally:
        shutil.rmtree(lock, ignore_errors=True)


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
        payload = marker.read_bytes()
        if len(payload) > 1_000_000:
            return None
        data = core.strict_json_loads(payload)
        if not isinstance(data, dict):
            return None
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
    core.ensure_exact_main = pinned_ensure_exact_main
    core.health_ok = fast_health_ok
    core.flush_pending_receipts = strict_flush_pending_receipts
    core.sync_once = sync_once_receipt_fail_closed
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
