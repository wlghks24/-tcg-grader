#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory

from instagram_tcg_content.production_state import (
    SCHEDULED_BASELINE_RUN_KIND,
    StateIntegrityError,
    acquire_run_lock,
    baseline_id_for_date,
    can_start_catchup,
    empty_state,
    finalize_production,
    load_state,
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

    print("Instagram TCG production state regression: PASS")


if __name__ == "__main__":
    main()
