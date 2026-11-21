#!/usr/bin/env python3
"""Verify a second Lenovo backup without installing, restoring or publishing.

Uses V1012's strict backup inventory, private-file SHA, and Git bundle checks.
Distinct filesystem != independently verified physical device or restore.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from execution import tablet_migration_preflight_v1012 as primary

DEFAULT_TRACKED = 30
DEFAULT_EXTRA = 5455


def _filesystem_id(path: Path) -> int:
    return path.stat().st_dev


def _same_bytes(left: Path, right: Path) -> bool:
    # Streaming SHA256; never print personal photos, learning data or secrets.
    return primary._digest(left) == primary._digest(right)


def inspect(root: Path, backup: Path, external_copy: Path, extra_dir: str, *,
            expected_tracked: int = DEFAULT_TRACKED,
            expected_extra: int = DEFAULT_EXTRA) -> dict:
    report = {
        "schema": "tcg-lenovo-second-copy-audit/v1",
        "status": "SECONDARY_COPY_HOLD",
        "backup_verified": False,
        "distinct_filesystem_copy_verified": False,
        "physical_offdevice_custody_verified": False,
        "quiesced_snapshot_verified": False,
        "restoration_test_verified": False,
        "current_protected_main_ci_verified": False,
        "code_release_approved": False,
        "physical_lenovo_runtime_verified": False,
        "install_allowed": False,
        "writes_or_updates_performed": False,
    }
    try:
        parts = primary._safe_name(extra_dir, top_level=True)
        root, backup, external_copy = Path(root), Path(backup), Path(external_copy)
        if (root.is_symlink() or backup.is_symlink() or external_copy.is_symlink()
                or not root.is_dir() or not backup.is_dir() or not external_copy.is_dir()):
            raise primary.Hold("unsafe_or_missing_backup_root")
        original = primary.inspect(root, backup, backup.joinpath(*parts),
                                   expected_tracked=expected_tracked,
                                   expected_extra=expected_extra)
        if not original["backup_verified"]:
            raise primary.Hold(original.get("hold_reason", "primary_backup_unverified"))
        report["backup_verified"] = True
        a, b, checkout = backup.resolve(), external_copy.resolve(), root.resolve()
        if (a == b or a in b.parents or b in a.parents
                or b == checkout or checkout in b.parents):
            raise primary.Hold("copy_not_separate_from_live_or_primary")
        if _filesystem_id(backup) == _filesystem_id(external_copy):
            raise primary.Hold("second_copy_on_same_filesystem")

        original_extra = backup.joinpath(*parts)
        copy_extra = external_copy.joinpath(*parts)
        tracked = primary._tracked_backup(external_copy, expected_tracked)
        extra = primary._extra_backup(copy_extra, expected_extra)
        disk_head = primary._git_value(root, "rev-parse", "HEAD")
        bundle = primary._bundle(external_copy, root, disk_head)

        # Independently valid copy must also match the original inventories.
        for name in ("SHA256SUMS", "operating-history.bundle.sha256",
                     "operating-history.bundle"):
            if not _same_bytes(
                primary._regular_child(backup, (name,)),
                primary._regular_child(external_copy, (name,)),
            ):
                raise primary.Hold("second_copy_control_file_differs")
        if not _same_bytes(
            primary._regular_child(original_extra, ("MANIFEST.json",)),
            primary._regular_child(copy_extra, ("MANIFEST.json",)),
        ):
            raise primary.Hold("second_copy_inventory_differs")

        report.update({
            "status": "SECONDARY_FILESYSTEM_COPY_VERIFIED_INSTALL_HOLD",
            "distinct_filesystem_copy_verified": True,
            "tracked_files_verified": tracked["files"],
            "private_files_verified": extra["files"],
            "git_bundle_verified": bundle["git_bundle_verified"],
            "copy_bytes_verified": tracked["bytes"] + extra["bytes"] + bundle["bytes"],
            "missing_install_gates": [
                "approved_protected_main_release",
                "quiesced_consistent_backup",
                "physical_offdevice_custody_and_restore_test",
                "tablet_runtime_preinstall_checks",
                "physical_lenovo_postinstall_readback",
            ],
        })
    except primary.Hold as exc:
        report["hold_reason"] = str(exc)
    except (OSError, ValueError, TypeError):
        report["hold_reason"] = "unreadable_or_invalid_second_copy"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lenovo 2차 백업 해시 검증, 읽기 전용")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--external-copy", type=Path, required=True)
    parser.add_argument("--extra-dir", required=True)
    # Production count is deliberately not overridable from command line.
    # Small fixtures may pass custom counts only to the Python inspect() API.
    parser.add_argument("--require-copy-verified", action="store_true")
    parser.add_argument("--require-install-ready", action="store_true",
                        help="설치 승인 불가. 항상 종료 코드 2")
    args = parser.parse_args(argv)
    result = inspect(args.root, args.backup, args.external_copy, args.extra_dir,
                     expected_tracked=DEFAULT_TRACKED,
                     expected_extra=DEFAULT_EXTRA)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.require_install_ready:
        return 2
    if args.require_copy_verified and not result["distinct_filesystem_copy_verified"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
