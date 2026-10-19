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


class CandidateSelectionTests(unittest.TestCase):
    def test_qualified_candidate_beats_unverified_high_score(self):
        base = fixture()
        policy = v387.uncertainty_policy(base, v387._default_state())
        self.assertEqual("REFRESH_MARKET_DATA", policy["selected_action"])
        self.assertEqual("VERIFIED_ELIGIBLE", policy["selection_mode"])
        self.assertEqual(1, policy["eligible_candidate_count"])
        self.assertTrue(v387.autonomous_gate(base, policy)["allow_execution"])

    def test_zero_sample_recovery_does_not_become_false_success(self):
        base = fixture()
        base["v386_mutual_neural_policy"]["candidates"] = [
            dict(base["v386_mutual_neural_policy"]["candidates"][1], local_verified_samples=0)
        ]
        policy = v387.uncertainty_policy(base, v387._default_state())
        gate = v387.autonomous_gate(base, policy)
        self.assertEqual("HOLD_NO_ELIGIBLE", policy["selection_mode"])
        self.assertFalse(gate["allow_execution"])
        self.assertEqual("V387_UNCERTAINTY_HOLD", gate["status"])
        self.assertIn("NO_VERIFIED_RECOVERY_EVIDENCE", gate["reasons"])

    def test_no_qualified_candidate_remains_held(self):
        base = fixture()
        base["v386_mutual_neural_policy"]["candidates"][1]["local_verified_samples"] = 0
        policy = v387.uncertainty_policy(base, v387._default_state())
        gate = v387.autonomous_gate(base, policy)
        self.assertFalse(gate["allow_execution"])
        self.assertEqual("HOLD_NO_ELIGIBLE", policy["selection_mode"])
        self.assertEqual(v387.MIN_LOCAL_CONFIDENCE, policy["confidence_threshold"])

    def test_original_verified_recovery_under_unstable_regime(self):
        base = fixture()
        base["v382_drift"]["score"] = 0.8
        base["v386_mutual_neural_policy"]["candidates"] = [base["v386_mutual_neural_policy"]["candidates"][1]]
        base["v386_mutual_neural_policy"]["candidates"][0]["local_verified_samples"] = 100
        policy = v387.uncertainty_policy(base, v387._default_state())
        self.assertTrue(v387.autonomous_gate(base, policy)["allow_execution"])


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
        self.assertIn('execution/tablet_autonomy_evidence_audit_v652.py', source)
        self.assertIn('return "$rc"', source)
        self.assertNotIn("reset --hard", source)


if __name__ == "__main__":
    unittest.main()
