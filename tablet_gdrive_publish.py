#!/usr/bin/env python3
"""Build and optionally upload the exact verified 17-JSON tablet Drive package.

The manifest is uploaded last and therefore acts as the remote commit marker. A
bundle can never become eligible for the tablet merely because a partial upload
exists. Existing remote object names are never overwritten.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile

import tablet_collection_publish as publisher
import tablet_gdrive_sync as sync

RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,120}$")
REMOTE_RETENTION_DAYS = 14
REMOTE_PACKAGE_MIN_KEEP = 4
REMOTE_PACKAGE_MAX_KEEP = 40
REMOTE_RECEIPT_MIN_KEEP = 16
REMOTE_RECEIPT_MAX_KEEP = 64
_REMOTE_MANIFEST_RE = re.compile(
    r"^manifest_(?P<stamp>\d{8}T\d{6}Z)_(?P<run>[A-Za-z0-9._-]{8,120})\.json$"
)
_REMOTE_BUNDLE_RE = re.compile(
    r"^TCG_VERIFIED_(?P<stamp>\d{8}T\d{6}Z)_(?P<run>[A-Za-z0-9._-]{8,120})\.tar\.gz$"
)
_REMOTE_RECEIPT_RE = re.compile(
    r"^TABLET_SYNC_RECEIPT_(?P<run>[A-Za-z0-9._-]{8,120})\.json$"
)


def run(args, *, cwd=None, capture=False, timeout=120):
    cp = subprocess.run(
        args, cwd=cwd, text=True, check=True, timeout=timeout,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return cp.stdout.strip() if capture else ""


def trusted_main_sha(root: Path) -> str:
    origin = run(["git", "remote", "get-url", "origin"], cwd=root, capture=True)
    if origin.rstrip("/") not in {
        "https://github.com/wlghks24/-tcg-grader",
        "https://github.com/wlghks24/-tcg-grader.git",
        "git@github.com:wlghks24/-tcg-grader.git",
    }:
        raise ValueError("untrusted git origin")
    run(["git", "fetch", "origin", "main"], cwd=root, timeout=120)
    head = run(["git", "rev-parse", "HEAD"], cwd=root, capture=True)
    upstream = run(["git", "rev-parse", "FETCH_HEAD"], cwd=root, capture=True)
    if not re.fullmatch(r"[0-9a-f]{40}", head) or head != upstream:
        raise ValueError("package build requires exact latest origin/main")
    return head


def validate_source_files(root: Path) -> list[dict]:
    files = []
    for name in sync.OUTPUTS:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"missing/non-regular public output: {name}")
        size = path.stat().st_size
        if size < 0 or size > sync.MAX_FILE_SIZE:
            raise ValueError(f"invalid output size: {name}")
        json.loads(path.read_text(encoding="utf-8"))
        files.append({"name": name, "size": size, "sha256": sync.sha256(path)})
    return files


def safe_remote_root(value: str) -> str:
    value = value.strip().strip("/")
    if not value or any(c in value for c in "\r\n\\"):
        raise ValueError("invalid remote root")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("invalid remote root")
    return "/".join(parts)


def _tar_exact(root: Path, bundle: Path) -> None:
    # Normalize archive metadata so identical source bytes produce stable tar
    # members. The gzip wrapper may still carry a stream timestamp; integrity is
    # always established by the manifest hash rather than filename assumptions.
    with tarfile.open(bundle, "w:gz", format=tarfile.PAX_FORMAT) as tf:
        for name in sync.OUTPUTS:
            raw = (root / name).read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            info.mode = 0o600
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            tf.addfile(info, io.BytesIO(raw))


def build_package(root: Path, output_dir: Path, *, run_id: str | None = None,
                  main_sha: str | None = None, run_gates: bool = True) -> tuple[Path, Path, dict]:
    root_input = Path(root).expanduser()
    output_input = Path(output_dir).expanduser()
    if root_input.is_symlink():
        raise ValueError("repository root symlink is not allowed")
    if output_input.is_symlink():
        raise ValueError("output directory symlink is not allowed")
    root = root_input.resolve()
    output_dir = output_input.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if run_gates:
        publisher.gates(root)
    files = validate_source_files(root)
    main_sha = main_sha or trusted_main_sha(root)
    if not re.fullmatch(r"[0-9a-f]{40}", str(main_sha)):
        raise ValueError("invalid main sha")

    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    run_id = run_id or f"gpt-{stamp}-{secrets.token_hex(6)}"
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("invalid run_id")

    bundle_name = f"TCG_VERIFIED_{stamp}_{run_id}.tar.gz"
    manifest_name = f"manifest_{stamp}_{run_id}.json"
    bundle = output_dir / bundle_name
    manifest_path = output_dir / manifest_name
    if bundle.exists() or manifest_path.exists():
        raise FileExistsError("package destination already exists")

    _tar_exact(root, bundle)
    if bundle.stat().st_size <= 0 or bundle.stat().st_size > sync.MAX_BUNDLE_SIZE:
        bundle.unlink(missing_ok=True)
        raise ValueError("invalid bundle size")
    manifest = {
        "schema_version": sync.SCHEMA,
        "repository": sync.REPO,
        "source": "chatgpt_automation",
        "run_id": run_id,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "main_sha": main_sha,
        "bundle": {
            "name": bundle.name,
            "size": bundle.stat().st_size,
            "sha256": sync.sha256(bundle),
        },
        "files": files,
    }
    sync.atomic_write_json(manifest_path, manifest)

    # Use the receiver itself as the final format oracle before anything leaves
    # the machine. This prevents producer/consumer schema drift.
    loaded = sync.load_manifest(manifest_path)
    with tempfile.TemporaryDirectory(prefix="tcg-drive-publish-verify-") as td:
        stage = Path(td)
        sync.extract_bundle(bundle, stage, loaded)
        for item in files:
            path = stage / item["name"]
            if sync.sha256(path) != item["sha256"]:
                raise ValueError(f"producer self-check hash mismatch: {item['name']}")
    return bundle, manifest_path, manifest


def _remote_exists(remote: str, remote_root: str, name: str) -> bool:
    parent = f"{remote}:{remote_root}/to_tablet"
    out = run(
        ["rclone", "lsf", parent, "--files-only", "--include", name],
        capture=True, timeout=45,
    )
    return any(line.strip() == name for line in out.splitlines())


def _upload_one(remote: str, local: Path, remote_root: str) -> None:
    run([
        "rclone", "copyto", str(local), f"{remote}:{remote_root}/to_tablet/{local.name}",
        "--immutable", "--retries", "2", "--low-level-retries", "2",
        "--timeout", "20s", "--contimeout", "10s",
    ], timeout=120)


def _parse_package_name(name: str) -> tuple[dt.datetime, str] | None:
    match = _REMOTE_MANIFEST_RE.fullmatch(name) or _REMOTE_BUNDLE_RE.fullmatch(name)
    if not match:
        return None
    try:
        stamp = dt.datetime.strptime(match.group("stamp"), "%Y%m%dT%H%M%SZ").replace(
            tzinfo=dt.timezone.utc
        )
    except ValueError:
        return None
    return stamp, match.group("run")


def _package_key(name: str) -> tuple[str, str] | None:
    parsed = _parse_package_name(name)
    if parsed is None:
        return None
    stamp, run_id = parsed
    return stamp.strftime("%Y%m%dT%H%M%SZ"), run_id


def _safe_remote_rows(remote: str, remote_root: str, subdir: str) -> list[dict]:
    if subdir not in {"to_tablet", "receipts"}:
        raise ValueError("unsupported retention subdir")
    out = run(
        [
            "rclone", "lsjson", f"{remote}:{remote_root}/{subdir}",
            "--files-only", "--no-mimetype",
        ],
        capture=True,
        timeout=60,
    )
    rows = json.loads(out or "[]")
    if not isinstance(rows, list):
        raise ValueError("invalid rclone lsjson response")
    safe_rows = []
    for row in rows:
        if not isinstance(row, dict) or row.get("IsDir") is True:
            continue
        name = row.get("Path") or row.get("Name")
        if not isinstance(name, str) or not name or "/" in name or "\\" in name or name in {".", ".."}:
            continue
        safe_rows.append({"name": name, "mod_time": row.get("ModTime")})
    return safe_rows


def _delete_remote_retention_file(remote: str, remote_root: str, subdir: str, name: str) -> None:
    if subdir == "to_tablet":
        if not (_REMOTE_MANIFEST_RE.fullmatch(name) or _REMOTE_BUNDLE_RE.fullmatch(name)):
            raise ValueError("refusing to delete unknown to_tablet object")
    elif subdir == "receipts":
        if not _REMOTE_RECEIPT_RE.fullmatch(name):
            raise ValueError("refusing to delete unknown receipt object")
    else:
        raise ValueError("unsupported retention subdir")
    # Google Drive's rclone backend sends deletes to Trash by default. These are
    # exact TCG-generated names, so permanently delete just these individual
    # objects; never run a Drive-wide trash cleanup that could affect user files.
    run(
        [
            "rclone", "deletefile", f"{remote}:{remote_root}/{subdir}/{name}",
            "--drive-use-trash=false",
            "--retries", "2", "--low-level-retries", "2",
            "--timeout", "20s", "--contimeout", "10s",
        ],
        timeout=90,
    )


def _receipt_modtime(value) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _normalize_protected_package_keys(values) -> set[tuple[str, str]]:
    protected: set[tuple[str, str]] = set()
    for value in values or ():
        if not isinstance(value, tuple) or len(value) != 2:
            raise ValueError("invalid protected package key")
        stamp, run_id = value
        if (
            not isinstance(stamp, str)
            or not re.fullmatch(r"\d{8}T\d{6}Z", stamp)
            or not isinstance(run_id, str)
            or not RUN_ID_RE.fullmatch(run_id)
        ):
            raise ValueError("invalid protected package key")
        try:
            dt.datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
        except ValueError as exc:
            raise ValueError("invalid protected package timestamp") from exc
        protected.add((stamp, run_id))
    return protected


def prune_remote_drive(remote: str = sync.DEFAULT_REMOTE,
                       remote_root: str = sync.DEFAULT_REMOTE_ROOT,
                       *,
                       now: dt.datetime | None = None,
                       protected_keys=None) -> dict:
    """Bound only TCG-managed Drive objects; unknown user files are never deleted."""
    remote = sync.safe_remote_name(remote)
    remote_root = safe_remote_root(remote_root)
    explicit_protected = _normalize_protected_package_keys(protected_keys)
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("retention clock must be timezone-aware")
    now = now.astimezone(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=REMOTE_RETENTION_DAYS)

    package_rows = []
    for row in _safe_remote_rows(remote, remote_root, "to_tablet"):
        parsed = _parse_package_name(row["name"])
        if parsed is None:
            continue
        stamp, run_id = parsed
        package_rows.append({
            "name": row["name"],
            "stamp": stamp,
            "key": (stamp.strftime("%Y%m%dT%H%M%SZ"), run_id),
        })

    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in package_rows:
        grouped.setdefault(row["key"], []).append(row)
    keys = sorted(
        grouped,
        key=lambda key: max(item["stamp"] for item in grouped[key]),
        reverse=True,
    )
    complete_keys = [
        key for key in keys
        if any(_REMOTE_MANIFEST_RE.fullmatch(item["name"]) for item in grouped[key])
        and any(_REMOTE_BUNDLE_RE.fullmatch(item["name"]) for item in grouped[key])
    ]
    complete_rank = {key: index for index, key in enumerate(complete_keys)}
    protected = set(complete_keys[:REMOTE_PACKAGE_MIN_KEEP]) | explicit_protected

    deleted_packages = 0
    deleted_complete_sets = 0
    deleted_incomplete_groups = 0
    for key in keys:
        rows = grouped[key]
        stamp = max(item["stamp"] for item in rows)
        is_complete = key in complete_rank
        beyond_cap = is_complete and complete_rank[key] >= REMOTE_PACKAGE_MAX_KEEP
        expired = stamp < cutoff
        if key in protected or not (expired or beyond_cap):
            continue

        # Manifest is the remote commit marker. Delete it before its bundle so a
        # mid-cleanup failure can only leave a harmless bundle orphan, never a
        # manifest that points at a deleted bundle.
        ordered_rows = sorted(
            rows,
            key=lambda item: 0 if _REMOTE_MANIFEST_RE.fullmatch(item["name"]) else 1,
        )
        for item in ordered_rows:
            _delete_remote_retention_file(remote, remote_root, "to_tablet", item["name"])
            deleted_packages += 1
        if is_complete:
            deleted_complete_sets += 1
        else:
            deleted_incomplete_groups += 1

    receipt_rows = []
    for row in _safe_remote_rows(remote, remote_root, "receipts"):
        if not _REMOTE_RECEIPT_RE.fullmatch(row["name"]):
            continue
        mod_time = _receipt_modtime(row["mod_time"])
        receipt_rows.append({"name": row["name"], "mod_time": mod_time})
    receipt_rows.sort(
        key=lambda row: row["mod_time"] or dt.datetime.max.replace(tzinfo=dt.timezone.utc),
        reverse=True,
    )
    deleted_receipts = 0
    for index, row in enumerate(receipt_rows):
        if index < REMOTE_RECEIPT_MIN_KEEP:
            continue
        expired = row["mod_time"] is not None and row["mod_time"] < cutoff
        beyond_cap = index >= REMOTE_RECEIPT_MAX_KEEP
        if not (expired or beyond_cap):
            continue
        _delete_remote_retention_file(remote, remote_root, "receipts", row["name"])
        deleted_receipts += 1

    return {
        "status": "DRIVE_RETENTION_OK",
        "retention_days": REMOTE_RETENTION_DAYS,
        "package_min_keep": REMOTE_PACKAGE_MIN_KEEP,
        "package_max_keep": REMOTE_PACKAGE_MAX_KEEP,
        "receipt_min_keep": REMOTE_RECEIPT_MIN_KEEP,
        "receipt_max_keep": REMOTE_RECEIPT_MAX_KEEP,
        "deleted_package_objects": deleted_packages,
        "deleted_complete_package_sets": deleted_complete_sets,
        "deleted_incomplete_package_groups": deleted_incomplete_groups,
        "deleted_receipts": deleted_receipts,
    }


def upload_package(bundle: Path, manifest_path: Path, manifest: dict, *,
                   remote: str = sync.DEFAULT_REMOTE,
                   remote_root: str = sync.DEFAULT_REMOTE_ROOT) -> dict:
    remote = sync.safe_remote_name(remote)
    remote_root = safe_remote_root(remote_root)
    expected = sync.load_manifest(manifest_path)
    if expected != manifest:
        raise ValueError("manifest changed after package build")

    manifest_key = _package_key(manifest_path.name)
    bundle_key = _package_key(bundle.name)
    if manifest_key is None or bundle_key is None or manifest_key != bundle_key:
        raise ValueError("package manifest/bundle filename key mismatch")
    if manifest_key[1] != manifest.get("run_id"):
        raise ValueError("package filename/run_id mismatch")

    for name in (bundle.name, manifest_path.name):
        if _remote_exists(remote, remote_root, name):
            raise FileExistsError(f"remote object already exists: {name}")

    # Bundle first, manifest last. The receiver only discovers manifest_*.json,
    # so an interrupted bundle upload cannot be applied.
    _upload_one(remote, bundle, remote_root)
    _upload_one(remote, manifest_path, remote_root)

    with tempfile.TemporaryDirectory(prefix="tcg-drive-readback-") as td:
        td_path = Path(td)
        read_manifest = td_path / manifest_path.name
        read_bundle = td_path / bundle.name
        sync.rclone_copyto(remote, f"{remote_root}/to_tablet/{manifest_path.name}", read_manifest)
        loaded = sync.load_manifest(read_manifest)
        sync.rclone_copyto(remote, f"{remote_root}/to_tablet/{bundle.name}", read_bundle)
        if read_bundle.stat().st_size != loaded["bundle"]["size"]:
            raise ValueError("Drive read-back bundle size mismatch")
        if sync.sha256(read_bundle) != loaded["bundle"]["sha256"]:
            raise ValueError("Drive read-back bundle hash mismatch")
        stage = td_path / "stage"
        stage.mkdir()
        sync.extract_bundle(read_bundle, stage, loaded)

    try:
        retention = prune_remote_drive(
            remote, remote_root, protected_keys={manifest_key}
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # The just-uploaded package passed full Drive read-back. A cleanup outage
        # is reported separately so retrying does not create duplicate objects.
        return {
            "status": "DRIVE_RETENTION_WARNING",
            "error_type": type(exc).__name__,
            "message": str(exc)[:300],
        }

    # Defensive postcondition: successful retention must never remove the package
    # that triggered it. If it did, do not claim a verified Drive upload.
    for name in (bundle.name, manifest_path.name):
        if not _remote_exists(remote, remote_root, name):
            raise RuntimeError(f"verified Drive package disappeared after retention: {name}")
    return retention


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--run-id")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--remote", default=os.environ.get("TCG_GDRIVE_REMOTE", sync.DEFAULT_REMOTE))
    parser.add_argument("--remote-root", default=os.environ.get("TCG_GDRIVE_ROOT", sync.DEFAULT_REMOTE_ROOT))
    args = parser.parse_args()
    root = Path(args.root)
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else root / ".tcg_drive_outbox"
    try:
        bundle, manifest_path, manifest = build_package(root, output_dir, run_id=args.run_id)
        print(json.dumps({
            "status": "PACKAGE_VERIFIED",
            "run_id": manifest["run_id"],
            "main_sha": manifest["main_sha"],
            "bundle": str(bundle),
            "manifest": str(manifest_path),
            "file_count": len(manifest["files"]),
        }, ensure_ascii=False))
        if args.upload:
            retention = upload_package(
                bundle, manifest_path, manifest,
                remote=args.remote, remote_root=args.remote_root,
            )
            print(json.dumps({
                "status": "DRIVE_UPLOAD_VERIFIED",
                "run_id": manifest["run_id"],
                "retention": retention,
            }, ensure_ascii=False))
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"검증/전송 중단: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
