#!/usr/bin/env python3
"""V977 read-only Termux process inventory. Never signals, stops or installs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

SIGNATURES = {
    "boot": "TCG_AUTO_START.sh",
    "launcher": "execution/start_tablet_unified_v897.sh",
    "server": "execution.tablet_unified_runtime_v889",
    "pair": "graded_photo_manual_pair_queue.py",
    "raw": "verified_slab_raw_learning_v155.py",
    "archive": "verified_slab_training_archive_v152.py",
}
REQUIRED = frozenset(SIGNATURES)
PID = re.compile(r"[1-9][0-9]*\\Z")


def read_process(proc: Path, pid: int):
    """Capture kernel start ticks to detect PID reuse in a later comparison."""
    directory = proc / str(pid)
    try:
        raw = (directory / "cmdline").read_bytes()
        argv = [s.decode("utf-8", "replace") for s in raw.split(b"\\0") if s]
        stat = (directory / "stat").read_text()
        tail = stat.rsplit(")", 1)[1].split()
        start_ticks = int(tail[19])  # /proc/[pid]/stat field 22
        cwd = os.readlink(directory / "cwd")
    except (OSError, ValueError, IndexError):
        return None
    if not argv:
        return None
    command = " ".join(argv)
    roles = [role for role, token in SIGNATURES.items() if token in command]
    if not roles:
        return None
    return {"pid": pid, "ppid": int(tail[1]), "start_ticks": start_ticks,
            "cwd": cwd, "argv": argv, "roles": roles}


def inventory(repo: Path, proc: Path = Path("/proc")):
    repo = repo.expanduser().resolve(strict=True)
    if not (repo / ".git").exists():
        raise ValueError("LIVE_REPOSITORY_REQUIRED")
    rows = []
    for entry in proc.iterdir():
        if entry.name.isdigit():
            item = read_process(proc, int(entry.name))
            if item is not None:
                rows.append(item)
    rows.sort(key=lambda row: row["pid"])
    found = {role for row in rows for role in row["roles"]}
    boot = [row for row in rows if "boot" in row["roles"]]
    launcher = [row for row in rows if "launcher" in row["roles"]]
    archive = [row for row in rows if "archive" in row["roles"]]
    # Fail closed: no process can be identified as safe to stop from this report.
    reasons = []
    if found != REQUIRED:
        reasons.append("REQUIRED_ROLES_NOT_UNIQUELY_VERIFIED")
    if len(boot) != 1 or len(launcher) != 1 or len(archive) != 1:
        reasons.append("SUPERVISOR_OR_LAUNCHER_AMBIGUOUS")
    if any(row["cwd"] != str(repo) for row in rows if "boot" not in row["roles"]):
        reasons.append("PROCESS_WORKDIR_MISMATCH")
    if any(row["ppid"] == 1 for row in archive):
        reasons.append("ORPHAN_ARCHIVE_WATCHER_REQUIRES_COORDINATION")
    if boot:
        reasons.append("BOOT_MAINTENANCE_HANDSHAKE_NOT_IMPLEMENTED")
    lock = repo / ".tcg_android_start.lock" / "pid"
    if lock.is_symlink():
        reasons.append("UNSAFE_LOCK_SYMLINK")
    else:
        try:
            lock_pid = lock.read_text().strip()
        except OSError:
            lock_pid = ""
        if not PID.fullmatch(lock_pid) or not any(str(row["pid"]) == lock_pid for row in launcher):
            reasons.append("LAUNCHER_LOCK_MISMATCH")
    return {"status": "HOLD_NO_DEVICE_ACTION", "repo": str(repo),
            "processes": rows, "reasons": sorted(set(reasons)),
            "installation_completed": False, "signals_sent": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = inventory(args.repo)
    except (OSError, ValueError) as exc:
        report = {"status": "HOLD_NO_DEVICE_ACTION", "reason": str(exc),
                  "installation_completed": False, "signals_sent": False}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
