from instagram_tcg_content import root_cause_diagnostics as diag


def _status(slot, phase="STARTED", terminal=False, observed="2026-09-10T09:00:00Z", **kw):
    data={"schema_version":diag.PRODUCER_SCHEMA,"project":diag.PROJECT,"task_id":diag.TASK_ID,"scheduled_slot_kst":slot,"phase":phase,"terminal":terminal,"observed_at":observed,"seq":1,"failed_stage":None,"error_code":None,"root_cause":None,"evidence":None}
    data.update(kw); return data


def test_schedule_gap_and_active():
    r=diag.diagnose(scheduled_slot_kst="2026-09-10T18:30:00+09:00",observed_at="2026-09-10T18:40:00+09:00",is_enabled=True,last_run_time="2026-09-10T08:00:00Z",producer_status=None)
    assert r["event_class"]=="SCHEDULE_GAP_NO_PRODUCER_START"
    assert "SCHEDULE_GAP_ACTIVE" in r["auxiliary_events"]


def test_invoked_without_receipt_not_healthy():
    r=diag.diagnose(scheduled_slot_kst="2026-09-10T18:30:00+09:00",observed_at="2026-09-10T18:40:00+09:00",is_enabled=True,last_run_time="2026-09-10T09:31:00Z",producer_status=None)
    assert r["event_class"]=="RUN_INVOKED_NO_PRODUCER_RECEIPT"


def test_timezone_equivalent_slot_and_stale_phase():
    s=_status("2026-09-10T09:30:00Z",phase="VERIFY",terminal=False,observed="2026-09-10T09:31:00Z")
    r=diag.diagnose(scheduled_slot_kst="2026-09-10T18:30:00+09:00",observed_at="2026-09-10T18:52:00+09:00",is_enabled=True,last_run_time="2026-09-10T09:31:00Z",producer_status=s)
    assert r["producer_status_present"] is True
    assert r["event_class"]=="RUN_STARTED_NO_TERMINAL_RECEIPT"


def test_terminal_mismatch_detected():
    slot="2026-09-10T18:30:00+09:00"
    s=_status(slot,phase="VERIFIED_NO_OUTPUT",terminal=False,observed="2026-09-10T09:31:00Z")
    r=diag.diagnose(scheduled_slot_kst=slot,observed_at="2026-09-10T18:40:00+09:00",is_enabled=True,last_run_time="2026-09-10T09:31:00Z",producer_status=s)
    assert r["event_class"]=="EXCHANGE_RECEIPT_TERMINAL_MISMATCH"


def test_failure_root_requires_direct_evidence():
    slot="2026-09-10T18:30:00+09:00"
    s=_status(slot,phase="BLOCKED",terminal=True,root_cause="UNVERIFIED_GUESS")
    r=diag.diagnose(scheduled_slot_kst=slot,observed_at="2026-09-10T18:40:00+09:00",is_enabled=True,last_run_time="2026-09-10T09:31:00Z",producer_status=s)
    assert r["root_cause"]=="ROOT_CAUSE_UNRESOLVED"
    assert "PRODUCER_FAILURE_EVIDENCE_INCOMPLETE" in r["auxiliary_events"]


def test_direct_failure_evidence_can_resolve_root():
    slot="2026-09-10T18:30:00+09:00"
    s=_status(slot,phase="FAILED",terminal=True,failed_stage="OUTPUT_VALIDATION",error_code="PIXEL_MISMATCH",root_cause="PIXEL_FORMAT_MISMATCH",evidence={"actual":"rgb24"})
    r=diag.diagnose(scheduled_slot_kst=slot,observed_at="2026-09-10T18:40:00+09:00",is_enabled=True,last_run_time="2026-09-10T09:31:00Z",producer_status=s)
    assert r["root_cause"]=="PIXEL_FORMAT_MISMATCH"
    assert r["evidence_tier"]=="DIRECT"


def test_schema_mismatch_detected():
    slot="2026-09-10T18:30:00+09:00"
    s=_status(slot,phase="VERIFY",terminal=False); s["schema_version"]="old"
    r=diag.diagnose(scheduled_slot_kst=slot,observed_at="2026-09-10T18:40:00+09:00",is_enabled=True,last_run_time="2026-09-10T09:31:00Z",producer_status=s)
    assert r["event_class"]=="EXCHANGE_CONTRACT_VERSION_MISMATCH"
