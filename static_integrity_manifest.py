#!/usr/bin/env python3
"""Build/check the static-publish integrity manifest from the exact Git-tracked tree.

The normal runtime collector can create temporary JSON reports and can mutate tracked
learning/report files that are not part of the approved static publish set.  Those
objects must never become fixed-hash source-of-truth entries for a candidate commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import fault_injection_healing as healing
from safe_runtime import atomic_write_json, reject_nonstandard_json, unique_json_object

ROOT = Path(__file__).resolve().parent


def _git_tracked_paths(root: Path) -> set[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("git tracked-file inventory unavailable")
    return {
        raw.decode("utf-8")
        for raw in proc.stdout.split(b"\0")
        if raw
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=reject_nonstandard_json,
        object_pairs_hook=unique_json_object,
    )


def policy_paths(root: Path = ROOT) -> list[Path]:
    root = root.resolve()
    git_paths = _git_tracked_paths(root)
    return [
        path
        for path in healing.tracked_files(root)
        if path.relative_to(root).as_posix() in git_paths
    ]


def build_manifest(root: Path = ROOT, target: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    git_paths = _git_tracked_paths(root)
    files = {
        path.relative_to(root).as_posix(): {
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in policy_paths(root)
    }
    mutable_json = {
        name: contract
        for name, contract in healing._mutable_json_manifest(root).items()
        if name in git_paths
    }
    payload = {
        "version": 2,
        "engine": healing.ENGINE_VERSION,
        "generated_at": healing._utc_now(),
        "files": files,
        "mutable_json": mutable_json,
        "policy": {
            "generated_code_auto_applied": False,
            "code_corruption_auto_repaired": False,
            "verified_json_backup_auto_repair_allowed": True,
            "fault_injection_production_allowed": False,
            "mutable_runtime_json_validation": "strict-schema-without-fixed-hash",
        },
    }
    if target is not None:
        atomic_write_json(target, payload, suffix=".static-integrity.tmp")
    return payload


def check_manifest(root: Path = ROOT, target: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    target = target or root / "integrity_manifest.json"
    try:
        payload = _strict_json(target)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        return {"ok": False, "error": f"manifest:{type(exc).__name__}"}
    listed = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(listed, dict):
        return {"ok": False, "error": "manifest:files"}
    expected_paths = {path.relative_to(root).as_posix() for path in policy_paths(root)}
    listed_paths = set(listed)
    missing = sorted(expected_paths - listed_paths)
    extra = sorted(listed_paths - expected_paths)
    mismatched: list[str] = []
    for relative in sorted(expected_paths & listed_paths):
        path = root / relative
        row = listed.get(relative)
        if not isinstance(row, dict):
            mismatched.append(relative)
            continue
        try:
            if int(row.get("bytes", -1)) != path.stat().st_size or row.get("sha256") != _sha256(path):
                mismatched.append(relative)
        except (OSError, TypeError, ValueError, OverflowError):
            mismatched.append(relative)
    git_paths = _git_tracked_paths(root)
    expected_mutable = {
        name for name in healing._mutable_json_manifest(root)
        if name in git_paths
    }
    listed_mutable_raw = payload.get("mutable_json", {}) if isinstance(payload, dict) else {}
    listed_mutable = set(listed_mutable_raw) if isinstance(listed_mutable_raw, dict) else set()
    mutable_mismatch = sorted(expected_mutable ^ listed_mutable)
    ok = not missing and not extra and not mismatched and not mutable_mismatch
    return {
        "ok": ok,
        "tracked": len(expected_paths),
        "missing": missing[:50],
        "extra": extra[:50],
        "mismatched": mismatched[:50],
        "mutable_mismatch": mutable_mismatch[:50],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("manifest", nargs="?", default="integrity_manifest.json")
    args = parser.parse_args(argv)
    target = (ROOT / args.manifest).resolve()
    if ROOT.resolve() not in target.parents and target != ROOT.resolve():
        raise SystemExit("manifest path outside repository")
    result = build_manifest(ROOT, target) if args.write else check_manifest(ROOT, target)
    print(json.dumps(result if args.check else {"ok": True, "tracked": len(result["files"])}, ensure_ascii=False, indent=2))
    return 0 if (not args.check or result.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
