"""Read-only official product/event preflight for existing TCG snapshot evidence.

A successful check means that the *already stored* snapshot can be partitioned
and its retained event rows satisfy the existing production shape validator.
It DOES NOT refresh a source, endorse an event date, publish data, modify
promo_events.json, approve a GitHub merge, or authorize a tablet installation.

Run: python -m execution.promo_event_readonly_preflight
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "promo_events.json"
MAX_INPUT_BYTES = 16 * 1024 * 1024
STATUS = "READ_ONLY_REVIEW_PASS_NOT_FRESH"


def assess_snapshot(payload: dict) -> dict:
    """Check a caller-owned JSON object without modifying it or persisting data."""
    from auto_update_all import validate_json
    from execution.static_refresh_event_preflight import prepare_validated_event_snapshot

    if not isinstance(payload, dict):
        raise ValueError("EVENT_SNAPSHOT_NOT_OBJECT")
    original = sum(len(payload[name]) for name in ("items", "archive_items")
                   if isinstance(payload.get(name), list))
    candidate = prepare_validated_event_snapshot(payload, validate_json)
    remaining = sum(len(candidate[name]) for name in ("items", "archive_items"))
    if original < remaining:
        raise ValueError("EVENT_PARTITION_INCREASED_EVENTS")
    return {
        "status": STATUS,
        "publish_allowed": False,
        "device_install_allowed": False,
        "source_refresh_performed": False,
        "original_event_and_archive_rows": original,
        "retained_event_and_archive_rows": remaining,
        "moved_product_only_rows": original - remaining,
        "manual_review_queue_rows": len(candidate.get("product_release_review_queue", [])),
        "source_updated_at": payload.get("updated_at"),
        "social_topic_source_updated_at": payload.get("social_topic_source_updated_at"),
    }


def _stat_identity(info) -> tuple[int, int, int, int]:
    """Use descriptor metadata; only reject drift, never infer freshness."""
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def read_stable_snapshot(path: Path = SNAPSHOT) -> tuple[bytes, dict]:
    """Read bounded original bytes and a decoded copy with drift checks."""
    import os
    path = Path(path)
    # Windows lacks O_NOFOLLOW. The precheck and post-open identity checks
    # detect ordinary path replacements; POSIX O_NOFOLLOW also rejects an
    # intermediate symlink swap. Neither implies a malicious-writer lock.
    if path.is_symlink():
        raise ValueError("EVENT_SNAPSHOT_SYMLINK")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("EVENT_SNAPSHOT_NOT_REGULAR_FILE")
        if before.st_size > MAX_INPUT_BYTES:
            raise ValueError("EVENT_SNAPSHOT_TOO_LARGE")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("EVENT_SNAPSHOT_TOO_LARGE")
        after = os.fstat(fd)
        if _stat_identity(before) != _stat_identity(after):
            raise ValueError("EVENT_SNAPSHOT_CHANGED_DURING_READ")
        if len(raw) != before.st_size:
            raise ValueError("EVENT_SNAPSHOT_INCOMPLETE_READ")
        current = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(current.st_mode) or _stat_identity(current) != _stat_identity(after):
            raise ValueError("EVENT_SNAPSHOT_PATH_REPLACED")
    finally:
        os.close(fd)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("EVENT_SNAPSHOT_NOT_OBJECT")
    return raw, payload


def inspect_file(path: Path = SNAPSHOT) -> dict:
    """Classify existing snapshot read-only after a stable bounded load."""
    raw, payload = read_stable_snapshot(path)
    result = assess_snapshot(payload)
    result["input_sha256"] = hashlib.sha256(raw).hexdigest()
    result["input_bytes"] = len(raw)
    return result


def main() -> int:
    try:
        result = inspect_file()
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
        # No raw file content or absolute machine paths in the failure report.
        print(json.dumps({
            "status": "READ_ONLY_REVIEW_FAILED",
            "publish_allowed": False,
            "device_install_allowed": False,
            "error_type": type(exc).__name__,
        }, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
