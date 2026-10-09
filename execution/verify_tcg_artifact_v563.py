#!/usr/bin/env python3
"""Offline fail-closed validator for GitHub's two-file verified TCG package ZIP.

Checks the actual tablet receiver contract before any device import. Does not
fetch from GitHub/Drive, modify the repository, start services, or claim a
physical tablet receipt. Requires only the Python standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import tablet_gdrive_sync as sync

MANIFEST_NAME = re.compile(r"manifest_\d{8}T\d{6}Z_[A-Za-z0-9._-]{8,120}\.json\Z")
BUNDLE_NAME = re.compile(r"TCG_VERIFIED_\d{8}T\d{6}Z_[A-Za-z0-9._-]{8,120}\.tar\.gz\Z")
MAX_ZIP_BYTES = sync.MAX_BUNDLE_SIZE + sync.MAX_MANIFEST_SIZE + 5_000_000


def _safe_member(member: zipfile.ZipInfo) -> bool:
    name = member.filename
    mode = (member.external_attr >> 16) & 0xFFFF
    return (
        isinstance(name, str) and bool(name)
        and name == Path(name).name and "/" not in name and "\\" not in name
        and not member.is_dir() and not (member.flag_bits & 0x1)
        and (not mode or stat.S_ISREG(mode) or (mode & 0o170000) == 0)
    )


def verify_artifact(artifact: Path | str, expected_main_sha: str | None = None) -> dict:
    artifact = Path(artifact).expanduser()
    if artifact.is_symlink() or not artifact.is_file():
        raise ValueError("artifact must be a regular local ZIP file")
    if artifact.stat().st_size <= 0 or artifact.stat().st_size > MAX_ZIP_BYTES:
        raise ValueError("artifact ZIP exceeds bounded size")
    if expected_main_sha is not None and not re.fullmatch(r"[0-9a-f]{40}", expected_main_sha):
        raise ValueError("expected main SHA must be exactly 40 lowercase hex characters")

    with zipfile.ZipFile(artifact) as archive:
        members = archive.infolist()
        if len(members) != 2 or any(not _safe_member(row) for row in members):
            raise ValueError("archive must contain exactly two safe regular files")
        names = [row.filename for row in members]
        if len(set(names)) != 2:
            raise ValueError("duplicate ZIP filenames are forbidden")
        manifests = [name for name in names if MANIFEST_NAME.fullmatch(name)]
        bundles = [name for name in names if BUNDLE_NAME.fullmatch(name)]
        if len(manifests) != 1 or len(bundles) != 1:
            raise ValueError("missing verified manifest/bundle pair")
        for row in members:
            cap = sync.MAX_MANIFEST_SIZE if row.filename == manifests[0] else sync.MAX_BUNDLE_SIZE
            if row.file_size <= 0 or row.file_size > cap:
                raise ValueError("oversized/empty ZIP member")
            if row.compress_size <= 0 or row.file_size > row.compress_size * 1000:
                raise ValueError("suspicious compressed file expansion")

        with tempfile.TemporaryDirectory(prefix="tcg-verified-zip-audit-") as tmp:
            root = Path(tmp)
            for row in members:
                target = root / row.filename
                with archive.open(row, "r") as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)

            manifest = sync.load_manifest(root / manifests[0])
            if manifest["bundle"]["name"] != bundles[0]:
                raise ValueError("manifest/bundle filename mismatch")
            if manifest["main_sha"] != expected_main_sha and expected_main_sha is not None:
                raise ValueError("package does not match requested exact main commit")

            bundle = root / bundles[0]
            if bundle.stat().st_size != manifest["bundle"]["size"]:
                raise ValueError("bundle size mismatch")
            if sync.sha256(bundle) != manifest["bundle"]["sha256"]:
                raise ValueError("bundle SHA-256 mismatch")
            stage = root / "verified"
            stage.mkdir()
            # The real tablet receiver verifies exact 17 output paths, member
            # types, uncompressed sizes, individual hashes and strict JSON.
            sync.extract_bundle(bundle, stage, manifest)
            return {
                "status": "PACKAGE_VERIFIED_OFFLINE",
                "repository": manifest["repository"],
                "main_sha": manifest["main_sha"],
                "run_id": manifest["run_id"],
                "created_at": manifest["created_at"],
                "file_count": len(sync.OUTPUTS),
                "bundle_sha256": manifest["bundle"]["sha256"],
                "device_imported": False,
                "external_links_verified_live": False,
            }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("artifact", type=Path, help="GitHub Actions tcg-gdrive-package ZIP")
    p.add_argument("--expected-main-sha", help="Reject a package from any other commit")
    args = p.parse_args(argv)
    try:
        result = verify_artifact(args.artifact, args.expected_main_sha)
    except (OSError, ValueError, EOFError, zipfile.BadZipFile,
            zipfile.LargeZipFile) as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "error_type": type(exc).__name__,
                          "message": str(exc)[:300]}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
