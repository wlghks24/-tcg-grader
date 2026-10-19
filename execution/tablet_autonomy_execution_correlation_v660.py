#!/usr/bin/env python3
"""V660: read-only V376 execution journal + V656 collector/trial corroboration.

A locally committed journal is not independent proof of market improvement.
No learner writes, no fabricated samples, no threshold or gate changes.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from execution import tablet_autonomy_collection_receipts_v653 as v653
from execution import tablet_autonomy_trial_provenance_v656 as v656

JOURNAL_NAME = "tablet_autonomy_execution_journal_v376.json"
MAX_JOURNAL_BYTES = 512_000
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
RECIPE_TO_ACTION = dict(v656.ACTIONS)


def _hold(reason: str) -> dict:
    return {
        "status": "JOURNAL_EVIDENCE_HOLD", "reason": reason,
        "local_correlation_only": True,
        "independent_external_attestation": False,
        "causal_improvement_proven": False,
        "verified_outcomes_created": 0, "eligible_for_v373_training": False,
        "v387_confidence_changed": False,
    }


def inspect(root: Path, *, now: datetime | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if root.is_symlink() or not root.is_dir():
        return _hold("UNSAFE_ROOT")
    journal_path = root / JOURNAL_NAME
    if journal_path.is_symlink() or not journal_path.is_file():
        return _hold("MISSING_OR_UNSAFE_JOURNAL")
    try:
        if journal_path.stat().st_size > MAX_JOURNAL_BYTES:
            return _hold("OVERSIZE_JOURNAL")
        journal, journal_digest = v653._load(journal_path)
    except (v653.Hold, OSError, UnicodeError, ValueError, TypeError):
        return _hold("INVALID_JOURNAL")
    if (type(journal.get("schema_version")) is not int
            or journal["schema_version"] != 6
            or journal.get("controller_version") != "v376"):
        return _hold("WRONG_JOURNAL_SCHEMA")
    state = journal.get("status")
    if state != "COMMITTED":
        return _hold("JOURNAL_NOT_COMMITTED")
    if (journal.get("git_write") is not False
            or journal.get("source_code_modified") is not False
            or journal.get("skill_state_status") != "SKILL_STATE_SAVED"
            or journal.get("operational_status") != "OPERATIONAL_REFRESH_EXECUTED"):
        return _hold("JOURNAL_NOT_PROVEN_SAFE_EXECUTION")
    for field in ("cycle_id", "plan_sha256"):
        value = journal.get(field)
        if not isinstance(value, str) or not SHA256.fullmatch(value):
            return _hold("INVALID_JOURNAL_DIGEST")
    recipe, skill_id = journal.get("selected_recipe"), journal.get("selected_skill_id")
    if (recipe not in RECIPE_TO_ACTION or not isinstance(skill_id, str)
            or not 1 <= len(skill_id) <= 128):
        return _hold("INVALID_JOURNAL_ACTION")
    try:
        intent_at, run_at, commit_at = (
            v653._stamp(journal.get(field))
            for field in ("prepared_at", "executed_at", "committed_at")
        )
        report, report_digest = v653._load(root / "auto_update_report.json")
        start = v653._stamp(report.get("started_at"))
        finish = v653._stamp(report.get("finished_at"))
    except (v653.Hold, OSError, UnicodeError, ValueError, TypeError):
        return _hold("INVALID_EXECUTION_OR_REPORT_TIMES")
    if (not intent_at <= run_at <= commit_at <= now + timedelta(minutes=5)
            or not start <= finish <= now + timedelta(minutes=5)
            or now - commit_at > timedelta(hours=36)):
        return _hold("INCONSISTENT_JOURNAL_TIMELINE")
    if (not start - timedelta(minutes=5) <= run_at <= finish + timedelta(minutes=5)
            or not finish - timedelta(minutes=5) <= commit_at <= finish + timedelta(minutes=15)):
        return _hold("JOURNAL_COLLECTOR_TIME_MISMATCH")
    correlated = v656.inspect(root, now=now)
    if correlated.get("status") != "LOCAL_EXECUTION_CORRELATED_UNVERIFIED":
        return _hold("COLLECTOR_TRIAL_" + str(correlated.get("reason") or "NOT_CORRELATED")[:85])
    trial = correlated.get("trial")
    if (not isinstance(trial, dict)
            or trial.get("trial_id") != skill_id
            or trial.get("action_id") != RECIPE_TO_ACTION[recipe]):
        return _hold("JOURNAL_TRIAL_ACTION_MISMATCH")
    if correlated.get("collector_report_sha256") != report_digest:
        return _hold("REPORT_SHA_MISMATCH")
    return {
        "status": "LOCAL_THREE_WAY_CORRELATED_UNVERIFIED",
        "cycle_id": journal["cycle_id"],
        "journal_sha256": journal_digest,
        "report_sha256": report_digest,
        "trial_id": skill_id,
        "action_id": RECIPE_TO_ACTION[recipe],
        "local_correlation_only": True,
        "independent_external_attestation": False,
        "causal_improvement_proven": False,
        "verified_outcomes_created": 0,
        "eligible_for_v373_training": False,
        "v387_confidence_changed": False,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True, type=Path)
    args = p.parse_args()
    print("V660_EXECUTION_CORRELATION=" +
          json.dumps(inspect(args.root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
