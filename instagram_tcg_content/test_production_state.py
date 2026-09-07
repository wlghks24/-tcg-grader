#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from instagram_tcg_content.production_state import (
    SCHEDULED_BASELINE_RUN_KIND,
    USER_REQUESTED_RECOVERY_RUN_KIND,
    StateIntegrityError,
    acquire_run_lock,
    baseline_id_for_date,
    can_start_catchup,
    can_start_user_requested_recovery,
    empty_state,
    finalize_production,
    load_state,
    record_blocked_production_attempt,
    record_catchup_attempt,
    release_run_lock,
    validate_production_record,
    write_state_atomic,
)


def record(run_kind=SCHEDULED_BASELINE_RUN_KIND, baseline_id="IG-20260906-1030"):
    value = {
        "production_date_kst": "2026-09-06",
        "scheduled_slot_kst": "2026-09-06T10:30:00+09:00",
        "actual_started_at_kst": "2026-09-06T10:30:03+09:00",
        "router_branch": "DAILY_PRODUCTION",
        "run_kind": run_kind,
        "snapshot_id": "snapshot-1",
        "schema_version": 1,
        "payload_hashes": [f"payload-{i}" for i in range(6)],
        "artifact_hashes": [f"artifact-{i}" for i in range(6)],
        "dimensions": [[1080, 1350] for _ in range(6)],
        "caption_hash": "caption",
        "hashtag_hash": "hashtags",
        "x10_status": "pass",
        "delivery_reference_status": "verified",
        "finalized_at": "2026-09-06T10:31:00+09:00",
    }
    if baseline_id is not None:
        value["baseline_id"] = baseline_id
    return value


