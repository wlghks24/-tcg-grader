#!/usr/bin/env python3
"""V653 bounded on-device autonomy observation journal.

Records ACTUAL local log/report hashes for future independent review.
NEVER produces V373/V374/V375 "verified" outcomes or changes learning gates.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json

SCHEMA_VERSION = 1
MAX_LOG_BYTES = 8_000_000
MAX_SOURCE_BYTES = 4_000_000
MAX_JOURNAL_BYTES = 512_000
MAX_OBSERVATIONS = 120
SOURCE_FILES = ("COLLECTION_VERIFICATION_REPORT.json", "STATIC_DATA_PUBLISH_REPORT.json")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _limited_bytes(path: Path, maximum: int) -> bytes | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
            return None
        with path.open("rb") as handle:
            raw = handle.read(maximum + 1)
        return raw if len(raw) <= maximum else None
    except (OSError, ValueError):
        return None


def _head_sha(root: Path) -> str | None:
    if root.is_symlink() or not root.is_dir():
        return None
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired):
        return None
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and SHA_RE.fullmatch(value) else None


def _v400_report(raw: bytes) -> dict[str, Any] | None:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError:
        return None
    for line in reversed(lines[-40:]):
        if len(line) > 300_000 or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(obj, dict) and isinstance(obj.get("execution"), dict) and "v400_status" in obj:
            return obj
    return None


def _reports(root: Path) -> dict[str, Any]:
    details = {}
    for name in SOURCE_FILES:
        path = root / name
        raw = _limited_bytes(path, MAX_SOURCE_BYTES)
        if raw is None:
            details[name] = {"status": "MISSING_OR_UNSAFE"}
        else:
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                payload = None
            details[name] = {
                "status": "PARSEABLE_UNVERIFIED" if isinstance(payload, dict) else "INVALID_JSON",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
    return details


def observe(root: Path, log: Path, now: datetime | None = None) -> dict[str, Any]:
    """Read-only capture; a hash proves bytes observed, NOT causal verification."""
    raw = _limited_bytes(log, MAX_LOG_BYTES)
    head = _head_sha(root)
    if raw is None or head is None:
        return {"status": "EVIDENCE_CAPTURE_HOLD", "reason": "INVALID_LOG_OR_HEAD"}
    report = _v400_report(raw)
    if report is None:
        return {"status": "EVIDENCE_CAPTURE_HOLD", "reason": "V400_LOG_JSON_MISSING"}
    execution = report["execution"]
    gate = report.get("v387_autonomous_gate")
    policy = report.get("v387_uncertainty_policy")
    if not isinstance(gate, dict) or not isinstance(policy, dict):
        return {"status": "EVIDENCE_CAPTURE_HOLD", "reason": "V387_GATES_MISSING"}
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "classification": "UNVERIFIED_RUNTIME_OBSERVATION_ONLY",
        "observed_at": moment.isoformat(timespec="seconds"),
        "git_head_sha": head,
        "log_file_name": log.name,
        "log_sha256": hashlib.sha256(raw).hexdigest(),
        "log_bytes": len(raw),
        "v400_status": str(report.get("v400_status") or "")[:96],
        "v387_status": str(gate.get("status") or "")[:96],
        "selected_action": str(policy.get("selected_action") or "")[:160],
        "reported_confidence": policy.get("selected_confidence")
        if isinstance(policy.get("selected_confidence"), (int, float)) else None,
        "reported_threshold": policy.get("confidence_threshold")
        if isinstance(policy.get("confidence_threshold"), (int, float)) else None,
        "reported_executed": execution.get("executed") is True,
        "reported_git_write": execution.get("git_write") is True,
        "source_reports": _reports(root),
        "verified_training_outcome": False,
        "may_promote_to_v373_outcome": False,
        "independent_receipt_required": True,
        "trust_increase_authorized": False,
    }


def _journal_load(path: Path) -> tuple[str, list[dict[str, Any]]]:
    if path.is_symlink():
        return "CORRUPT_OR_SYMLINK_HOLD", []
    if not path.exists():
        return "EMPTY", []
    raw = _limited_bytes(path, MAX_JOURNAL_BYTES)
    if raw is None:
        return "CORRUPT_OR_SYMLINK_HOLD", []
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return "CORRUPT_OR_SYMLINK_HOLD", []
    if (not isinstance(obj, dict) or obj.get("schema_version") != SCHEMA_VERSION
            or not isinstance(obj.get("observations"), list)
            or len(obj["observations"]) > MAX_OBSERVATIONS):
        return "CORRUPT_OR_SYMLINK_HOLD", []
    for row in obj["observations"]:
        if (not isinstance(row, dict)
                or row.get("classification") != "UNVERIFIED_RUNTIME_OBSERVATION_ONLY"
                or row.get("verified_training_outcome") is not False
                or row.get("trust_increase_authorized") is not False
                or not isinstance(row.get("log_sha256"), str)):
            return "CORRUPT_OR_SYMLINK_HOLD", []
    return "LOADED", obj["observations"]


def persist_observation(journal: Path, record: dict[str, Any]) -> dict[str, Any]:
    if record.get("classification") != "UNVERIFIED_RUNTIME_OBSERVATION_ONLY":
        return {"status": "NO_OBSERVATION_TO_SAVE", "written": False}
    if record.get("verified_training_outcome") is not False or record.get("trust_increase_authorized") is not False:
        return {"status": "UNSAFE_PROMOTION_HOLD", "written": False}
    if journal.is_symlink() or journal.parent.is_symlink() or not journal.parent.is_dir():
        return {"status": "UNSAFE_JOURNAL_PATH_HOLD", "written": False}
    lock = journal.with_name(journal.name + ".lock")
    if lock.is_symlink():
        return {"status": "UNSAFE_LOCK_PATH_HOLD", "written": False}
    try:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(lock, flags, 0o600)
    except OSError:
        return {"status": "LOCK_OPEN_HOLD", "written": False}
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return {"status": "CONCURRENT_CAPTURE_HOLD", "written": False}
        status, items = _journal_load(journal)
        if status == "CORRUPT_OR_SYMLINK_HOLD":
            return {"status": status, "written": False}
        if any(x["log_sha256"] == record["log_sha256"]
               and x.get("log_file_name") == record["log_file_name"] for x in items):
            return {"status": "ALREADY_OBSERVED", "written": False, "count": len(items)}
        if len(items) >= MAX_OBSERVATIONS:
            return {"status": "JOURNAL_CAPACITY_HOLD", "written": False, "count": len(items)}
        payload = {"schema_version": SCHEMA_VERSION, "observations": items + [record],
                   "training_promotion_authorized": False}
        if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_JOURNAL_BYTES:
            return {"status": "JOURNAL_SIZE_HOLD", "written": False}
        try:
            atomic_write_json(journal, payload, suffix=".v653-observations.tmp")
        except (OSError, UnicodeError, ValueError, TypeError):
            return {"status": "JOURNAL_WRITE_HOLD", "written": False}
        return {"status": "OBSERVATION_SAVED_UNVERIFIED", "written": True, "count": len(items) + 1}
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    args = parser.parse_args()
    receipt = observe(args.root, args.log)
    if receipt.get("classification") != "UNVERIFIED_RUNTIME_OBSERVATION_ONLY":
        print(json.dumps(receipt, sort_keys=True))
        return 2
    outcome = persist_observation(args.journal, receipt)
    print(json.dumps(outcome, sort_keys=True))
    return 0 if outcome["status"] in {"OBSERVATION_SAVED_UNVERIFIED", "ALREADY_OBSERVED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
