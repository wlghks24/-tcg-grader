#!/usr/bin/env python3
"""V656: read-only V374 collector ↔ V375 trial proof-stage crosscheck.

A matched local report is NOT independent attestation or causal improvement.
Never writes verified samples, model state, source files, or Git.
"""
from __future__ import annotations
import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tablet_autonomous_evolution_v374 as v374
from execution import tablet_autonomy_collection_receipts_v653 as v653

TRIGGER = "tablet-v374-autonomous-refresh"
ACTIONS = {
    "RECOVER_FRESHNESS": "REFRESH_MARKET_DATA",
    "EXPAND_REGION_COVERAGE": "EXPAND_MARKET_COVERAGE",
    "RECOVER_SOURCE_HEALTH": "RECHECK_DEGRADED_SOURCES",
}

def _hold(reason):
    return {"status": "EVIDENCE_HOLD", "reason": reason, "verified_outcomes_created": 0,
            "eligible_for_v373_training": False, "causal_improvement_proven": False,
            "independent_external_attestation": False, "v387_confidence_changed": False}

def inspect(root: Path, *, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if root.is_symlink() or not root.is_dir():
        return _hold("UNSAFE_ROOT")
    state_path = root / v374.SKILL_STATE_PATH.name
    if state_path.is_symlink():
        return _hold("SKILL_STATE_SYMLINK")
    loaded = v374.load_skill_state(path=state_path, now=now)
    if loaded.get("corruption_hold") is True:
        return _hold("SKILL_STATE_CORRUPT")
    pending = loaded["state"].get("pending_trials")
    if not isinstance(pending, list) or not pending:
        return _hold("NO_PENDING_TRIAL")
    try:
        observed = v653.observe(root, now=now)
        raw, digest = v653._load(root / "auto_update_report.json")
        started = v653._stamp(raw.get("started_at"))
        finished = v653._stamp(raw.get("finished_at"))
    except (v653.Hold, OSError, UnicodeError, ValueError, TypeError) as exc:
        return _hold("COLLECTOR_" + str(exc)[:90])
    if raw.get("trigger") != TRIGGER or observed["trigger"] != TRIGGER:
        return _hold("NOT_EXECUTED_BY_V374")
    if digest != observed["report_sha256"]:
        return _hold("COLLECTOR_DIGEST_MISMATCH")
    if not (started <= finished <= now and now-finished <= timedelta(hours=36)):
        return _hold("UNTRUSTED_REPORT_TIME")
    matching = []
    for trial in pending:
        if not isinstance(trial, dict):
            return _hold("BAD_TRIAL")
        recipe = trial.get("recipe")
        if recipe not in ACTIONS:
            continue  # No-op OBSERVE_ONLY/RECOVER_MODEL cannot be given action evidence.
        features = trial.get("meta_features")
        if not isinstance(features, list) or len(features) != 10 or any(
            isinstance(x, bool) or not isinstance(x, (int, float))
            or not math.isfinite(x) or x < 0 or x > 1 for x in features
        ):
            return _hold("INVALID_META_FEATURES")
        try:
            created = v653._stamp(trial.get("created_at"))
        except (v653.Hold, OSError, ValueError):
            return _hold("INVALID_TRIAL_TIME")
        if not (finished - timedelta(minutes=5) <= created <= finished + timedelta(minutes=15)):
            continue
        before = trial.get("before")
        if not isinstance(before, dict) or not before:
            return _hold("NO_PREACTION_BASELINE")
        if recipe == "RECOVER_FRESHNESS" and before.get("freshness") == "fresh":
            return _hold("FRESHNESS_NO_GAP")
        if recipe == "RECOVER_SOURCE_HEALTH":
            ratio = before.get("degraded_source_ratio")
            if isinstance(ratio, bool) or not isinstance(ratio, (float, int)) or not math.isfinite(ratio) or ratio <= 0.35:
                return _hold("SOURCE_HEALTH_NO_GAP")
        if recipe == "EXPAND_REGION_COVERAGE":
            if (trial.get("region") not in ("KR","JP","US")
                    or trial["region"] not in (before.get("low_coverage_regions") or ())):
                return _hold("REGION_COVERAGE_NO_GAP")
        if not isinstance(trial.get("skill_id"), str) or not trial["skill_id"]:
            return _hold("MISSING_TRIAL_ID")
        matching.append({"trial_id": trial["skill_id"][:128], "action_id": ACTIONS[recipe]})
    if len(matching) != 1:
        return _hold("NO_UNAMBIGUOUS_EXECUTED_TRIAL")
    return {
        "status": "LOCAL_EXECUTION_CORRELATED_UNVERIFIED",
        "trial": matching[0], "collector_report_sha256": digest,
        "output_sha256": observed["output_sha256"],
        "postflight_local_files_passed": True, "v374_trigger_matched": True,
        "verified_outcomes_created": 0,
        "eligible_for_v373_training": False,
        "causal_improvement_proven": False,
        "independent_external_attestation": False,
        "v387_confidence_changed": False,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    a = p.parse_args()
    print("V656_TRIAL_EVIDENCE=" + json.dumps(inspect(a.root), ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
