#!/usr/bin/env python3
"""Regression: historical pause evidence must not be labeled as a live pause."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_reliability_v8.diagnostics import EvidenceLog


ROOT = Path(__file__).resolve().parents[1]


class SchedulerSnapshotAttributionTests(unittest.TestCase):
    def test_mirrored_diagnostics_have_identical_code(self):
        canonical = (ROOT / "ai_reliability_v8" / "diagnostics.py").read_bytes()
        mirrored = (ROOT / "tcg_reliability" / "ai_reliability_v8" / "diagnostics.py").read_bytes()
        self.assertEqual(canonical, mirrored)

    def test_latest_snapshot_only_controls_pause_attribution(self):
        with tempfile.TemporaryDirectory() as folder:
            log = EvidenceLog(Path(folder), project="tcg_grader", task_id="test-snapshot")
            self.assertIsNone(log.diagnose()["scheduler"]["current_enabled"])

            log.snapshot({
                "id": "test-snapshot", "is_enabled": False, "updated_at": "v1",
                "pause_actor": "scheduler", "pause_reason": "audit-backed-pause",
                "audit_reference": "audit-1",
            }, foreground=True)
            first = log.diagnose()["scheduler"]
            self.assertFalse(first["current_enabled"])
            self.assertEqual(first["cause"], "AUDIT_ATTRIBUTED")
            self.assertEqual(first["audit_reference"], "audit-1")

            log.snapshot({"id": "test-snapshot", "is_enabled": True, "updated_at": "v2"}, foreground=True)
            resumed = log.diagnose()["scheduler"]
            self.assertTrue(resumed["current_enabled"])
            self.assertEqual(resumed["cause"], "ENABLED_AT_LAST_SNAPSHOT")
            self.assertIn("historical_disabled_observed_at", resumed)
            self.assertNotIn("actor", resumed)
            self.assertNotIn("reason", resumed)
            self.assertNotIn("audit_reference", resumed)
            self.assertNotIn("disabled_observed_at", resumed)
            self.assertFalse(resumed["runtime_error_is_pause_proof"])

            # New disabled observation without a new host audit must not
            # inherit the historical attribution (nor claim causal certainty).
            log.snapshot({"id": "test-snapshot", "is_enabled": False, "updated_at": "v3"}, foreground=True)
            new_pause = log.diagnose()["scheduler"]
            self.assertFalse(new_pause["current_enabled"])
            self.assertEqual(new_pause["cause"], "UNRESOLVED")
            self.assertIn("platform_audit_reference", new_pause["missing_evidence"])
            self.assertNotIn("audit_reference", new_pause)
            self.assertNotIn("actor", new_pause)

            # Fresh audited evidence may attribute only this latest pause.
            log.snapshot({
                "id": "test-snapshot", "is_enabled": False, "updated_at": "v4",
                "pause_actor": "scheduler", "pause_reason": "new-audited-pause",
                "audit_reference": "audit-4",
            }, foreground=True)
            last = log.diagnose()["scheduler"]
            self.assertEqual(last["cause"], "AUDIT_ATTRIBUTED")
            self.assertEqual(last["audit_reference"], "audit-4")
            self.assertEqual(last["reason"], "new-audited-pause")


if __name__ == "__main__":
    unittest.main()
