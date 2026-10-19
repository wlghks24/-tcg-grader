"""V655: cross-layer local collection/log correspondence is never neural evidence."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from execution.tablet_autonomy_collection_receipts_v653 import NAME, capture
from execution.tablet_autonomy_evidence_journal_v654 import OUTPUT_NAME, record

class CollectorLogCorrelationV655Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.state = self.base / "state"
        self.state.mkdir()
        (self.state / "logs").mkdir()
        self.receipts = self.state / "collection-evidence-v653"
        self.receipts.mkdir()
        self.log = self.state / "logs" / "autonomy-20261019-230000.log"
        self.log.write_text(
            "precheck ok\n" +
            json.dumps({"v400_status": "V400_UPSTREAM_HOLD",
                        "execution": {"executed": False},
                        "v387_uncertainty_policy": {"selected_action": "TRAIN_QUERY_STRATEGY",
                                                    "selected_confidence": 0.3852}}) + "\n",
            encoding="utf-8"
        )
        self.sha = "a" * 40
        self.finished = datetime.now(timezone.utc) - timedelta(minutes=2)
        self.write_collector()

    def write_collector(self):
        end = self.finished
        start = end - timedelta(minutes=5)
        jobs = []
        for name in ("market_prices.json", "market_watch.json"):
            payload = {"updated_at": end.isoformat(), "collection_errors": [],
                       "collection_status": "정상"}
            if name == "market_prices.json":
                payload["entries"] = {"test": {"price": 3}}
            else:
                payload["items"] = []
            (self.root / name).write_text(json.dumps(payload), encoding="utf-8")
            jobs.append({"file": name, "ok": True, "updated_at": end.isoformat(),
                         "collection_errors": [], "remaining_collection_errors": []})
        report = {
            "started_at": start.isoformat(), "finished_at": end.isoformat(),
            "trigger": "scheduled-v655", "ok": True,
            "failure_count": 0, "degraded_count": 0, "fresh_failure_count": 0,
            "results": jobs, "postflight_monitor": {
                "ok": True, "results": [{"file": x["file"], "ok": True} for x in jobs]
            }
        }
        (self.root / "auto_update_report.json").write_text(json.dumps(report), encoding="utf-8")

    def take_receipt(self):
        out = capture(self.root, self.receipts, now=datetime.now(timezone.utc))
        self.assertEqual("OBSERVATION_RECORDED_NOT_VERIFIED", out["status"])

    def invoke(self, *, root=True):
        return record(self.state, self.log, self.sha, "EVIDENCE_BOOTSTRAP_HOLD",
                      root=self.root if root else None)

    def last(self):
        return json.loads((self.state / OUTPUT_NAME).read_text())["observations"][-1]

    def test_correlated_real_bytes_are_still_unverified(self):
        self.take_receipt()
        result = self.invoke()
        self.assertEqual("OBSERVATION_RECORDED_UNVERIFIED", result["status"])
        x = self.last()["collector_correlation"]
        self.assertEqual("LOCAL_COLLECTOR_CORRELATED_UNVERIFIED", x["status"])
        for k in ("verified", "eligible_for_training", "independent_source_attestation",
                  "causal_action_proven"):
            self.assertIs(x[k], False)
        self.assertIs(self.last()["verified"], False)
        self.assertFalse((self.root / "tablet_autonomy_verified_outcomes.jsonl").exists())

    def test_empty_baseline_does_not_create_neural_evidence(self):
        x = self.invoke()
        self.assertEqual("COLLECTOR_OBSERVATION_MISSING",
                         self.last()["collector_correlation"]["status"])

    def test_output_file_changed_after_receipt_is_rejected(self):
        self.take_receipt()
        p = self.root / "market_prices.json"
        data = json.loads(p.read_text())
        data["entries"]["test"]["price"] = 999
        p.write_text(json.dumps(data), encoding="utf-8")
        self.invoke()
        self.assertEqual("COLLECTOR_OUTPUT_MISMATCH",
                         self.last()["collector_correlation"]["status"])

    def test_global_degradation_blocks_correlation(self):
        self.take_receipt()
        p = self.root / "auto_update_report.json"
        data = json.loads(p.read_text())
        data["degraded_count"] = 1
        p.write_text(json.dumps(data), encoding="utf-8")
        self.invoke()
        self.assertEqual("COLLECTOR_CORRELATION_HOLD",
                         self.last()["collector_correlation"]["status"])

    def test_stale_report_never_certifies(self):
        self.finished = datetime.now(timezone.utc) - timedelta(hours=4)
        self.write_collector()
        self.take_receipt()
        self.invoke()
        self.assertEqual("COLLECTOR_OBSERVATION_STALE",
                         self.last()["collector_correlation"]["status"])

    def test_symlink_receipt_directory_is_refused(self):
        self.receipts.rmdir()
        self.receipts.symlink_to(self.root, target_is_directory=True)
        self.invoke()
        self.assertEqual("COLLECTOR_UNSAFE_PATH",
                         self.last()["collector_correlation"]["status"])

    def test_forged_verified_label_is_rejected(self):
        self.take_receipt()
        p = self.receipts / NAME
        data = json.loads(p.read_text())
        data["observations"][-1]["verified_neural_outcome"] = True
        p.write_text(json.dumps(data), encoding="utf-8")
        self.invoke()
        self.assertEqual("COLLECTOR_CORRELATION_HOLD",
                         self.last()["collector_correlation"]["status"])

    def test_optional_old_record_api_is_backward_compatible(self):
        self.take_receipt()
        self.invoke(root=False)
        self.assertEqual("COLLECTOR_NOT_CONFIGURED",
                         self.last()["collector_correlation"]["status"])

    def test_nested_verified_forgery_is_blocked_even_when_rehashed(self):
        from execution.tablet_autonomy_evidence_journal_v654 import _digest, EvidenceHold, status
        self.take_receipt()
        self.invoke()
        path = self.state / OUTPUT_NAME
        data = json.loads(path.read_text())
        row = data["observations"][0]
        row["collector_correlation"]["verified"] = True
        row["receipt_sha256"] = _digest({k: v for k, v in row.items() if k != "receipt_sha256"})
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(EvidenceHold, "JOURNAL_NESTED_TRUST_HOLD"):
            status(self.state)

    def test_nested_digest_forgery_is_rejected(self):
        from execution.tablet_autonomy_evidence_journal_v654 import _digest, EvidenceHold, status
        self.take_receipt()
        self.invoke()
        path = self.state / OUTPUT_NAME
        data = json.loads(path.read_text())
        row = data["observations"][0]
        row["collector_correlation"]["report_sha256"] = "not-a-sha256"
        row["receipt_sha256"] = _digest({k: v for k, v in row.items() if k != "receipt_sha256"})
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(EvidenceHold, "JOURNAL_CORRELATION_DIGEST_HOLD"):
            status(self.state)

    def test_scheduler_uses_existing_23h_schedule_not_new_timer(self):
        script = (Path(__file__).resolve().parents[1] / "TABLET_SCHEDULED_UPDATE.sh").read_text()
        self.assertIn('--root "$ROOT" --state-dir "$STATE_DIR"', script)
        self.assertIn('SCHEDULE_HOUR="23"', script)
        self.assertIn('SCHEDULE_MINUTE="00"', script)
        self.assertNotIn('reset --hard', script)

if __name__ == "__main__":
    unittest.main()
