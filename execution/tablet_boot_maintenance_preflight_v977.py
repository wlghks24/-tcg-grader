#!/usr/bin/env python3
"""V977 read-only Boot maintenance protocol inspection; never creates markers."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

PROTOCOL = "TCG_V977_MAINTENANCE_PROTOCOL_V1"
PAUSE = "TCG_V977_MAINTENANCE_PAUSE"
ACK = "TCG_V977_MAINTENANCE_ACK"


def inspect(repo: Path, boot_script: Path) -> dict:
    reasons = []
    repo = Path(repo).expanduser()
    boot_script = Path(boot_script).expanduser()
    if repo.is_symlink() or not repo.is_dir() or not (repo / ".git").is_dir():
        reasons.append("LIVE_REPO_NOT_VERIFIED")
    if boot_script.is_symlink() or not boot_script.is_file():
        reasons.append("BOOT_SCRIPT_NOT_REGULAR")
        content = ""
    else:
        try:
            content = boot_script.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            reasons.append("BOOT_SCRIPT_UNREADABLE")
            content = ""
    # Text markers are a prerequisite for further manual audit, never proof of
    # a working pause/ack protocol or authorization to stop a process.
    if not all(token in content for token in (PROTOCOL, PAUSE, ACK)):
        reasons.append("BOOT_PROTOCOL_NOT_PRESENT")
    reasons.append("BOOT_PAUSE_ACK_RUNTIME_NOT_VERIFIED")
    return {"status": "HOLD_NO_DEVICE_ACTION", "reasons": sorted(set(reasons)),
            "protocol_marker_present": all(token in content for token in (PROTOCOL, PAUSE, ACK)),
            "installation_completed": False, "signals_sent": False,
            "files_written": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--boot-script", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(inspect(args.repo, args.boot_script), ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
