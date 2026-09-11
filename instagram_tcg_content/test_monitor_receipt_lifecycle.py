from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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


class MonitorReceiptLifecycleTests(unittest.TestCase):
    RUN_ID = "monitor:2026-09-11T10:35:00+09:00:test"

    def _started(self, seq: int = 41):
        return build_monitor_started(
            monitor_run_id=self.RUN_ID,
            scheduled_slot_kst="2026-09-11T10:35:00+09:00",
            observed_at="2026-09-11T10:35:01+09:00",
            seq=seq,
        )

    def _final_status(self, classification: str = "HEALTHY"):
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

    def test_started_receipt_never_creates_incident(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "MONITOR_STATUS.json"
            stored = write_monitor_started(self._started(), path=path)

            self.assertEqual(stored["receipt_phase"], MONITOR_STARTED)
            self.assertEqual(stored["monitor_run_id"], self.RUN_ID)
            self.assertIs(stored["terminal"], False)
            self.assertIsNone(stored["classification"])
            self.assertIs(stored["incident_created"], False)
            self.assertFalse((root / "incidents").exists())

    def test_started_receipt_becomes_incomplete_only_after_direct_staleness(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "MONITOR_STATUS.json"
            stored = write_monitor_started(self._started(), path=path)

            in_progress = assess_monitor_receipt_completion(
                observed_at="2026-09-11T10:54:59+09:00",
                monitor_status=stored,
                stale_after=timedelta(minutes=20),
            )
            self.assertEqual(in_progress["classification"], "MONITOR_RUN_IN_PROGRESS")
            self.assertIsNone(in_progress["root_cause"])

            incomplete = assess_monitor_receipt_completion(
                observed_at="2026-09-11T10:55:01+09:00",
                monitor_status=stored,
                stale_after=timedelta(minutes=20),
            )
            self.assertEqual(incomplete["classification"], "MONITOR_RUN_INCOMPLETE")
            self.assertEqual(incomplete["root_cause"], "ROOT_CAUSE_UNRESOLVED")
            self.assertIs(incomplete["historical_backfill_allowed"], False)

    def test_final_requires_same_run_id_and_advancing_seq(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "MONITOR_STATUS.json"
            write_monitor_started(self._started(), path=path)

            with self.assertRaisesRegex(ValueError, "MONITOR_RUN_ID_MISMATCH"):
                write_monitor_final(
                    self._final_status(),
                    monitor_run_id="monitor:other",
                    seq=42,
                    path=path,
                )

            final = write_monitor_final(
                self._final_status(),
                monitor_run_id=self.RUN_ID,
                seq=42,
                path=path,
            )
            self.assertEqual(final["receipt_phase"], MONITOR_FINAL)
            self.assertEqual(final["monitor_run_id"], self.RUN_ID)
            self.assertEqual(final["seq"], 42)
            self.assertIs(final["terminal"], True)
            self.assertIs(final["incident_created"], False)

    def test_nonhealthy_incident_is_created_only_on_final(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "MONITOR_STATUS.json"
            write_monitor_started(self._started(), path=path)
            self.assertFalse((root / "incidents").exists())

            final = write_monitor_final(
                self._final_status("RUN_INVOKED_NO_PRODUCER_RECEIPT"),
                monitor_run_id=self.RUN_ID,
                seq=42,
                path=path,
            )
            self.assertIs(final["incident_created"], True)
            self.assertEqual(len(list((root / "incidents").glob("*.json"))), 1)

    def test_final_without_started_receipt_is_rejected(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "MONITOR_STATUS.json"
            with self.assertRaisesRegex(ValueError, "MONITOR_FINAL_REQUIRES_STARTED_RECEIPT"):
                write_monitor_final(
                    self._final_status(),
                    monitor_run_id="monitor:test",
                    seq=2,
                    path=path,
                )


if __name__ == "__main__":
    unittest.main()
