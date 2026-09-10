#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

from instagram_tcg_content.pause_monitor_exchange import (
    MONITOR_TASK_ID,
    PROJECT,
    TASK_ID,
    build_producer_ack,
    build_producer_status,
    classify_monitor_observation,
    write_monitor_status,
    write_producer_ack,
    write_producer_status,
)


class PauseMonitorExchangeTests(unittest.TestCase):
    def test_schedule_gap_without_producer_start_is_control_plane_only(self):
        result = classify_monitor_observation(
            scheduled_slot_kst="2026-09-11T08:00:00+09:00",
            observed_at="2026-09-11T08:06:00+09:00",
            is_enabled=True,
            last_run_time="2026-09-11T07:00:03+09:00",
            producer_status=None,
        )
        self.assertEqual(result["classification"], "SCHEDULE_GAP_NO_PRODUCER_START")
        self.assertEqual(result["failed_stage"], "BEFORE_PRODUCER_START")
        self.assertEqual(result["root_cause"], "UNRESOLVED_CONTROL_PLANE")
        self.assertEqual(result["attribution"], "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE")
        self.assertTrue(result["repair_handoff"]["control_plane_event"])
        self.assertFalse(result["repair_handoff"]["auto_run_level_repair_allowed"])
        self.assertFalse(result["mandatory_reporting_slot"])

    def test_invoked_collection_run_without_receipt_is_not_healthy_but_not_production_report_slot(self):
        result = classify_monitor_observation(
            scheduled_slot_kst="2026-09-11T10:00:00+09:00",
            observed_at="2026-09-11T10:06:00+09:00",
            is_enabled=True,
            last_run_time="2026-09-11T10:00:33+09:00",
            producer_status=None,
        )
        self.assertEqual(result["classification"], "RUN_INVOKED_NO_PRODUCER_RECEIPT")
        self.assertEqual(result["failed_stage"], "EXCHANGE_PERSISTENCE")
        self.assertEqual(result["root_cause"], "ROOT_CAUSE_UNRESOLVED")
        self.assertFalse(result["mandatory_reporting_slot"])
        self.assertEqual(
            result["repair_handoff"]["recommended_action"],
            "VERIFY_EXCHANGE_PERSISTENCE_AND_FORCE_VISIBLE_STATUS_REPORT",
        )

    def test_monday_1900_is_only_mandatory_production_reporting_slot(self):
        result = classify_monitor_observation(
            scheduled_slot_kst="2026-09-14T19:00:00+09:00",
            observed_at="2026-09-14T19:06:00+09:00",
            is_enabled=True,
            last_run_time="2026-09-14T19:00:33+09:00",
            producer_status=None,
        )
        self.assertTrue(result["mandatory_reporting_slot"])

    def test_reported_producer_failure_allows_only_run_level_handoff(self):
        status = build_producer_status(
            run_id="r1",
            scheduled_slot_kst="2026-09-11T08:00:00+09:00",
            phase="FAILED",
            seq=3,
            observed_at="2026-09-11T08:04:00+09:00",
            code_version="single-router",
            failed_stage="VERIFY",
            error_code="CONFLICT",
            evidence="two independent sources disagree",
        )
        result = classify_monitor_observation(
            scheduled_slot_kst="2026-09-11T08:00:00+09:00",
            observed_at="2026-09-11T08:08:00+09:00",
            is_enabled=True,
            last_run_time="2026-09-11T08:00:30+09:00",
            producer_status=status,
        )
        self.assertEqual(result["classification"], "PRODUCER_REPORTED_FAILURE")
        self.assertTrue(result["repair_handoff"]["auto_run_level_repair_allowed"])
        self.assertFalse(result["repair_handoff"]["source_code_auto_patch_allowed"])
        self.assertFalse(result["repair_handoff"]["control_plane_event"])

    def test_verified_delivery_then_disabled_is_post_run_control_plane_event(self):
        status = build_producer_status(
            run_id="r2",
            scheduled_slot_kst="2026-09-14T19:00:00+09:00",
            phase="VERIFIED_DELIVERY",
            seq=10,
            observed_at="2026-09-14T19:04:00+09:00",
            code_version="single-router",
            delivery_reference="attachment://six",
            artifact_count=6,
        )
        result = classify_monitor_observation(
            scheduled_slot_kst="2026-09-14T19:00:00+09:00",
            observed_at="2026-09-14T19:08:00+09:00",
            is_enabled=False,
            last_run_time="2026-09-14T19:00:30+09:00",
            producer_status=status,
        )
        self.assertEqual(result["classification"], "POST_RUN_DISABLE")
        self.assertTrue(result["repair_handoff"]["control_plane_event"])

    def test_single_writer_paths_and_monotonic_sequences(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            producer = root / "PRODUCER_STATUS.json"
            ack_path = root / "PRODUCER_ACK.json"
            monitor = root / "MONITOR_STATUS.json"
            p1 = build_producer_status(
                run_id="r1",
                scheduled_slot_kst="2026-09-11T08:00:00+09:00",
                phase="STARTED",
                seq=1,
                observed_at="2026-09-11T08:00:01+09:00",
                code_version="single-router",
            )
            write_producer_status(p1, producer)
            with self.assertRaisesRegex(ValueError, "PRODUCER_SEQ_NOT_ADVANCING"):
                write_producer_status(p1, producer)
            monitor_row = classify_monitor_observation(
                scheduled_slot_kst="2026-09-11T08:00:00+09:00",
                observed_at="2026-09-11T08:08:00+09:00",
                is_enabled=True,
                last_run_time="2026-09-11T08:00:30+09:00",
                producer_status=p1,
            )
            written = write_monitor_status(monitor_row, seq=1, path=monitor)
            self.assertEqual(written["monitor_task_id"], MONITOR_TASK_ID)
            with self.assertRaisesRegex(ValueError, "MONITOR_SEQ_NOT_ADVANCING"):
                write_monitor_status(monitor_row, seq=1, path=monitor)
            ack = build_producer_ack(
                run_id="r1", monitor_status=written,
                observed_at="2026-09-11T08:09:00+09:00",
                action_taken="NO_PATCH_CONTROL_PLANE_EVENT",
            )
            stored_ack = write_producer_ack(ack, ack_path)
            self.assertEqual(stored_ack["project"], PROJECT)
            self.assertEqual(stored_ack["task_id"], TASK_ID)
            self.assertEqual(stored_ack["monitor_seq_seen"], 1)


if __name__ == "__main__":
    unittest.main()
