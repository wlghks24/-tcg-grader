"""V676 read-only, resource-neutral account of true independent label gaps.

The existing six-hour Termux supervisor remains the only active learning owner.
This module does not observe sources, train models, mutate labels or request
network access. Missing outcomes and unverified legacy examples never count.
"""
from __future__ import annotations

import math

MODEL_NAMES = ("query", "job")
HARD_LABEL_MINIMUM = 1000
HARD_CLASS_MINIMUM = 100


def count(value):
    return value if type(value) is int and 0 <= value <= 10_000_000 else None


def _gap(value):
    return max(0, HARD_LABEL_MINIMUM - value) if value is not None else None


def assess_model(value):
    """Report demonstrable blockers, never set a training approval flag."""
    result = {
        "state": "UNVERIFIED",
        "eligible_labels": None,
        "remaining_verified_labels": None,
        "positive_labels_remaining": None,
        "negative_labels_remaining": None,
        "training_permitted": False,
        "model_promotion_permitted": False,
        "next_step": "verify_independent_outcome_labels",
        "blockers": [],
    }
    if not isinstance(value, dict):
        result["blockers"].append("MODEL_STATUS_MISSING_OR_INVALID")
        return result
    eligible = count(value.get("eligible_training_labels"))
    total = count(value.get("label_count"))
    minimum = count(value.get("minimum_labels"))
    readiness = value.get("training_readiness")
    result["eligible_labels"] = eligible
    result["remaining_verified_labels"] = _gap(eligible)
    if total is None or eligible is None or eligible > total:
        result["blockers"].append("INDEPENDENT_LABEL_COUNTS_UNVERIFIED")
    if minimum is None or minimum < HARD_LABEL_MINIMUM:
        result["blockers"].append("TRAINING_POLICY_MINIMUM_UNVERIFIED")
    if not isinstance(readiness, dict):
        result["blockers"].append("CLASS_DISTRIBUTION_UNVERIFIED")
    else:
        for field, output in (
                ("positive_labels_remaining", "positive_labels_remaining"),
                ("negative_labels_remaining", "negative_labels_remaining")):
            n = count(readiness.get(field))
            result[output] = n
            if n is None:
                result["blockers"].append("CLASS_DISTRIBUTION_UNVERIFIED")
        if readiness.get("ready") is True and (
                eligible is None or eligible < HARD_LABEL_MINIMUM or
                result["positive_labels_remaining"] != 0 or
                result["negative_labels_remaining"] != 0):
            result["blockers"].append("CONTRADICTORY_READINESS")
    if eligible is None or eligible < HARD_LABEL_MINIMUM:
        result["blockers"].append("INSUFFICIENT_INDEPENDENT_LABELS")
    if isinstance(readiness, dict) and readiness.get("ready") is not True:
        result["blockers"].append("REVIEWED_READINESS_NOT_YET_CONFIRMED")
    if value.get("training_attempted") is True and isinstance(value.get("training_result"), dict):
        outcome = value["training_result"]
        if outcome.get("training_skipped") is False and outcome.get("active") is False:
            result["blockers"].append("PRIOR_TRAINING_RESULT_UNSUCCESSFUL")
    result["blockers"] = sorted(set(result["blockers"]))
    result["state"] = "ELIGIBLE_FOR_EXISTING_GATE_REVIEW" if not result["blockers"] else "WAITING_FOR_VERIFIED_EVIDENCE"
    result["next_step"] = (
        "existing_scheduler_may_evaluate_gates"
        if not result["blockers"] else
        "continue_verified_collection_without_fabricating_labels"
    )
    return result


def assess(learning):
    """Accept existing status JSON in memory; do not fetch or persist anything."""
    result = {
        "version": "v676",
        "scope": "OFFLINE_ADVISORY_GAPS_ONLY",
        "training_permitted": False,
        "model_promotion_permitted": False,
        "real_device_verified": False,
        "source_rewrite_permitted": False,
        "models": {},
        "overall": "HOLD",
    }
    models = learning.get("models") if isinstance(learning, dict) else None
    if not isinstance(models, dict):
        models = {}
    for name in MODEL_NAMES:
        result["models"][name] = assess_model(models.get(name))
    return result
