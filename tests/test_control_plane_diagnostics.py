import pytest
from monitoring.control_plane_diagnostics import (
    DiagnosticError,
    WATCHDOG_ID,
    classify_observation,
    correlate_control_plane_mutations,
    assess_recovery_verification,
    snapshot_target,
)

CARD = "6a9b8a22e72c8191849c273e1240378e"
ANIME = "6a98ce3a84ec8191b114f98ae66ba184"
REELS = "6a9d514e332c8191b6b094259139ce6c"


def state(task_id, title, enabled=True, updated="2026-09-10T08:38:23Z", last="2026-09-10T07:34:24Z"):
    return {
        "id": task_id, "title": title, "is_enabled": enabled,
        "schedule": "stable", "timing_mode": "exact_schedule", "prompt": "stable",
        "updated_at": updated, "last_run_time": last,
    }


def test_fixed_scope_rejects_exclusions():
    with pytest.raises(DiagnosticError):
        snapshot_target(state("6a9b878f35bc8191963b8685566709c4", "카드시세분석"), observed_at="2026-09-10T08:40:00Z")


def test_pre_producer_gap_is_control_plane_unresolved():
    snap = snapshot_target(state(CARD, "인스타 카드정보"), observed_at="2026-09-10T08:40:00Z")
    result = classify_observation(snap, scheduled_slot="2026-09-10T17:30:00+09:00", slot_due=True, last_run_advanced=False, producer_status=None)
    assert result["event_class"] == "SCHEDULE_GAP_NO_PRODUCER_START"
    assert result["root_cause"] == "UNRESOLVED_CONTROL_PLANE"
    assert result["failed_stage"] == "BEFORE_PRODUCER_START"
    assert result["attribution"]["status"] == "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE"


def test_any_actor_reason_or_trace_counts_as_available_but_not_as_root_cause():
    snap = snapshot_target(state(CARD, "인스타 카드정보", enabled=False), observed_at="2026-09-10T08:40:00Z")
    result = classify_observation(snap, attribution_evidence={"error_trace": "platform-event-id=1"})
    assert result["attribution"]["status"] == "AVAILABLE"
    assert result["root_cause"] == "CONTROL_PLANE_EVIDENCE_AVAILABLE_REVIEW_REQUIRED"


def test_recovery_plan_changes_enabled_only():
    snap = snapshot_target(state(REELS, "릴스 AI 통합관리", enabled=False), observed_at="2026-09-10T08:40:00Z")
    result = classify_observation(snap)
    assert result["recovery_plan"]["allowed"] is True
    assert result["recovery_plan"]["changes"] == {"is_enabled": True}
    assert result["recovery_plan"]["source_code_auto_patch_allowed"] is False


def test_post_recovery_disable_is_regression():
    good = snapshot_target(state(ANIME, "인스타 애니정보", enabled=True), observed_at="2026-09-10T08:30:00Z")
    bad = snapshot_target(state(ANIME, "인스타 애니정보", enabled=False, updated="2026-09-10T08:45:00Z"), observed_at="2026-09-10T08:46:00Z")
    result = classify_observation(bad, post_recovery=good, recurrence_count=2)
    assert result["event_class"] == "RECOVERY_REGRESSION"


def test_correlated_mutation_is_candidate_only():
    records = []
    for task_id, title, updated in [
        (CARD, "인스타 카드정보", "2026-09-10T08:38:23Z"),
        (REELS, "릴스 AI 통합관리", "2026-09-10T08:39:50Z"),
    ]:
        snap = snapshot_target(state(task_id, title, enabled=False, updated=updated), observed_at="2026-09-10T08:40:00Z")
        records.append(classify_observation(snap))
    correlated = correlate_control_plane_mutations(records)
    assert correlated["candidate"] is True
    assert correlated["common_cause_asserted"] is False


def test_watchdog_self_snapshot_allowed_only_explicitly():
    wd = state(WATCHDOG_ID, "핵심 예약 작업 중지 감시", enabled=False)
    with pytest.raises(DiagnosticError):
        snapshot_target(wd, observed_at="2026-09-10T08:40:00Z")
    snap = snapshot_target(wd, observed_at="2026-09-10T08:40:00Z", allow_watchdog=True)
    assert snap["task_id"] == WATCHDOG_ID


