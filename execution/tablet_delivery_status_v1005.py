"""Read-only, fail-closed assessment of the existing Lenovo main delivery.

This module neither installs nor starts software. A main checkout, running HTTP
build, scheduled-update loop, and actual reboot are independent evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Any

SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_AGE_SECONDS = 26 * 3600
MAX_SIZE = 8192


def _sha(value: Any) -> str | None:
    return value if isinstance(value, str) and SHA.fullmatch(value) else None


def _read_env(path: Path) -> dict[str, str]:
    """Parse bounded scheduler records as plain text, NEVER source as shell."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SIZE:
            return {}
        data = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    result: dict[str, str] = {}
    for line in data.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,50}", key) and len(value) < 2048 and key not in result:
            result[key] = value
    return result


def _age_fresh(value: str | None, now: datetime, *, max_age: int = MAX_AGE_SECONDS) -> bool:
    if not value:
        return False
    try:
        observed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return False
    age = (now.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
    return -180 <= age <= max_age


def _running_loop(root: Path, ident: dict[str, str], heartbeat: dict[str, str]) -> bool:
    pid = ident.get("PID", "")
    if not re.fullmatch(r"[1-9][0-9]{0,7}", pid):
        return False
    if heartbeat.get("BOOT_LOOP_PID") != pid:
        return False
    if ident.get("VERSION") != "daily-2300-kst-v3" or heartbeat.get("BOOT_LOOP_VERSION") != ident.get("VERSION"):
        return False
    if heartbeat.get("ROOT") != str(root.resolve()):
        return False
    proc = Path("/proc") / pid
    try:
        # A recorded PID is not proof of the scheduler: check its live argv,
        # owner and working directory. Never send signals to this process.
        if proc.stat().st_uid != os.getuid():
            return False
        if (proc / "cwd").resolve(strict=True) != root:
            return False
        argv = (proc / "cmdline").read_bytes()[:8192].split(b"\0")
    except (OSError, UnicodeError):
        return False
    script = str(root / "TABLET_SCHEDULED_UPDATE.sh").encode()
    return script in argv and b"boot-loop" in argv


def evaluate(
    root: Path,
    git: dict[str, Any],
    health: dict[str, Any],
    runtime: dict[str, Any],
    *,
    state_root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return independent verdicts; never manufacture a tablet readback."""
    root = Path(root).resolve()
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("aware_now_required")
    state = state_root or (Path.home() / ".local/state/tcg-grader/scheduled-update")
    update = _read_env(state / "status.env")
    heartbeat = _read_env(state / "boot-heartbeat.env")
    ident = _read_env(state / "boot-loop.pid")
    disk = _sha(git.get("sha_full"))
    remote = _sha(update.get("REMOTE_SHA"))
    recorded = _sha(update.get("LOCAL_SHA"))
    local_origin = _sha(git.get("origin_main"))
    official_origin = git.get("origin_url") in (
        "https://github.com/wlghks24/-tcg-grader",
        "https://github.com/wlghks24/-tcg-grader.git",
        "git@github.com:wlghks24/-tcg-grader.git",
    )
    update_fresh = _age_fresh(update.get("LAST_CHECK"), now)
    code_ok = (disk is not None and disk == remote == recorded == local_origin
               and official_origin and git.get("branch") == "main" and update_fresh
               and update.get("RESULT") in ("UP_TO_DATE", "UPDATED"))
    code_status = "LOCAL_MAIN_CHECK_VERIFIED" if code_ok else "MAIN_UPDATE_UNVERIFIED"
    if update.get("RESULT") in ("FETCH_FAILED", "LOCAL_CHANGES_HOLD", "UPDATE_FAILED", "POSTCHECK_MISMATCH"):
        code_status = "MAIN_UPDATE_HOLD"
    # The existing runtime probe validates identity, delivery patch and SHA.
    run_sha = _sha(runtime.get("running_build_sha"))
    if disk and run_sha and run_sha != disk:
        runtime_status = "RUNNING_SHA_MISMATCH"
    elif disk and health.get("ok") is True and runtime.get("ok") is True and run_sha == disk:
        runtime_status = "RUNNING_SHA_VERIFIED_LOCAL_HTTP"
    else:
        runtime_status = "RUNNING_SHA_UNVERIFIED"
    boot_file = Path.home() / ".termux/boot/tcg-grader-scheduled-update.sh"
    try:
        boot_ready = (boot_file.is_file() and not boot_file.is_symlink()
                      and bool(boot_file.stat().st_mode & 0o111)
                      and boot_file.stat().st_size <= MAX_SIZE
                      and 'TABLET_SCHEDULED_UPDATE.sh" boot-loop' in boot_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        boot_ready = False
    # A valid boot script alone is not an Android package or reboot proof.
    loop_fresh = _age_fresh(heartbeat.get("BOOT_LOOP_HEARTBEAT_AT"), now)
    loop_running = loop_fresh and _running_loop(root, ident, heartbeat)
    scheduler_status = "LOOP_RUNNING_LOCALLY" if loop_running else "LOOP_NOT_VERIFIED"
    return {
        "schema": "tablet-delivery-v1005",
        "code_update_status": code_status,
        "code_update_checked_fresh": update_fresh,
        "disk_sha": disk or "unknown",
        "recorded_remote_sha": remote or "unknown",
        "local_origin_main_sha": local_origin or "unknown",
        "official_origin_verified": official_origin,
        "runtime_status": runtime_status,
        "running_sha": run_sha or "unknown",
        "scheduler_status": scheduler_status,
        "boot_script_present": boot_ready,
        "reboot_verified": False,
        "physical_tablet_verified": False,
        "ready_for_device_readback": code_ok and runtime_status == "RUNNING_SHA_VERIFIED_LOCAL_HTTP" and loop_running and boot_ready,
        "note": "CI or local health alone cannot prove reboot, PWA UI, card scan, or grading accuracy",
    }