def main():
    state = empty_state()

    ok, lock_key = acquire_run_lock(
        state,
        production_date_kst="2026-09-06",
        scheduled_slot_kst="2026-09-06T10:30:00+09:00",
        router_branch="DAILY_PRODUCTION",
        run_id="run-1",
    )
    assert ok

    ok, reason = acquire_run_lock(
        state,
        production_date_kst="2026-09-06",
        scheduled_slot_kst="2026-09-06T10:30:00+09:00",
        router_branch="DAILY_PRODUCTION",
        run_id="run-2",
    )
    assert not ok and reason == "DUPLICATE_RUN_SUPPRESSED"

    release_run_lock(state, lock_key, status="completed")

    ok, reason = acquire_run_lock(
        state,
        production_date_kst="2026-09-06",
        scheduled_slot_kst="2026-09-06T10:30:00+09:00",
        router_branch="DAILY_PRODUCTION",
        run_id="run-3",
    )
    assert not ok and reason == "DUPLICATE_RUN_SUPPRESSED"

    good = record()
    assert validate_production_record(good) == []
    finalize_production(state, good)
    assert baseline_id_for_date(state, "2026-09-06") == "IG-20260906-1030"

    allowed, reason = can_start_catchup(state, "2026-09-06")
    assert not allowed and reason == "FINALIZED_PRODUCTION_ALREADY_EXISTS"

    catchup = record(run_kind="catchup", baseline_id="illegal")
    errors = validate_production_record(catchup)
    assert "non-10:30 run cannot create baseline_id" in errors

    missing_baseline = record(baseline_id=None)
    errors = validate_production_record(missing_baseline)
    assert "10:30 scheduled run requires baseline_id" in errors

    fresh = empty_state()
    allowed, reason = can_start_catchup(fresh, "2026-09-07")
    assert allowed and reason == "CATCHUP_ALLOWED"
    assert record_catchup_attempt(fresh, "2026-09-07") == 1
    allowed, reason = can_start_catchup(fresh, "2026-09-07")
    assert not allowed and reason == "CATCHUP_BUDGET_EXHAUSTED"

    blocked = empty_state()
    row = record_blocked_production_attempt(
        blocked,
        production_date_kst="2026-09-07",
        scheduled_slot_kst="2026-09-07T10:30:00+09:00",
        reason_code="INSUFFICIENT_VERIFIED_FACTS",
        verified_fact_count=1,
        recorded_at_kst="2026-09-07T15:15:00+09:00",
        detail="6 required artifacts could not be supported by one verified fact",
    )
    assert row["verified_fact_count"] == 1

    allowed, reason = can_start_user_requested_recovery(
        blocked,
        "2026-09-07",
        user_requested=False,
    )
    assert not allowed and reason == "USER_REQUEST_REQUIRED"

    allowed, reason = can_start_user_requested_recovery(
        blocked,
        "2026-09-07",
        user_requested=True,
    )
    assert allowed and reason == "USER_REQUESTED_RECOVERY_ALLOWED"

    recovery = record(
        run_kind=USER_REQUESTED_RECOVERY_RUN_KIND,
        baseline_id=None,
    )
    recovery["scheduled_slot_kst"] = "2026-09-07T15:30:00+09:00"
    recovery["actual_started_at_kst"] = "2026-09-07T15:30:03+09:00"
    recovery["finalized_at"] = "2026-09-07T15:31:00+09:00"
    recovery["production_date_kst"] = "2026-09-07"
    recovery["recovery_of_slot_kst"] = "2026-09-07T10:30:00+09:00"
    recovery["recovery_request_evidence"] = "user requested missing artifact recovery in canonical chat"
    assert validate_production_record(recovery) == []

    missing_recovery_evidence = dict(recovery)
    missing_recovery_evidence["recovery_request_evidence"] = ""
    assert (
        "user-requested recovery requires recovery_request_evidence"
        in validate_production_record(missing_recovery_evidence)
    )

    record_catchup_attempt(blocked, "2026-09-07")
    allowed, reason = can_start_user_requested_recovery(
        blocked,
        "2026-09-07",
        user_requested=True,
    )
    assert not allowed and reason == "CATCHUP_BUDGET_EXHAUSTED"

    duplicate_artifact = record()
    duplicate_artifact["artifact_hashes"][5] = duplicate_artifact["artifact_hashes"][4]
    assert "artifact_hashes must be unique" in validate_production_record(duplicate_artifact)

    wrong_size = record()
    wrong_size["dimensions"][2] = [1080, 1080]
    assert "all artifacts must be 1080x1350" in validate_production_record(wrong_size)

    malformed_size = record()
    malformed_size["dimensions"][1] = "1080x1350"
    assert "all artifacts must be 1080x1350" in validate_production_record(malformed_size)

    # Finalized records are immutable.
    try:
        finalize_production(state, record())
        raise AssertionError("finalized production overwrite was not blocked")
    except RuntimeError as exc:
        assert str(exc) == "FINALIZED_PRODUCTION_ALREADY_EXISTS"

    bad_x10 = record()
    bad_x10["x10_status"] = "failed"
    assert "x10_status must be pass" in validate_production_record(bad_x10)

    bad_delivery = record()
    bad_delivery["delivery_reference_status"] = "pending"
    assert "delivery_reference_status must be verified" in validate_production_record(bad_delivery)

    bad_caption = record()
    bad_caption["caption_hash"] = ""
    assert "caption_hash missing" in validate_production_record(bad_caption)

    bad_hashtag = record()
    bad_hashtag["hashtag_hash"] = None
    assert "hashtag_hash missing" in validate_production_record(bad_hashtag)

    naive_time = record()
    naive_time["actual_started_at_kst"] = "2026-09-06T10:30:03"
    assert (
        "actual_started_at_kst must be timezone-aware ISO-8601"
        in validate_production_record(naive_time)
    )

    wrong_schema = record()
    wrong_schema["schema_version"] = 999
    assert "schema_version mismatch" in validate_production_record(wrong_schema)

    # Missing state is a valid first-run case, but existing corrupt state fails closed.
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "production-state.json"
        assert load_state(path) == empty_state()

        write_state_atomic(path, empty_state())
        assert load_state(path) == empty_state()

        path.write_text("{broken-json", encoding="utf-8")
        try:
            load_state(path)
            raise AssertionError("corrupt JSON was silently reset")
        except StateIntegrityError as exc:
            assert str(exc) == "STATE_CORRUPT_JSON"

        path.write_text('{"schema_version":999}', encoding="utf-8")
        try:
            load_state(path)
            raise AssertionError("schema mismatch was silently reset")
        except StateIntegrityError as exc:
            assert str(exc) == "STATE_SCHEMA_MISMATCH"

        malformed_lock = empty_state()
        malformed_lock["run_locks"]["slot"] = "broken"
        write_state_atomic(path, malformed_lock)
        try:
            load_state(path)
            raise AssertionError("malformed nested lock failed open")
        except StateIntegrityError as exc:
            assert str(exc) == "STATE_RUN_LOCK_INVALID"

        malformed_block = empty_state()
        malformed_block["blocked_attempts"]["2026-09-07"] = {
            "production_date_kst": "2026-09-07",
            "scheduled_slot_kst": "2026-09-07T10:30:00+09:00",
            "reason_code": "INVENTED_REASON",
            "verified_fact_count": 1,
            "recorded_at_kst": "2026-09-07T15:15:00+09:00",
        }
        write_state_atomic(path, malformed_block)
        try:
            load_state(path)
            raise AssertionError("malformed blocked attempt failed open")
        except StateIntegrityError as exc:
            assert str(exc) == "STATE_BLOCKED_ATTEMPT_INVALID"

        malformed_budget = empty_state()
        malformed_budget["catchup_attempts"]["2026-09-07"] = -1
        write_state_atomic(path, malformed_budget)
        try:
            load_state(path)
            raise AssertionError("malformed catchup budget failed open")
        except StateIntegrityError as exc:
            assert str(exc) == "STATE_CATCHUP_BUDGET_INVALID"

    print("Instagram TCG production state regression: PASS")


if __name__ == "__main__":
    main()
