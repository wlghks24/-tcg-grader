"""Read-only tablet learning-gap advisor. Never trains, writes labels, or promotes models.

The existing six-hour Termux supervisor is the only background owner.
The advisor reads native query/job readiness and image-learning status;
all missing counts are advisory, never fabricated from social/candidate data.
"""
from __future__ import annotations

import argparse
import json
from typing import Any


def nonnegative_int(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= 10_000_000 else None


def inspect_model(name: str, data: dict) -> dict:
    """Require corroborating counts AND the existing model's own readiness gate."""
    result = {
        "model": name, "status": "HOLD", "training_permitted": False,
        "next_action": "verify_model_status", "stored_labels": None,
        "eligible_labels": None, "labels_missing": None,
        "positive_missing": None, "negative_missing": None,
        "legacy_unverified_excluded": None,
        "required_each_class": None,
        "evidence": "independent_verified_observations_only",
    }
    if name not in ("query", "job") or not isinstance(data, dict):
        return result
    stored = nonnegative_int(data.get("label_count"))
    minimum = nonnegative_int(data.get("minimum_labels"))
    eligible = nonnegative_int(data.get("eligible_training_labels"))
    if name == "job" and eligible is None:
        eligible = stored
    readiness = data.get("training_readiness")
    positives = nonnegative_int(data.get("positive_labels"))
    negatives = nonnegative_int(data.get("negative_labels"))
    if not isinstance(readiness, dict):
        return result
    per_class = nonnegative_int(readiness.get("minimum_each_class"))
    if None in (stored, minimum, eligible, positives, negatives, per_class):
        return result
    if minimum < 1 or per_class < 1 or eligible > stored or positives + negatives != eligible:
        result["next_action"] = "investigate_inconsistent_label_counts"
        return result
    result.update(
        stored_labels=stored, eligible_labels=eligible,
        legacy_unverified_excluded=stored-eligible,
        labels_missing=max(0, minimum-eligible),
        positive_missing=max(0, per_class-positives),
        negative_missing=max(0, per_class-negatives),
        required_each_class=per_class,
    )
    # Both independent-count and temporal split readiness must agree.
    count_ready=(eligible >= minimum and positives >= per_class and negatives >= per_class)
    legacy_ready=readiness.get("ready") is True
    if count_ready and legacy_ready:
        result.update(status="READY_FOR_EXISTING_GUARDED_TRAINER",
                      training_permitted=True,
                      next_action="existing_scheduler_train_if_ready")
    elif count_ready:
        result.update(status="WAITING_FOR_TEMPORAL_EVIDENCE",
                      next_action="collect_more_temporally_diverse_verified_outcomes")
    else:
        result.update(status="WAITING_FOR_VERIFIED_LABELS",
                      next_action="continue_existing_six_hour_verified_collection")
    return result


def assess(models: dict, image: dict | None = None) -> dict:
    """No tuning knobs; guardrails intentionally can't be bypassed by caller."""
    models = models if isinstance(models, dict) else {}
    entries = {name: inspect_model(name, models.get(name)) for name in ("query", "job")}
    image = image if isinstance(image, dict) else {}
    image_status = str(image.get("status") or "")[:90]
    image_wait = (image_status in (
        "", "WAITING_FOR_REVIEWED_RAW_PHOTOS",
        "WAITING_FOR_FIRST_SIX_HOUR_CYCLE", "DEFERRED_RESOURCE_BUDGET", "HOLD",
    ))
    return {
        "schema": "tcg-tablet-learning-advisor/v676",
        "mode": "READ_ONLY_NO_TRAINING",
        "models": entries,
        "image_training": {
            "status": image_status or "UNVERIFIED",
            "requires_verified_raw_photos": image_wait,
            "required_evidence": (
                "reviewed_raw_card_photo_cert_pairs_and_disjoint_holdout"
                if image_wait else "separate_model_promotion_gate_still_required"
            ),
            "training_permitted_by_advisor": False,
        },
        "automatic_accumulation": {
            "owner": "existing_single_termux_six_hour_supervisor",
            "query_job_labels": "existing_postflight_independent_outcomes_only",
            "unverified_social_candidates_are_training_labels": False,
            "legacy_unverified_labels_promoted": False,
            "fake_labels_generated": False,
            "new_scheduler_installed": False,
        },
        "all_models_auto_promoted": False,
        "physical_tablet_verified": False,
    }


def snapshot() -> dict:
    """Read model statuses; this function intentionally never invokes train_if_ready."""
    try:
        import verified_collection_neural as query
        import verified_collection_job_neural as job
        from execution.tablet_image_autonomy import run as image_status
        statuses = {"query": query.status(), "job": job.status()}
        image = image_status(train=False)
        return assess(statuses, image)
    except (OSError, ValueError, TypeError, RuntimeError, KeyError) as exc:
        return {
            "schema": "tcg-tablet-learning-advisor/v676",
            "mode": "READ_ONLY_NO_TRAINING", "status": "HOLD",
            "error_type": type(exc).__name__,
            "training_permitted": False, "physical_tablet_verified": False,
        }


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = snapshot()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 2 if result.get("status") == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
