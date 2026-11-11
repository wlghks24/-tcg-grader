#!/usr/bin/env python3
"""Read-only GitHub main -> existing Lenovo Termux auto-pickup contract check.

No SSH, device control, installation, Git writes, training, or runtime mutation.
A passing report proves SOURCE STRUCTURE only, never physical deployment.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

RULES = {
    "main": {
        "existing_scheduler": "bash TABLET_SCHEDULED_UPDATE.sh ensure",
        "existing_runtime": "exec bash ANDROID_UPDATE_AND_START.sh",
        "current_update": "bash TABLET_SCHEDULED_UPDATE.sh run",
        "supervisor": "execution.tablet_local_automation install",
        "state_readback": "execution.tablet_local_automation status",
    },
    "TABLET_SCHEDULED_UPDATE.sh": {
        "official_main": 'OFFICIAL_HTTPS="https://github.com/wlghks24/-tcg-grader.git"',
        "canonical_fetch": 'git fetch "$OFFICIAL_HTTPS" refs/heads/main:refs/remotes/origin/main',
        "fixed_kst_hour": 'SCHEDULE_HOUR="23"',
        "fixed_kst_minute": 'SCHEDULE_MINUTE="00"',
        "update_only": 'TCG_UPDATE_ONLY=1 bash "$ROOT/ANDROID_UPDATE_AND_START.sh"',
        "runtime_reconciliation": "automation_tick()",
        "heartbeat": "write_boot_heartbeat()",
        "boot_loop": "boot_loop()",
        "auto_recovery": "ensure_schedule()",
        "source_hold": "LOCAL_CHANGES_HOLD",
    },
    "ANDROID_UPDATE_AND_START.sh": {
        "official_origin": "is_official_origin()",
        "official_main": 'OFFICIAL_HTTPS="https://github.com/wlghks24/-tcg-grader.git"',
        "candidate_review": "verify_remote_candidate()",
        "safe_fast_forward": "git merge --ff-only",
        "preserve_runtime_data": "backup_and_normalize_runtime()",
        "update_only": 'if [ "${TCG_UPDATE_ONLY:-0}" = "1" ]; then',
        "existing_launcher": "exec bash START_TCG_UPDATER_ANDROID.sh",
    },
    "execution/tablet_local_automation.py": {
        "termux_required": "def require_termux():",
        "check_source_sha": "def source_check(",
        "supervisor_tick": "def tick(",
        "existing_handoff": "runtime.handoff(",
        "running_sha_identity": "runtime.matched(",
        "install_entrypoint": "def install(",
        "status_readback": "def status(",
    },
    "tablet_runtime_manifest.py": {
        "control_plane": "TABLET_CONTROL_PLANE_FILES",
        "app_assets": "TABLET_PWA_ENTRY_FILES",
        "runtime_bundle": "ACTIVE_RUNTIME_FILES",
    },
}
FORBIDDEN = ("git reset --hard", "git clean -f", "git push --force")
MAX_FILE_BYTES = 100_000


def inspect(root: Path, *, sha: str, git_ref: str) -> dict:
    errors = []
    found = {}
    for name, contracts in RULES.items():
        p = root / name
        if p.is_symlink() or not p.is_file():
            errors.append(f"{name}: missing_or_symlink")
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("oversized")
            source = p.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError, ValueError):
            errors.append(f"{name}: unreadable_or_oversized")
            continue
        missing = [rule for rule, token in contracts.items() if token not in source]
        if missing:
            errors.extend(f"{name}: missing_{rule}" for rule in missing)
        if name in ("TABLET_SCHEDULED_UPDATE.sh", "ANDROID_UPDATE_AND_START.sh"):
            errors.extend(f"{name}: unsafe_{token.replace(' ', '_')}" for token in FORBIDDEN if token in source)
        found[name] = len(contracts) - len(missing)
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        errors.append("source_sha: invalid_or_unavailable")
    is_main = git_ref == "refs/heads/main"
    return {
        "schema_version": 1,
        "source_sha": sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None,
        "github_ref": git_ref,
        "source_scope": "main" if is_main else "review_candidate",
        "static_auto_pickup_contract_pass": not errors,
        "missing_or_unsafe_contracts": errors,
        "contract_count": sum(map(len, RULES.values())),
        "contract_files_checked": len(found),
        "existing_schedule": "23:00 Asia/Seoul (requires running Termux loop)",
        "code_delivery": "device pulls official GitHub main via existing scheduler",
        "code_ready_on_main": bool(not errors and is_main),
        "physical_tablet_verified": False,
        "installed_sha": None,
        "running_server_sha": None,
        "reboot_verified": False,
        "market_data_or_learning_verified": False,
        "evidence_scope": "static repository contract only; not a device readback",
        "status": ("SOURCE_CONTRACT_PASS_DEVICE_UNVERIFIED" if not errors
                   else "HOLD_SOURCE_CONTRACT_FAILED"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(args.root), "rev-parse", "HEAD"], text=True, timeout=10
        ).strip()
    except (OSError, subprocess.SubprocessError):
        sha = "unavailable"
    report = inspect(args.root, sha=sha, git_ref=os.environ.get("GITHUB_REF", "unavailable"))
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    print(encoded, end="")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.is_symlink() or args.output.resolve().is_relative_to(args.root.resolve()):
            raise SystemExit("HOLD: report output must be outside repository and not a symlink")
        args.output.write_text(encoded, encoding="utf-8")
    return 0 if report["static_auto_pickup_contract_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
