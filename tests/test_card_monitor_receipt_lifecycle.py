from datetime import timedelta

import pytest

from instagram_tcg_content.monitor_receipt_lifecycle import (
    MONITOR_FINAL,
    MONITOR_STARTED,
    assess_monitor_receipt_completion,
    build_monitor_started,
    write_monitor_final,
    write_monitor_started,
)
from instagram_tcg_content.pause_monitor_exchange import (
    MONITOR_TASK_ID,
    PROJECT,
    SCHEMA_VERSION,
    TASK_ID,
)


def _started(run_id: str, seq: int = 41):
    return build_monitor_started(
        monitor_run_id=run_id,
        scheduled_slot_kst="2026-09-11T10:35:00+09:00",
        observed_at="2026-09-11T10:35:01+09:00",
        seq=seq,
    )


def _final_status(classification: str = "HEALTHY"):
    return {
        "schema_version": SCHEMA_VERSION,
        "project": PROJECT,
        "task_id": TASK_ID,
        "monitor_task_id": MONITOR_TASK_ID,
        "scheduled_slot_kst": "2026-09-11T10:35:00+09:00",
        "observed_at": "2026-09-11T10:35:08+09:00",
        "classification": classification,
        "failed_stage": None,
        "root_cause": None,
    }


def test_started_receipt_never_creates_incident(tmp_path):
    path = tmp_path / "MONITOR_STATUS.json"
    run_id = "monitor:2026-09-11T10:35:00+09:00:test"
    stored = write_monitor_started(_started(run_id), path=path)

    assert stored["receipt_phase"] == MONITOR_STARTED
    assert stored["monitor_run_id"] == run_id
    assert stored["terminal"] is False
    assert stored["classification"] is None
    assert stored["incident_created"] is False
    assert not (tmp_path / "incidents").exists()


def test_started_receipt_becomes_incomplete_only_after_direct_staleness(tmp_path):
    path = tmp_path / "MONITOR_STATUS.json"
    run_id = "monitor:2026-09-11T10:35:00+09:00:test"
    stored = write_monitor_started(_started(run_id), path=path)

    in_progress = assess_monitor_receipt_completion(
        observed_at="2026-09-11T10:54:59+09:00",
        monitor_status=stored,
        stale_after=timedelta(minutes=20),
    )
    assert in_progress["classification"] == "MONITOR_RUN_IN_PROGRESS"
    assert in_progress["root_cause"] is None

    incomplete = assess_monitor_receipt_completion(
        observed_at="2026-09-11T10:55:01+09:00",
        monitor_status=stored,
        stale_after=timedelta(minutes=20),
    )
    assert incomplete["classification"] == "MONITOR_RUN_INCOMPLETE"
    assert incomplete["root_cause"] == "ROOT_CAUSE_UNRESOLVED"
    assert incomplete["historical_backfill_allowed"] is False


def test_final_requires_same_run_id_and_advancing_seq(tmp_path):
    path = tmp_path / "MONITOR_STATUS.json"
    run_id = "monitor:2026-09-11T10:35:00+09:00:test"
    write_monitor_started(_started(run_id), path=path)

    with pytest.raises(ValueError, match="MONITOR_RUN_ID_MISMATCH"):
        write_monitor_final(
            _final_status(),
            monitor_run_id="monitor:other",
            seq=42,
            path=path,
        )

    final = write_monitor_final(
        _final_status(),
        monitor_run_id=run_id,
        seq=42,
        path=path,
    )
    assert final["receipt_phase"] == MONITOR_FINAL
    assert final["monitor_run_id"] == run_id
    assert final["seq"] == 42
    assert final["terminal"] is True
    assert final["incident_created"] is False


def test_nonhealthy_incident_is_created_only_on_final(tmp_path):
    path = tmp_path / "MONITOR_STATUS.json"
    run_id = "monitor:2026-09-11T10:35:00+09:00:test"
    write_monitor_started(_started(run_id), path=path)
    assert not (tmp_path / "incidents").exists()

    final = write_monitor_final(
        _final_status("RUN_INVOKED_NO_PRODUCER_RECEIPT"),
        monitor_run_id=run_id,
        seq=42,
        path=path,
    )
    assert final["incident_created"] is True
    incidents = list((tmp_path / "incidents").glob("*.json"))
    assert len(incidents) == 1


def test_final_without_started_receipt_is_rejected(tmp_path):
    path = tmp_path / "MONITOR_STATUS.json"
    with pytest.raises(ValueError, match="MONITOR_FINAL_REQUIRES_STARTED_RECEIPT"):
        write_monitor_final(
            _final_status(),
            monitor_run_id="monitor:test",
            seq=2,
            path=path,
        )
