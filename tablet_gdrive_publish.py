#!/usr/bin/env python3
"""Build and optionally upload the exact verified 17-JSON tablet Drive package.

The manifest is uploaded last and therefore acts as the remote commit marker.  A
bundle can never become eligible for the tablet merely because a partial upload
exists.  Existing remote object names are never overwritten.
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
import tarfile
import tempfile

import tablet_collection_publish as publisher
import tablet_gdrive_sync as sync

RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,120}$")


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
    # members.  The gzip wrapper may still carry a stream timestamp; integrity is
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
    root = root.resolve()
    output_dir = output_dir.resolve()
    if output_dir.is_symlink():
        raise ValueError("output directory symlink is not allowed")
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


def upload_package(bundle: Path, manifest_path: Path, manifest: dict, *,
                   remote: str = sync.DEFAULT_REMOTE,
                   remote_root: str = sync.DEFAULT_REMOTE_ROOT) -> None:
    remote = sync.safe_remote_name(remote)
    remote_root = safe_remote_root(remote_root)
    expected = sync.load_manifest(manifest_path)
    if expected != manifest:
        raise ValueError("manifest changed after package build")
    for name in (bundle.name, manifest_path.name):
        if _remote_exists(remote, remote_root, name):
            raise FileExistsError(f"remote object already exists: {name}")

    # Bundle first, manifest last.  The receiver only discovers manifest_*.json,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--run-id")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--remote", default=os.environ.get("TCG_GDRIVE_REMOTE", sync.DEFAULT_REMOTE))
    parser.add_argument("--remote-root", default=os.environ.get("TCG_GDRIVE_ROOT", sync.DEFAULT_REMOTE_ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else root / ".tcg_drive_outbox"
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
            upload_package(bundle, manifest_path, manifest, remote=args.remote, remote_root=args.remote_root)
            print(json.dumps({"status": "DRIVE_UPLOAD_VERIFIED", "run_id": manifest["run_id"]}, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"검증/전송 중단: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
