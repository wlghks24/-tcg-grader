from instagram_tcg_content import root_cause_diagnostics as d

SLOT = "2026-09-10T19:00:00+09:00"
NOW = "2026-09-10T10:25:00Z"


def status(phase="STARTED", terminal=False, seq=1, observed="2026-09-10T10:00:01Z", run_id="r1"):
    return {
        "schema_version": d.PRODUCER_SCHEMA,
        "project": d.PROJECT,
        "task_id": d.TASK_ID,
        "scheduled_slot_kst": SLOT,
        "run_id": run_id,
        "phase": phase,
        "terminal": terminal,
        "seq": seq,
        "observed_at": observed,
        "failed_stage": None,
        "error_code": None,
        "root_cause": None,
        "evidence": {},
    }


def test_no_start_gap():
    r = d.diagnose(scheduled_slot_kst=SLOT, observed_at=NOW, is_enabled=True,
                   last_run_time="2026-09-10T09:59:00Z", producer_status=None)
    assert r["event_class"] == "SCHEDULE_GAP_NO_PRODUCER_START"


def test_invoked_without_receipt():
    r = d.diagnose(scheduled_slot_kst=SLOT, observed_at=NOW, is_enabled=True,
                   last_run_time="2026-09-10T10:01:00Z", producer_status=None)
    assert r["event_class"] == "RUN_INVOKED_NO_PRODUCER_RECEIPT"


def test_stale_started():
    r = d.diagnose(scheduled_slot_kst=SLOT, observed_at=NOW, is_enabled=True,
                   last_run_time="2026-09-10T10:01:00Z", producer_status=status())
    assert r["event_class"] == "RUN_STARTED_NO_TERMINAL_RECEIPT"


def test_terminal_mismatch():
    s = status(phase="VERIFIED_DELIVERY", terminal=False, observed="2026-09-10T10:24:00Z")
    r = d.diagnose(scheduled_slot_kst=SLOT, observed_at=NOW, is_enabled=True,
                   last_run_time="2026-09-10T10:01:00Z", producer_status=s)
    assert r["event_class"] == "EXCHANGE_RECEIPT_TERMINAL_MISMATCH"


def test_trace_seq_regression():
    history = [
        status(seq=2, observed="2026-09-10T10:00:01Z"),
        status(phase="VERIFY", seq=1, observed="2026-09-10T10:00:02Z"),
    ]
    r = d.diagnose(scheduled_slot_kst=SLOT, observed_at=NOW, is_enabled=True,
                   last_run_time="2026-09-10T10:01:00Z", producer_status=history[-1], producer_history=history)
    assert r["event_class"] == "EXCHANGE_TRACE_INTEGRITY_FAILURE"
    assert "TRACE_SEQ_NOT_MONOTONIC" in r["trace_anomalies"]


def test_event_id_is_attribution_evidence_not_root_truth():
    r = d.diagnose(scheduled_slot_kst=SLOT, observed_at=NOW, is_enabled=False,
                   last_run_time="2026-09-10T09:59:00Z", producer_status=None, event_id="evt-1")
    assert r["attribution"]["status"] == "AVAILABLE"
    assert r["root_cause"] == "CONTROL_PLANE_EVIDENCE_AVAILABLE_REVIEW_REQUIRED"


def test_timezone_same_instant():
    assert d.same_instant("2026-09-10T19:00:00+09:00", "2026-09-10T10:00:00Z")


def test_reverse_order_history_supported():
    newest = status(phase="VERIFIED_DELIVERY", terminal=True, seq=3, observed="2026-09-10T10:00:03Z")
    middle = status(phase="VERIFY", terminal=False, seq=2, observed="2026-09-10T10:00:02Z")
    start = status(seq=1, observed="2026-09-10T10:00:01Z")
    filler = [
        {"project": "other", "task_id": "x", "scheduled_slot_kst": "2026-01-01T00:00:00Z", "seq": i}
        for i in range(100)
    ]
    history = [newest, middle, start] + filler
    trace = d.inspect_trace_chain(history, scheduled_slot_kst=SLOT, observed_at=NOW)
    assert trace["matched"] == 3
    assert trace["status"] == "CONSISTENT"
