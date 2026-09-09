#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from ai_reliability_v8.evidence_learning import FEATURES
from instagram_tcg_content.ai_reliability_runtime import (
    EXPECTED_OUTPUT_KEYS,
    PURPOSE,
    REVISION,
    collection_features,
    evaluate_ai_runtime,
    train_candidate_if_ready,
    verify_binding_integrity,
)


class InstagramAiReliabilityRuntimeTests(unittest.TestCase):
    def _report(self, *, ready=True):
        return {
            "status": "READY" if ready else "NOT_READY",
            "snapshot_age_hours": 2.0 if ready else 72.0,
            "matrix_counts": {key: (12 if ready else 0) for key in EXPECTED_OUTPUT_KEYS},
            "completed_sale_counts": {key: (10 if ready else 0) for key in EXPECTED_OUTPUT_KEYS},
            "route_problems": [] if ready else ["COMPLETED_SALE_ROUTE_SHORTAGE:naruto:1/2"],
            "reasons": [] if ready else [
                "OUTPUT_MATRIX_COVERAGE_MISSING:naruto:EN",
                "COMPLETED_SALE_COVERAGE_INSUFFICIENT",
            ],
        }

    def _model(self):
        return {
            "schema_version": 8,
            "kind": "l2_logistic",
            "weights": [0.0] * (len(FEATURES) + 1),
            "features": list(FEATURES),
            "scope": {
                "project": "instagram_card",
                "purpose": PURPOSE,
                "revision": REVISION,
            },
            "calibration_slope": 1.0,
            "calibration_offset": 0.0,
            "operational": True,
            "training_label_count": 1000,
            "temporal_split_policy": "50_15_15_20",
            "verification_authority": False,
        }

    def test_binding_integrity_matches_canonical_project_and_task(self):
        result = verify_binding_integrity()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["project"], "instagram_card")
        self.assertEqual(result["task_id"], "6a9b8a22e72c8191849c273e1240378e")
        self.assertGreater(result["checked_file_count"], 10)
        self.assertEqual(result["minimum_real_labels"], 1000)

    def test_collection_health_is_mapped_to_exact_six_ai_features(self):
        good = collection_features(self._report(ready=True))
        self.assertEqual(set(good), set(FEATURES))
        self.assertEqual(good["field_completeness"], 1.0)
        self.assertEqual(good["independent_support"], 1.0)

        bad = collection_features(self._report(ready=False))
        self.assertEqual(bad["freshness"], 0.0)
        self.assertEqual(bad["field_completeness"], 0.0)
        self.assertEqual(bad["independent_support"], 0.0)

    def test_missing_model_and_labels_is_explicit_rules_only_not_fake_neural(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = evaluate_ai_runtime(
                self._report(ready=False),
                state_root=root / "state",
                model_path=root / "missing-model.json",
                labels_path=root / "missing-labels.json",
            )
        self.assertEqual(result["connection_status"], "CONNECTED_ADVISORY_ONLY")
        self.assertEqual(result["model_status"], "RULES_ONLY_NO_OPERATIONAL_MODEL")
        self.assertFalse(result["neural_active"])
        self.assertEqual(result["training_status"], "KEEP_EXISTING_MODEL_NO_TRAINING")
        self.assertEqual(result["label_audit"]["independent_real_label_rows"], 0)
        self.assertFalse(result["can_verify"])
        self.assertFalse(result["can_override_collection_health"])
        self.assertFalse(result["can_authorize_production"])
        self.assertTrue(result["collection_health_unchanged"])

    def test_valid_operational_model_is_advisory_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            model = root / "model.json"
            model.write_text(json.dumps(self._model()), encoding="utf-8")
            result = evaluate_ai_runtime(
                self._report(ready=True),
                state_root=root / "state",
                model_path=model,
                labels_path=root / "missing-labels.json",
            )
        self.assertTrue(result["neural_active"], result)
        self.assertEqual(result["ranking"]["status"], "ADVISORY_ONLY")
        self.assertIn("estimated_label_probability", result["ranking"])
        self.assertFalse(result["ranking"]["can_verify"])
        self.assertFalse(result["can_authorize_production"])

    def test_promoted_training_report_unwraps_operational_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            model = root / "model.json"
            model.write_text(json.dumps({
                "status": "READY_FOR_REVIEW_RANKING",
                "model": self._model(),
                "metrics": {"statistical_gates_passed": True},
            }), encoding="utf-8")
            result = evaluate_ai_runtime(
                self._report(ready=True),
                state_root=root / "state",
                model_path=model,
                labels_path=root / "missing-labels.json",
            )
        self.assertTrue(result["neural_active"], result)
        self.assertEqual(result["model_status"], "PROMOTED_MODEL_REPORT_PRESENT")
        self.assertEqual(result["ranking"]["status"], "ADVISORY_ONLY")
        self.assertFalse(result["can_verify"])

    def test_invalid_model_falls_back_to_rules_without_overriding_health(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            model = root / "model.json"
            invalid = self._model()
            invalid["scope"] = dict(invalid["scope"], project="wrong")
            model.write_text(json.dumps(invalid), encoding="utf-8")
            result = evaluate_ai_runtime(
                self._report(ready=True),
                state_root=root / "state",
                model_path=model,
                labels_path=root / "missing-labels.json",
            )
        self.assertFalse(result["neural_active"])
        self.assertTrue(result["model_status"].startswith("MODEL_REJECTED_RULES_ONLY:"))
        self.assertEqual(result["collection_health_status"], "READY")
        self.assertTrue(result["collection_health_unchanged"])

    def test_training_path_preserves_existing_model_below_real_label_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            model = root / "model.json"
            result = train_candidate_if_ready(
                labels_path=root / "missing-labels.json",
                model_path=model,
                state_root=root / "state",
            )
            self.assertFalse(model.exists())
        self.assertEqual(result["status"], "KEEP_EXISTING_MODEL_NO_TRAINING")
        self.assertTrue(result["existing_model_preserved"])
        self.assertEqual(result["label_audit"]["minimum_real_labels"], 1000)


if __name__ == "__main__":
    unittest.main()
