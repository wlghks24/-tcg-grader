"""V887 post-collection evidence gate (opt-in, not wired to approved V43).

This module NEVER starts the collector or downloads/changes a photo. Only an
already-finished original collector receipt can advance a repeated gap counter.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import tablet_image_library_v1 as library
from execution.tablet_catalog_bridge import build_report, write_gap_queue
from execution.tablet_image_reciprocity_v887 import read_summary, write_plan

STATE_FILENAME = "auto_state_v2.json"
MAX_STATE_BYTES = 1_500_000
MAX_AGE_SECONDS = 7 * 86400


def completed_cycle_id(*, root=None, now=None):
    """Validate a persisted receipt, not an observed read or a caller counter."""
    root = Path(root) if root is not None else library.storage_root()
    state_file = root / STATE_FILENAME
    try:
        if (state_file.is_symlink() or not state_file.is_file()
                or state_file.stat().st_size > MAX_STATE_BYTES):
            return None, "HOLD_NO_VALID_COLLECTOR_RECEIPT"

        def pairs_unique(pairs):
            value = {}
            for key, member in pairs:
                if key in value:
                    raise ValueError("duplicate_state_key")
                value[key] = member
            return value

        with library.LOCK:
            state = json.loads(state_file.read_text(encoding="utf-8"),
                               object_pairs_hook=pairs_unique)
        if not isinstance(state, dict) or type(state.get("cross_cycle")) is not int:
            return None, "HOLD_COLLECTOR_STATE_SCHEMA"
        if not 1 <= state["cross_cycle"] <= 1_000_000:
            return None, "HOLD_COLLECTOR_STATE_SCHEMA"
        last = state.get("last_result")
        if not isinstance(last, dict):
            return None, "HOLD_COLLECTOR_RESULT"
        # Failed/interrupted cycles cannot be used as success evidence.
        if last.get("stopped") is not False or last.get("deferred") is not False:
            return None, "HOLD_UNFINISHED_COLLECTION"
        if type(last.get("errors")) is not int or last["errors"] != 0:
            return None, "HOLD_COLLECTION_ERRORS"
        scanned = last.get("scanned", 0)
        metadata_attempted = last.get("metadata_repair_attempted", 0)
        if (type(scanned) is not int or type(metadata_attempted) is not int
                or not 0 <= scanned <= 100000 or
                not 0 <= metadata_attempted <= 100000 or
                scanned + metadata_attempted == 0):
            return None, "HOLD_NO_COLLECTION_ACTIVITY"
        raw_run_at = last.get("run_at")
        finish = state.get("last_finished_epoch")
        if (not isinstance(raw_run_at, str) or len(raw_run_at) > 64
                or type(finish) not in (float, int)
                or not math.isfinite(finish)):
            return None, "HOLD_INVALID_COLLECTION_TIME"
        started = datetime.fromisoformat(raw_run_at.replace("Z", "+00:00"))
        if started.tzinfo is None:
            return None, "HOLD_INVALID_COLLECTION_TIME"
        started_epoch = started.timestamp()
        when = datetime.now(timezone.utc).timestamp() if now is None else now
        if (type(when) not in (float, int) or not math.isfinite(when)
                or finish <= 0 or finish > when + 300
                or finish < when - MAX_AGE_SECONDS
                or started_epoch > finish + 1 or started_epoch < finish - 86400):
            return None, "HOLD_STALE_OR_UNORDERED_COLLECTION_TIME"
        # Hash contains cycle index, start receipt and finish receipt. A rerun
        # against the same saved state MUST map to the exact same identity.
        raw = f'{state["cross_cycle"]}|{raw_run_at}|{finish:.6f}'
        return hashlib.sha256(raw.encode("utf-8")).hexdigest(), "COMPLETED_COLLECTOR_RECEIPT"
    except (ValueError, TypeError, OSError, UnicodeError, OverflowError):
        return None, "HOLD_INVALID_COLLECTOR_RECEIPT"


def reconcile_finished_cycle(repo, *, root=None, now=None):
    """Write private evidence plan, only after authentic locally completed cycle.

    Source/catalog and image bytes are never mutated. No network I/O.
    """
    root = Path(root) if root is not None else library.storage_root()
    token, reason = completed_cycle_id(root=root, now=now)
    if not token:
        return {"ok": False, "status": reason, "physical_tablet_verified": False}
    report = build_report(repo)
    if (report.get("ok") is not True or report.get("source_errors")
            or not isinstance(report.get("gap_queue"), list)):
        return {"ok": False, "status": "HOLD_INCOMPLETE_SOURCE_REPORT",
                "physical_tablet_verified": False}
    queue = write_gap_queue(repo)
    if not queue.get("ok"):
        return {"ok": False, "status": "HOLD_SOURCE_QUEUE_WRITE",
                "physical_tablet_verified": False}
    planned = write_plan(report, root=root, cycle_id=token)
    return {"ok": planned.get("ok") is True, "status": planned.get("status"),
            "reciprocal_recheck": planned.get("summary"),
            "physical_tablet_verified": False,
            "runtime_integration": "OPT_IN_POST_COLLECTION_ONLY"}


def read_only_status():
    """Safe diagnostic; no request or file mutation."""
    return {"reciprocal_recheck": read_summary(),
            "runtime_integration": "NOT_CONNECTED_TO_PROTECTED_V43",
            "physical_tablet_verified": False}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="V887 local collector receipt review")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--record-completed-cycle", action="store_true",
                        help="Opt-in private evidence plan write; never downloads images")
    args = parser.parse_args()
    result = (reconcile_finished_cycle(args.repo) if args.record_completed_cycle
              else read_only_status())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.record_completed_cycle and not result.get("ok"):
        sys.exit(2)
