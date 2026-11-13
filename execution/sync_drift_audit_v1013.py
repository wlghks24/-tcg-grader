#!/usr/bin/env python3
"""Read-only V426/V427 successor drift evidence; never authorizes a bypass."""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHS = (
    ".github/workflows/tablet-autonomy-patch-checks.yml",
    ".github/workflows/tablet-v1013-offdevice-compare.yml",
    "tablet_autonomous_evolution_v372.py",
    "tablet_autonomous_evolution_v387.py",
)
V641_BASE = "4c8e210069867f68818661ee93127dce960f5b9c"
V641_CANDIDATE = "dcf287caf103d0aa19c5aec0231e5643096eee67"

def git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=False)

def main() -> int:
    result = {"schema": "tcg-v1013-sync-drift-audit/v1",
              "read_only": True, "sync_successor_approved": False,
              "physical_tablet_verified": False, "paths": []}
    try:
        head = git("rev-parse", "HEAD")
        if head.returncode:
            raise ValueError("git_head_unavailable")
        result["head_sha"] = head.stdout.decode().strip()
        for commit in (V641_BASE, V641_CANDIDATE):
            if git("merge-base", "--is-ancestor", commit, "HEAD").returncode:
                raise ValueError("v641_history_missing")
        for relative in PATHS:
            target = ROOT / relative
            if target.is_symlink() or not target.is_file():
                raise ValueError("missing_or_unsafe:" + relative)
            current = target.read_bytes()
            row = {"path": relative, "current_sha256": hashlib.sha256(current).hexdigest(),
                   "current_bytes": len(current), "history": {}}
            for label, commit in (("v641_base", V641_BASE), ("v641_candidate", V641_CANDIDATE)):
                old = git("show", f"{commit}:{relative}")
                row["history"][label] = ({"present": True, "sha256": hashlib.sha256(old.stdout).hexdigest()}
                                         if old.returncode == 0 else {"present": False})
            tracked = git("show", f"HEAD:{relative}")
            if tracked.returncode or hashlib.sha256(tracked.stdout).hexdigest() != row["current_sha256"]:
                raise ValueError("working_tree_drift:" + relative)
            row["changed_after_v641"] = (
                row["history"]["v641_candidate"].get("sha256") != row["current_sha256"]
            )
            result["paths"].append(row)
        # Previously approved V641 files must remain byte-for-byte unchanged.
        approved = {
            ".github/workflows/tablet-autonomy-patch-checks.yml":
                "831e5a2b030c15fb43c7c450de7ba815f5f59827f1fa9e07670af6959dd40ac6",
            "tablet_autonomous_evolution_v372.py":
                "0cab6ba76f339f33800d2210fd9e3cd7b332f54dd5f505eb692e949e505e6170",
            "tablet_autonomous_evolution_v387.py":
                "006f62226eeb26abd9f0a13661d066c497381c37d0ce699b0b5f167e345ad4ae",
        }
        for row in result["paths"]:
            path = row["path"]
            if path in approved and (row["current_sha256"] != approved[path]
                                     or row["changed_after_v641"]):
                raise ValueError("v641_pin_mismatch:" + path)
        # A newly added workflow requires separate review, never implicit approval.
        new = next(row for row in result["paths"]
                   if row["path"] == ".github/workflows/tablet-v1013-offdevice-compare.yml")
        if new["history"]["v641_base"]["present"] or new["history"]["v641_candidate"]["present"]:
            raise ValueError("v1013_workflow_unexpected_history")
        result["audit_complete"] = True
    except (OSError, ValueError) as exc:
        result["audit_complete"] = False
        result["hold_reason"] = str(exc)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result.get("audit_complete") else 2

if __name__ == "__main__":
    sys.exit(main())
