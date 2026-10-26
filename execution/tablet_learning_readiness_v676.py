"""V676 read-only Termux learning-gap reviewer for existing six-hour supervisor.

Never creates labels, trains, fetches, changes model files or installs a daemon.
Reads each model's existing independently verified label-status gate.
"""
from __future__ import annotations

import argparse
import json
import math


def _count(value):
    return value if type(value) is int and 0 <= value <= 10_000_000 else None


def _gap(status: dict):
    if not isinstance(status, dict):
        return {"status": "HOLD_INVALID_STATUS", "training_allowed": False}
    readiness = status.get("training_readiness")
    if not isinstance(readiness, dict) or type(readiness.get("ready")) is not bool:
        return {"status": "HOLD_INVALID_READINESS", "training_allowed": False}
    observed = _count(status.get("label_count"))
    # Query rejects legacy labels, while Job currently exposes the same
    # count as eligible. Never silently substitute total for eligible.
    eligible = _count(status.get("eligible_training_labels"))
    if eligible is None:
        eligible = _count(readiness.get("eligible_training_labels"))
    if eligible is None and status.get("scope") == "adaptive_public_search_priority_only":
        return {"status": "HOLD_ELIGIBLE_COUNT_UNKNOWN", "training_allowed": False}
    if eligible is None:
        eligible = observed
    minimum = _count(status.get("minimum_labels"))
    if any(v is None for v in (observed, eligible, minimum)) or minimum == 0 or eligible > observed:
        return {"status": "HOLD_COUNT_CONTRADICTION", "training_allowed": False}
    remaining = max(0, minimum - eligible)
    positive = _count(readiness.get("positive_labels_remaining"))
    negative = _count(readiness.get("negative_labels_remaining"))
    if positive is None or negative is None:
        return {"status": "HOLD_CLASS_COUNTS_UNKNOWN", "training_allowed": False}
    if type(readiness.get("automatic_training_on_collection")) is not bool:
        return {"status": "HOLD_AUTOMATION_POLICY_UNKNOWN", "training_allowed": False}
    ready = readiness["ready"]
    if ready and (remaining or positive or negative or not readiness["automatic_training_on_collection"]):
        return {"status": "HOLD_FALSE_READY", "training_allowed": False}
    if not isinstance(readiness.get("reason"), str):
        return {"status": "HOLD_READINESS_REASON_UNKNOWN", "training_allowed": False}
    reason = readiness["reason"]
    return {
        "status": "READY_FOR_EXISTING_GUARDED_TRAINING" if ready
        else "ACCUMULATING_VERIFIED_LABELS",
        "training_allowed": ready and readiness["automatic_training_on_collection"],
        "stored": observed,
        "eligible": eligible,
        "minimum": minimum,
        "total_remaining": remaining,
        "positive_remaining": positive,
        "negative_remaining": negative,
        "legacy_unverified_excluded": observed - eligible,
        "reason": reason[:90],
        "next_action": "existing_supervisor_train_if_ready" if ready
        else "continue_verified_collection_no_synthetic_labels",
    }


def summarize(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("local_only") is not True or snapshot.get("fabricated_labels") is not False:
        return {"ok": False, "status": "HOLD_UNTRUSTED_LEARNING_SNAPSHOT"}
    rows = snapshot.get("models")
    if not isinstance(rows, dict) or not rows or set(rows) - {"query", "job"}:
        return {"ok": False, "status": "HOLD_INVALID_MODELS"}
    results = {name: _gap(rows[name]) for name in ("query", "job") if name in rows}
    # Status is purely advisory; a successful snapshot is not a deployment
    # or trainer approval. Errors are counts only to avoid private log leaks.
    errors = snapshot.get("errors")
    healthy = errors == [] and len(results) == 2 and all(
        item["status"] in ("READY_FOR_EXISTING_GUARDED_TRAINING",
                           "ACCUMULATING_VERIFIED_LABELS")
        for item in results.values()
    )
    return {
        "ok": healthy,
        "status": "READ_ONLY_READY_TO_MONITOR" if healthy else "HOLD_SNAPSHOT_ERROR",
        "models": results,
        "training_executed": False,
        "production_model_changed": False,
        "new_labels_created": 0,
        "existing_six_hour_supervisor": True,
        "physical_tablet_verified": False,
    }


def run():
    from execution.tablet_local_learning import run as current_status
    return summarize(current_status(train=False))


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(run(), ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
