"""Fail-closed read-only evidence for the existing Lenovo main/Termux route."""
from __future__ import annotations
from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Any

SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_AGE_SECONDS = 26 * 3600

def _sha(value: Any) -> str | None:
    return value if isinstance(value, str) and SHA.fullmatch(value) else None

def _read_env(path: Path) -> dict[str, str]:
    """Parse existing .env as untrusted data, never as shell instructions."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192:
            return {}
        contents = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {}
    result: dict[str, str] = {}
    for row in contents.splitlines():
        if "=" not in row:
            continue
        key, value = row.split("=", 1)
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,50}", key) and len(value) < 2048 and key not in result:
            result[key] = value
    return result

def _fresh(value: str | None, now: datetime) -> bool:
    try:
        observed = datetime.strptime(value or "", "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return False
    age = (now.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
    return -180 <= age <= MAX_AGE_SECONDS

def _loop_verified(root: Path, identity: dict[str, str], heartbeat: dict[str, str]) -> bool:
    pid = identity.get("PID", "")
    if not re.fullmatch(r"[1-9][0-9]{0,7}", pid):
        return False
    if (heartbeat.get("BOOT_LOOP_PID") != pid
        or identity.get("VERSION") != "daily-2300-kst-v3"
        or heartbeat.get("BOOT_LOOP_VERSION") != identity.get("VERSION")
        or heartbeat.get("ROOT") != str(root.resolve())):
        return False
    proc = Path("/proc") / pid
    try:
        if proc.stat().st_uid != os.getuid():
            return False
        argv = (proc / "cmdline").read_bytes()[:8192].split(b"\0")
    except (OSError, UnicodeError):
        return False
    return str(root / "TABLET_SCHEDULED_UPDATE.sh").encode() in argv and b"boot-loop" in argv

def evaluate(
    root: Path, git: dict[str, Any], health: dict[str, Any], runtime: dict[str, Any],
    *, state_root: Path | None = None, now: datetime | None = None,
) -> dict[str, Any]:
    """Assess three independent stages; a GitHub CI pass is not device evidence."""
    root = Path(root).resolve()
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("aware_now_required")
    state = state_root or Path.home() / ".local/state/tcg-grader/scheduled-update"
    update = _read_env(state / "status.env")
    heartbeat = _read_env(state / "boot-heartbeat.env")
    identity = _read_env(state / "boot-loop.pid")
    disk = _sha(git.get("sha_full"))
    remote = _sha(update.get("REMOTE_SHA"))
    recorded = _sha(update.get("LOCAL_SHA"))
    local_origin = _sha(git.get("origin_main"))
    official = git.get("origin_url") in (
        "https://github.com/wlghks24/-tcg-grader",
        "https://github.com/wlghks24/-tcg-grader.git",
        "git@github.com:wlghks24/-tcg-grader.git",
    )
    fresh = _fresh(update.get("LAST_CHECK"), now)
    code_ok = (disk is not None and disk == recorded == remote == local_origin
               and official and git.get("branch") == "main" and fresh
               and update.get("RESULT") in ("UP_TO_DATE", "UPDATED"))
    code_status = "LOCAL_MAIN_CHECK_VERIFIED" if code_ok else "MAIN_UPDATE_UNVERIFIED"
    if update.get("RESULT") in ("FETCH_FAILED", "LOCAL_CHANGES_HOLD", "UPDATE_FAILED", "POSTCHECK_MISMATCH"):
        code_status = "MAIN_UPDATE_HOLD"
    running = _sha(runtime.get("running_build_sha"))
    if disk and running and running != disk:
        runtime_status = "RUNNING_SHA_MISMATCH"
    elif disk and health.get("ok") is True and runtime.get("ok") is True and running == disk:
        runtime_status = "RUNNING_SHA_VERIFIED_LOCAL_HTTP"
    else:
        runtime_status = "RUNNING_SHA_UNVERIFIED"
    loop_running = _fresh(heartbeat.get("BOOT_LOOP_HEARTBEAT_AT"), now) and _loop_verified(root, identity, heartbeat)
    boot_script = Path.home() / ".termux/boot/tcg-grader-scheduled-update.sh"
    boot_present = boot_script.is_file() and not boot_script.is_symlink()
    return {
        "schema": "tablet-delivery-v1005",
        "code_update_status": code_status, "code_update_checked_fresh": fresh,
        "disk_sha": disk or "unknown", "recorded_remote_sha": remote or "unknown",
        "local_origin_main_sha": local_origin or "unknown", "official_origin_verified": official,
        "runtime_status": runtime_status, "running_sha": running or "unknown",
        "scheduler_status": "LOOP_RUNNING_LOCALLY" if loop_running else "LOOP_NOT_VERIFIED",
        "boot_script_present": boot_present, "reboot_verified": False,
        "physical_tablet_verified": False,
        "ready_for_device_readback": bool(code_ok and runtime_status == "RUNNING_SHA_VERIFIED_LOCAL_HTTP" and loop_running and boot_present),
        "note": "Local source and health do not prove a physical reboot, PWA rendering, or grading accuracy",
    }
