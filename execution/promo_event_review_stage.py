"""Explicit review staging; never overwrite, approve, or publish event evidence.

The module writes ONLY a new, caller-named stage file. It is not the legacy
collector, not a source refresh, and not a substitute for a reviewed successor.
No operation is performed without an explicit --output when run as a CLI.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

from execution.promo_event_readonly_preflight import (
    MAX_INPUT_BYTES, SNAPSHOT, read_stable_snapshot,
)
from execution.static_refresh_event_preflight import prepare_validated_event_snapshot

STATUS = "CANDIDATE_STAGED_REVIEW_ONLY"
MAX_STAGE_BYTES = 2 * MAX_INPUT_BYTES


def stage_candidate(source: Path, destination: Path) -> dict:
    """Validate against legacy rules, then exclusively create a new stage file."""
    source, destination = Path(source), Path(destination)
    if os.path.abspath(source) == os.path.abspath(destination):
        raise ValueError("STAGE_CANNOT_REPLACE_SOURCE")
    if destination.is_symlink():
        raise ValueError("STAGE_TARGET_SYMLINK")
    if destination.parent.is_symlink():
        raise ValueError("STAGE_PARENT_SYMLINK")

    # No modification of the original evidence: the unmodified collector's
    # auxiliary sync is invoked exclusively with write=False on a deep copy.
    old_raw, original = read_stable_snapshot(source)
    import auto_update_all
    import update_promo_events

    synchronized = update_promo_events.refresh_auxiliary_coverage_metadata(
        deepcopy(original), write=False,
    )
    candidate = prepare_validated_event_snapshot(
        synchronized, auto_update_all.validate_json,
    )
    if candidate.get("updated_at") != original.get("updated_at"):
        raise ValueError("STAGE_SOURCE_TIMESTAMP_DRIFT")
    if not isinstance(candidate.get("product_release_review_queue", []), list):
        raise ValueError("STAGE_REVIEW_QUEUE_INVALID")

    # Refuse a stale input if the source changed during preparation.
    confirmed_raw, _ = read_stable_snapshot(source)
    if old_raw != confirmed_raw:
        raise ValueError("STAGE_SOURCE_CHANGED_BEFORE_WRITE")

    payload = (json.dumps(candidate, ensure_ascii=False, sort_keys=True,
                          indent=2) + "\n").encode("utf-8")
    if len(payload) > MAX_STAGE_BYTES:
        raise ValueError("STAGE_TOO_LARGE")

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(destination, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        # Keep any interrupted file clearly unapproved; never roll forward
        # the source or rename this stage to the live data path.
        raise

    return {
        "status": STATUS,
        "source_refresh_performed": False,
        "publish_allowed": False,
        "device_install_allowed": False,
        "review_required": True,
        "input_sha256": hashlib.sha256(old_raw).hexdigest(),
        "stage_sha256": hashlib.sha256(payload).hexdigest(),
        "input_bytes": len(old_raw),
        "stage_bytes": len(payload),
        "source_updated_at": original.get("updated_at"),
        "manual_review_queue_rows": len(
            candidate.get("product_release_review_queue", [])
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage a validated TCG event candidate for human review")
    parser.add_argument("--output", type=Path, required=True,
                        help="new review-only JSON file; existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        report = stage_candidate(SNAPSHOT, args.output)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
        print(json.dumps({
            "status": "STAGE_REVIEW_FAILED",
            "publish_allowed": False,
            "device_install_allowed": False,
            "error_type": type(exc).__name__,
        }, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
