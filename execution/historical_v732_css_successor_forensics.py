#!/usr/bin/env python3
"""W701 historical V732 CSS-title cleanup: immutable original Git proof only.

No live collectors, runtime imports, network, tracked writes or installation.
This does not certify 100 V701–V800 releases or quality of current event data.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

MAIN = "6c78831bbb6e188717f86ef90243a836d2e0b67a"
BASE = "82f1220dc9137ef5a30f41ad5cbd9fb7e7335eae"
LANDING = "0a22abfe02cd8931227e63562d417795932063fd"
PATH = "social_event_candidates.json"
BEFORE_BLOB = "00ce8c41398bde6588171b1822e89a6c32fb8996"
AFTER_BLOB = "813f6d79a375bdee80fcd1959eed0989a1202920"
PROTECT = "sync_v376_successor_test_support.py"
PROTECT_MAIN_BLOB = "6b899d70c835253f8381ffb0e6fb8740a413951f"
SHA1 = re.compile(r"^[a-f0-9]{40}$")


def git(root: Path, *args: str) -> bytes:
    p = subprocess.run(["git", *args], cwd=root, capture_output=True,
                       check=False, timeout=60)
    if p.returncode:
        raise ValueError("historical_git_unavailable:" + (args[0] if args else "?"))
    return p.stdout


def git_blob(root: Path, commit: str, path: str, expected: str) -> bytes:
    if not SHA1.fullmatch(commit) or not SHA1.fullmatch(expected):
        raise ValueError("invalid_original_pin")
    blob = git(root, "rev-parse", "--verify", f"{commit}:{path}").decode("ascii").strip()
    if blob != expected:
        raise ValueError("original_source_blob_mismatch:" + path)
    raw = git(root, "show", f"{commit}:{path}")
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if actual != expected:
        raise ValueError("corrupt_original_git_object")
    return raw


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("duplicate_json_key")
        data[key] = value
    return data


def load(raw: bytes) -> dict[str, Any]:
    if len(raw) > 16_000_000:
        raise ValueError("event_evidence_budget")
    data = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError("nonfinite_source_evidence")))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("invalid_event_inventory")
    if any(not isinstance(item, dict) for item in data["items"]):
        raise ValueError("malformed_event_row")
    return data


def review(root: Path) -> dict[str, Any]:
    root = root.resolve()
    git(root, "merge-base", "--is-ancestor", LANDING, MAIN)
    git(root, "merge-base", "--is-ancestor", MAIN, "HEAD")
    before = load(git_blob(root, BASE, PATH, BEFORE_BLOB))
    after = load(git_blob(root, LANDING, PATH, AFTER_BLOB))
    # float 1.0 and int 1 are semantically equal in parsed historical JSON.
    other_before = {k: v for k, v in before.items() if k != "items"}
    other_after = {k: v for k, v in after.items() if k != "items"}
    if other_before != other_after:
        raise ValueError("unreviewed_event_metadata_change")
    remaining = list(after["items"])
    removed = []
    for old in before["items"]:
        try:
            at = remaining.index(old)
        except ValueError:
            removed.append(old)
        else:
            del remaining[at]
    if remaining:
        raise ValueError("unreviewed_event_additions_or_rewrites")
    if len(removed) != 9:
        raise ValueError("unexpected_css_cleanup_count")
    if any(not re.search(r"\.css-[a-z0-9]+\s*\{", str(row.get("title", "")), re.I)
           for row in removed):
        raise ValueError("non_css_event_removed")
    changed = sorted(git(root, "diff-tree", "--no-commit-id", "--name-only",
                         "-r", LANDING).decode("utf-8").splitlines())
    expected = sorted([PATH, PROTECT, "integrity_manifest.json"])
    if changed != expected:
        raise ValueError("unreviewed_v732_change_scope")
    msg = git(root, "show", "--no-patch", "--format=%B", LANDING).decode("utf-8")
    if "#732" not in msg or "V732" not in msg:
        raise ValueError("missing_original_landing_identity")
    support = git_blob(root, MAIN, PROTECT, PROTECT_MAIN_BLOB).decode("utf-8")
    for marker in (LANDING, AFTER_BLOB, "V732: accept only the exact CSS-title cleanup",
                   "merge-base", "event_path ="):
        if marker not in support:
            raise ValueError("missing_v732_immutable_source_guard")
    return {
        "schema": "tcg-v732-css-cleanup-original-source-proof/v1",
        "protected_main_sha": MAIN,
        "original_landing_sha": LANDING,
        "original_baseline_sha": BASE,
        "old_event_blob": BEFORE_BLOB,
        "cleaned_event_blob": AFTER_BLOB,
        "current_protect_source_blob": PROTECT_MAIN_BLOB,
        "original_change_paths": changed,
        "css_title_rows_removed": len(removed),
        "other_event_rows_semantically_preserved": len(after["items"]),
        "historical_code_and_data_inspected": True,
        "current_head_live_event_collector_tested": False,
        "release_version_certified": False,
        "all_100_versions_reviewed": False,
        "quality_score": None,
        "device_verified": False,
        "status": "V732_ORIGINAL_CSS_DATA_PATCH_PROVED_NOT_DEPLOYMENT"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        data = review(args.root)
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:160]}))
        return 2
    print(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