def test_recovery_requires_next_real_slot():
    before = snapshot_target(state(CARD, "인스타 카드정보", enabled=False), observed_at="2026-09-10T08:40:00Z")
    immediate = snapshot_target(state(CARD, "인스타 카드정보", enabled=True, updated="2026-09-10T08:46:08Z"), observed_at="2026-09-10T08:46:09Z")
    same = snapshot_target(state(CARD, "인스타 카드정보", enabled=True, updated="2026-09-10T08:46:08Z"), observed_at="2026-09-10T08:46:10Z")
    pending = assess_recovery_verification(before=before, immediate=immediate, same_execution=same, next_slot=immediate, next_slot_executed=False)
    assert pending["recovery_verified"] is False
    done = assess_recovery_verification(before=before, immediate=immediate, same_execution=same, next_slot=immediate, next_slot_executed=True)
    assert done["recovery_verified"] is True


def test_invoked_without_matching_receipt_is_not_healthy():
    snap = snapshot_target(state(CARD, "인스타 카드정보"), observed_at="2026-09-10T09:35:00Z")
    result = classify_observation(
        snap,
        scheduled_slot="2026-09-10T18:30:00+09:00",
        slot_due=True,
        last_run_advanced=True,
        producer_status=None,
    )
    assert result["event_class"] == "RUN_INVOKED_NO_PRODUCER_RECEIPT"
    assert result["failed_stage"] == "EXCHANGE_PERSISTENCE"


def test_terminal_phase_false_flag_is_mismatch():
    snap = snapshot_target(state(CARD, "인스타 카드정보"), observed_at="2026-09-10T09:35:00Z")
    producer = {
        "scheduled_slot_kst": "2026-09-10T18:30:00+09:00",
        "phase": "VERIFIED_NO_OUTPUT",
        "terminal": False,
        "observed_at": "2026-09-10T09:31:00Z",
    }
    result = classify_observation(
        snap,
        scheduled_slot="2026-09-10T18:30:00+09:00",
        slot_due=True,
        last_run_advanced=True,
        producer_status=producer,
    )
    assert result["event_class"] == "EXCHANGE_RECEIPT_TERMINAL_MISMATCH"


def test_age_is_computed_from_receipt_when_not_supplied():
    snap = snapshot_target(state(CARD, "인스타 카드정보"), observed_at="2026-09-10T10:00:01Z")
    producer = {
        "scheduled_slot_kst": "2026-09-10T18:30:00+09:00",
        "phase": "VERIFY",
        "terminal": False,
        "observed_at": "2026-09-10T09:30:00Z",
    }
    result = classify_observation(
        snap,
        scheduled_slot="2026-09-10T18:30:00+09:00",
        slot_due=True,
        last_run_advanced=True,
        producer_status=producer,
    )
    assert result["event_class"] == "RUN_STARTED_NO_TERMINAL_RECEIPT"
    assert result["producer_status_age_seconds"] == 1801.0


def test_failure_without_direct_error_evidence_does_not_promote_root_cause():
    snap = snapshot_target(state(CARD, "인스타 카드정보"), observed_at="2026-09-10T09:35:00Z")
    producer = {
        "scheduled_slot_kst": "2026-09-10T18:30:00+09:00",
        "phase": "FAILED",
        "terminal": True,
        "observed_at": "2026-09-10T09:31:00Z",
        "root_cause": "MADE_UP",
    }
    result = classify_observation(
        snap,
        scheduled_slot="2026-09-10T18:30:00+09:00",
        slot_due=True,
        last_run_advanced=True,
        producer_status=producer,
    )
    assert result["event_class"] == "PRODUCER_REPORTED_FAILURE"
    assert result["root_cause"] == "ROOT_CAUSE_UNRESOLVED"
    assert "PRODUCER_FAILURE_EVIDENCE_INCOMPLETE" in result["auxiliary_events"]


def test_recovery_can_require_exchange_verification():
    before = snapshot_target(state(CARD, "인스타 카드정보", enabled=False), observed_at="2026-09-10T08:40:00Z")
    immediate = snapshot_target(state(CARD, "인스타 카드정보", enabled=True, updated="2026-09-10T08:46:08Z"), observed_at="2026-09-10T08:46:09Z")
    same = snapshot_target(state(CARD, "인스타 카드정보", enabled=True, updated="2026-09-10T08:46:08Z"), observed_at="2026-09-10T08:46:10Z")
    result = assess_recovery_verification(
        before=before,
        immediate=immediate,
        same_execution=same,
        next_slot=immediate,
        next_slot_executed=True,
        next_slot_exchange_verified=False,
    )
    assert result["recovery_verified"] is False
