"""Safety/regression tests for evidence maturity review and V387 selection."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v387 as v387
from execution.tablet_autonomy_evidence_audit_v652 import audit


def fixture():
    return {
        "v386_autonomous_gate": {"allow_execution": True, "status": "V386_LOCAL_ONLY_ALLOW"},
        "v386_mutual_neural_policy": {
            "peer_available": False,
            "local_regime": "NORMAL_VOLATILITY",
            "peer_regime": None,
            "candidates": [
                {"action_id": "TRAIN_QUERY_STRATEGY", "score": 0.99, "local_score": 0.99,
                 "peer_score": None, "mutual_neural_score": None,
                 "local_verified_samples": 0, "peer_verified_samples": 0, "reward_gap": None},
                {"action_id": "REFRESH_MARKET_DATA", "score": 0.80, "local_score": 0.80,
                 "peer_score": None, "mutual_neural_score": None,
                 "local_verified_samples": 18, "peer_verified_samples": 0, "reward_gap": None},
            ],
        },
        "v382_drift": {"score": 0.0},
        "v382_kpis": {"score": 0.75},
    }


class CandidateSelectionAdvisoryTests(unittest.TestCase):
    def test_actual_gate_is_unchanged_pending_successor_lineage(self):
        base = fixture()
        policy = v387.uncertainty_policy(base, v387._default_state())
        self.assertEqual("TRAIN_QUERY_STRATEGY", policy["selected_action"])
        self.assertFalse(v387.autonomous_gate(base, policy)["allow_execution"])

    def test_advisory_identifies_qualified_alternative_without_execution(self):
        from execution.tablet_autonomy_evidence_audit_v652 import _candidate_advisory
        base = fixture()
        policy = v387.uncertainty_policy(base, v387._default_state())
        review = _candidate_advisory({"v387_uncertainty_policy": policy})
        self.assertEqual("VERIFIED_ALTERNATIVE_AVAILABLE", review["status"])
        self.assertEqual("REFRESH_MARKET_DATA", review["advisory_preferred_verified_action"])
        self.assertTrue(review["recommendations_are_non_executable"])
        self.assertTrue(review["v387_runtime_behavior_unchanged"])

    def test_recovery_without_samples_is_explicit_review_risk(self):
        from execution.tablet_autonomy_evidence_audit_v652 import _candidate_advisory
        base = fixture()
        base["v386_mutual_neural_policy"]["candidates"] = [
            dict(base["v386_mutual_neural_policy"]["candidates"][1], local_verified_samples=0)
        ]
        policy = v387.uncertainty_policy(base, v387._default_state())
        review = _candidate_advisory({"v387_uncertainty_policy": policy})
        self.assertEqual("NO_ELIGIBLE_ACTION", review["status"])
        self.assertEqual(["REFRESH_MARKET_DATA"], review["zero_sample_recovery_risk"])
        self.assertIsNone(review["advisory_preferred_verified_action"])

    def test_uncertainty_threshold_remains_original(self):
        self.assertEqual(0.55, v387.MIN_LOCAL_CONFIDENCE)
        self.assertEqual(0.62, v387.MIN_MUTUAL_CONFIDENCE)
        self.assertEqual(0.45, v387.MAX_EXECUTION_UNCERTAINTY)


class EvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / "autonomy.log"
        report = {
            **fixture(),
            "v400_status": "V400_UPSTREAM_HOLD",
            "v387_status": "V387_UNCERTAINTY_HOLD",
            "execution": {"executed": False, "source_code_modified": False, "git_write": False},
            "v387_autonomous_gate": {"allow_execution": False},
        }
        report["v386_mutual_neural_policy"]["candidates"] = [
            dict(row, local_verified_samples=0) for row in report["v386_mutual_neural_policy"]["candidates"]
        ]
        report["v387_uncertainty_policy"] = v387.uncertainty_policy(report, v387._default_state())
        self.log.write_text("precheck\n" + json.dumps(report) + "\n", encoding="utf-8")

    def test_missing_evidence_is_blocked_and_scored_independently(self):
        result = audit(self.root, self.log)
        self.assertEqual("HOLD", result["overall_status"])
        self.assertEqual("MISSING", result["evidence_file_status"])
        self.assertEqual(0, result["accepted_schema_rows"])
        self.assertLess(result["recorded_confidence"], v387.MIN_LOCAL_CONFIDENCE)
        self.assertTrue(result["readiness_score_not_v387_confidence"])
        self.assertFalse(result["independent_provenance_verified"])

    def test_counterfactual_is_explicitly_not_training(self):
        result = audit(self.root, self.log)
        p = result["counterfactual"]
        self.assertEqual("COUNTERFACTUAL_NOT_VERIFIED", p["mode"])
        self.assertTrue(p["not_a_guarantee"])
        self.assertGreater(p["additional_genuine_samples_indicated"], 0)
        self.assertTrue(result["no_training_or_model_writes"])

    def test_corrupt_schema_is_never_certified(self):
        (self.root / "tablet_autonomy_verified_outcomes.jsonl").write_text('{"verified":true}\n', encoding="utf-8")
        result = audit(self.root, self.log)
        self.assertEqual("REJECTED_ROWS", result["evidence_file_status"])
        self.assertEqual("HOLD", result["facets"]["storage"])

    def test_symlinked_evidence_is_held(self):
        (self.root / "tablet_autonomy_verified_outcomes.jsonl").symlink_to(self.root / "absent")
        self.assertEqual("UNSAFE_SYMLINK", audit(self.root, self.log)["evidence_file_status"])

    def test_duplicate_evidence_refs_are_held(self):
        row = {"verified": True, "action_id": "TRAIN_QUERY_STRATEGY",
               "reward": 0.4, "features": [0.3]*10, "evidence_ref": "real-receipt-needed"}
        p = self.root / "tablet_autonomy_verified_outcomes.jsonl"
        p.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
        self.assertEqual("DUPLICATE_EVIDENCE", audit(self.root, self.log)["evidence_file_status"])

    def test_no_side_effects_and_repeatability(self):
        before = sorted(p.name for p in self.root.iterdir())
        first = audit(self.root, self.log)
        second = audit(self.root, self.log)
        after = sorted(p.name for p in self.root.iterdir())
        self.assertEqual(before, after)
        self.assertEqual(first["overall_status"], second["overall_status"])

    def test_scheduler_keeps_original_rc_and_daily_cadence(self):
        source = (Path(__file__).resolve().parents[1] / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        self.assertIn('SCHEDULE_HOUR="23"', source)
        self.assertIn('SCHEDULE_MINUTE="00"', source)
        self.assertIn('python -m execution.tablet_autonomy_evidence_audit_v652', source)
        self.assertIn('return "$rc"', source)
        self.assertNotIn("reset --hard", source)


class CollectorProvenanceTests(unittest.TestCase):
    def setUp(self):
        from datetime import datetime, timezone
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    def data(self, collector=True, verified=True, publish=True, old=False):
        from datetime import timedelta
        def put(filename, value):
            (self.root / filename).write_text(json.dumps(value), encoding="utf-8")
        t = self.now - timedelta(hours=2 if old else 0)
        put("auto_update_report.json", {
            "ok": collector, "failure_count": 0 if collector else 1,
            "fresh_success_count": 4, "degraded_count": 0, "restored_count": 0,
            "finished_at": (t-timedelta(minutes=12)).isoformat()})
        put("COLLECTION_VERIFICATION_REPORT.json", {
            "status": "pass" if verified else "degraded",
            "counts": {"critical": 0, "high": 0 if verified else 1},
            "verified_at": (t-timedelta(minutes=8)).isoformat()})
        put("STATIC_DATA_PUBLISH_REPORT.json", {
            "status": "pass" if publish else "fail_closed",
            "publish_allowed": publish, "counts": {"critical": 0 if publish else 1},
            "checked_at": (t-timedelta(minutes=4)).isoformat()})

    def check(self):
        from execution.tablet_autonomy_evidence_audit_v652 import _collector_provenance
        return _collector_provenance(self.root, now=self.now)

    def test_missing_files_are_not_verified(self):
        self.assertEqual("NOT_READY", self.check()["status"])

    def test_clean_receipts_still_require_causal_action(self):
        self.data()
        x = self.check()
        self.assertEqual("CLEAN_REPORTS_REQUIRE_ACTION_RECEIPT", x["status"])
        self.assertEqual(3, len(x["artifact_sha256"]))
        self.assertFalse(x["causal_action_proven"])
        self.assertEqual(0, x["verified_training_outcomes_written"])

    def test_failure_remains_held(self):
        self.data(collector=False)
        self.assertIn("COLLECTOR_NOT_CLEAN", self.check()["issues"])

    def test_degradation_remains_held(self):
        self.data(verified=False)
        self.assertIn("VERIFICATION_NOT_PASS", self.check()["issues"])

    def test_publish_hold_remains_held(self):
        self.data(publish=False)
        self.assertIn("PUBLISH_NOT_PASS", self.check()["issues"])

    def test_stale_reports_remain_held(self):
        self.data(old=True)
        self.assertIn("STALE_OR_UNRELATED_RUNS", self.check()["issues"])

    def test_symlink_is_rejected(self):
        self.data()
        p = self.root / "auto_update_report.json"
        p.unlink()
        p.symlink_to(self.root / "STATIC_DATA_PUBLISH_REPORT.json")
        self.assertIn("collector:MISSING_OR_UNSAFE", self.check()["issues"])

    def test_repeated_checks_do_not_write(self):
        self.data()
        first = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.check()
        self.check()
        self.assertEqual(first, {p.name: p.read_bytes() for p in self.root.iterdir()})



if __name__ == "__main__":
    unittest.main()
