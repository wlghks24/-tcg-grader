#!/usr/bin/env python3
"""Single-run guard for transactional Tablet GPT / TCG Grader autonomy.

V377 keeps V376 as the verified transactional core and adds an OS-level,
non-blocking exclusive lock around every state-mutating cycle.  Concurrent
mutation attempts fail closed before skill/capability/meta state or execution
journals are touched.  Planning-only calls remain lock-free and read-only.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v376 as v376
from safe_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v377"
CORE_CONTROLLER_VERSION = "v376"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v377.lock"
REPORT_PATH = ROOT / "tablet_autonomy_v377_report.json"

SAFETY = dict(v376.SAFETY)
SAFETY.update({
    "single_mutating_cycle_lock_required": True,
    "concurrent_mutating_cycle_fail_closed": True,
    "concurrent_mutating_cycle_state_write_forbidden": True,
    "concurrent_mutating_cycle_execution_forbidden": True,
})

_HOLD_STATUSES = {
    "CONCURRENT_AUTONOMY_HOLD",
    "AUTONOMY_LOCK_UNAVAILABLE",
    "EXECUTION_RECOVERY_HOLD",
    "EXECUTION_PERSISTENCE_PRECONDITION_HOLD",
    "EVIDENCE_COMMIT_HOLD",
    "EXECUTION_JOURNAL_HOLD",
    "EXECUTED_JOURNAL_COMMIT_HOLD",
    "EXECUTED_STATE_COMMIT_HOLD",
}


def _mutating_requested(*, execute: bool, apply_capabilities: bool, train_meta: bool, apply_skills: bool) -> bool:
    return bool(execute or apply_capabilities or train_meta or apply_skills)


def _acquire_lock(path: Path) -> tuple[int | None, dict[str, Any]]:
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            return None, {"status": "AUTONOMY_LOCK_UNAVAILABLE", "error_code": "NOT_REGULAR_FILE"}
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        try:
            os.close(fd)
        except (OSError, UnboundLocalError):
            pass
        return None, {"status": "CONCURRENT_AUTONOMY_HOLD", "error_code": "LOCK_BUSY"}
    except OSError as exc:
        try:
            os.close(fd)
        except (OSError, UnboundLocalError):
            pass
        return None, {"status": "AUTONOMY_LOCK_UNAVAILABLE", "error_code": type(exc).__name__}
    return fd, {"status": "LOCK_ACQUIRED", "error_code": None}


def _release_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _hold(status: str, lock: dict[str, Any]) -> dict[str, Any]:
    return {
        "controller_version": CONTROLLER_VERSION,
        "core_controller_version": CORE_CONTROLLER_VERSION,
        "v377_status": status,
        "execution": {
            "status": status,
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        },
        "single_run_lock": lock,
        "safety": SAFETY,
    }


def _decorate(result: dict[str, Any], lock: dict[str, Any]) -> dict[str, Any]:
    result = dict(result)
    result["core_controller_version"] = str(result.get("controller_version") or CORE_CONTROLLER_VERSION)
    result["controller_version"] = CONTROLLER_VERSION
    result["v377_status"] = str(result.get("v376_status") or result.get("status") or "UNKNOWN")
    result["single_run_lock"] = dict(lock)
    result["safety"] = SAFETY
    return result


def run_cycle(
    *, execute: bool = False, apply_capabilities: bool = False, train_meta: bool = False,
    apply_skills: bool = False, root: Path = ROOT, now: datetime | None = None,
    proc_root: Path = Path("/proc"), state_path: Path | None = None,
    capability_path: Path | None = None, meta_model_path: Path | None = None,
    meta_outcomes_path: Path | None = None, skill_state_path: Path | None = None,
    skill_outcomes_path: Path | None = None, journal_path: Path | None = None,
    lock_path: Path | None = None, persist_outputs: bool = True,
) -> dict[str, Any]:
    kwargs = dict(
        execute=execute, apply_capabilities=apply_capabilities, train_meta=train_meta,
        apply_skills=apply_skills, root=root, now=now, proc_root=proc_root,
        state_path=state_path, capability_path=capability_path, meta_model_path=meta_model_path,
        meta_outcomes_path=meta_outcomes_path, skill_state_path=skill_state_path,
        skill_outcomes_path=skill_outcomes_path, journal_path=journal_path,
        persist_outputs=persist_outputs,
    )
    if not _mutating_requested(
        execute=execute, apply_capabilities=apply_capabilities,
        train_meta=train_meta, apply_skills=apply_skills,
    ):
        return _decorate(v376.run_cycle(**kwargs), {"status": "LOCK_NOT_REQUIRED", "error_code": None})

    lock_file = lock_path or (root / LOCK_PATH.name)
    fd, lock = _acquire_lock(lock_file)
    if fd is None:
        # Do not call V376 or persist shared outputs when another mutating cycle
        # may be active; contention itself must be side-effect free.
        return _hold(str(lock["status"]), lock)
    try:
        result = _decorate(v376.run_cycle(**kwargs), lock)
        if persist_outputs:
            try:
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v377-report.tmp")
                result["v377_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v377_runtime_output"] = {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
        return result
    finally:
        _release_lock(fd)


def self_test() -> None:
    assert SAFETY["single_mutating_cycle_lock_required"] is True
    assert SAFETY["concurrent_mutating_cycle_fail_closed"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["verification_bypass"] is False
    assert SAFETY["price_or_grade_invention"] is False
    print("Tablet autonomous single-run guard v377: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-safe-learning", action="store_true")
    parser.add_argument("--apply-capabilities", action="store_true")
    parser.add_argument("--train-meta", action="store_true")
    parser.add_argument("--apply-skills", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = run_cycle(
        execute=args.execute_safe_learning,
        apply_capabilities=args.apply_capabilities,
        train_meta=args.train_meta,
        apply_skills=args.apply_skills,
    )
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("v377_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
