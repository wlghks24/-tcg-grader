#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import collection_verification_gate_contextual as gate


class CollectionVerificationContextualV257Tests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 9, 20, 0, 30, tzinfo=dt.timezone.utc)

    def _root(self, *, stat_at=None, cycle_start=None, report_start=None, report_finish=None):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        stat_at = stat_at or (self.now - dt.timedelta(minutes=25))
        cycle_start = cycle_start or (self.now - dt.timedelta(minutes=28))
        report_start = report_start or (self.now - dt.timedelta(minutes=24))
        report_finish = report_finish or (self.now - dt.timedelta(minutes=2))
        for name in gate.HEALTH_TARGETS:
            (root / name).write_text(json.dumps({"updated_at": stat_at.isoformat(), "sources": {}, "jobs": {}}), encoding="utf-8")
        results = [{"file": name, "ok": True} for name in gate.base.MANDATORY_OUTPUT_FILES]
        (root / "auto_update_report.json").write_text(json.dumps({
            "started_at": report_start.isoformat(),
            "finished_at": report_finish.isoformat(),
            "results": results,
        }), encoding="utf-8")
        (root / "tcg_live_data.json").write_text(json.dumps({
            "auto_update": {"last_run": cycle_start.isoformat()}
        }), encoding="utf-8")
        return td, root

    @staticmethod
    def _base_report(*findings):
        return {
            "schema_version": 1,
            "status": "degraded",
            "counts": {"critical": 0, "high": len(findings), "medium": 0},
            "metrics": {},
            "findings": list(findings),
        }

    def test_same_transaction_proof_replaces_only_stale_health_high(self):
        td, root = self._root()
        self.addCleanup(td.cleanup)
        stale = {"severity": "high", "code": "STALE_COLLECTION_STATE", "target": "source_collection_stats.json", "age_seconds": 1500}
        with mock.patch.object(gate.base, "verify", return_value=self._base_report(stale)):
            report = gate.verify(root, now=self.now)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["counts"]["high"], 0)
        proofs = [x for x in report["findings"] if x.get("code") == "CURRENT_COLLECTION_WINDOW_PROVEN"]
        self.assertEqual(len(proofs), 1)
        self.assertFalse(report["contextual_freshness"]["threshold_widened"])

    def test_unrelated_high_is_never_removed(self):
        td, root = self._root()
        self.addCleanup(td.cleanup)
        stale = {"severity": "high", "code": "STALE_COLLECTION_STATE", "target": "source_collection_stats.json", "age_seconds": 1500}
        other = {"severity": "high", "code": "HARD_COLLECTION_FAILURE", "target": "market_prices.json"}
        with mock.patch.object(gate.base, "verify", return_value=self._base_report(stale, other)):
            report = gate.verify(root, now=self.now)
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["counts"]["high"], 1)
        self.assertTrue(any(x.get("code") == "HARD_COLLECTION_FAILURE" for x in report["findings"]))

    def test_health_timestamp_before_cycle_remains_degraded(self):
        td, root = self._root(stat_at=self.now - dt.timedelta(hours=3))
        self.addCleanup(td.cleanup)
        stale = {"severity": "high", "code": "STALE_COLLECTION_STATE", "target": "source_collection_stats.json", "age_seconds": 10800}
        with mock.patch.object(gate.base, "verify", return_value=self._base_report(stale)):
            report = gate.verify(root, now=self.now)
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["counts"]["high"], 1)

    def test_old_completed_report_cannot_extend_health_freshness(self):
        td, root = self._root(
            stat_at=self.now - dt.timedelta(hours=3, minutes=20),
            cycle_start=self.now - dt.timedelta(hours=3, minutes=25),
            report_start=self.now - dt.timedelta(hours=3, minutes=18),
            report_finish=self.now - dt.timedelta(hours=3),
        )
        self.addCleanup(td.cleanup)
        stale = {"severity": "high", "code": "STALE_COLLECTION_STATE", "target": "source_collection_stats.json", "age_seconds": 12000}
        with mock.patch.object(gate.base, "verify", return_value=self._base_report(stale)):
            report = gate.verify(root, now=self.now)
        self.assertEqual(report["status"], "degraded")

    def test_incomplete_mandatory_report_cannot_prove_transaction(self):
        td, root = self._root()
        self.addCleanup(td.cleanup)
        report = json.loads((root / "auto_update_report.json").read_text(encoding="utf-8"))
        report["results"] = report["results"][:-1]
        (root / "auto_update_report.json").write_text(json.dumps(report), encoding="utf-8")
        stale = {"severity": "high", "code": "STALE_COLLECTION_STATE", "target": "adaptive_collection_stats.json", "age_seconds": 1500}
        with mock.patch.object(gate.base, "verify", return_value=self._base_report(stale)):
            checked = gate.verify(root, now=self.now)
        self.assertEqual(checked["status"], "degraded")


if __name__ == "__main__":
    unittest.main()
