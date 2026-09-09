#!/usr/bin/env python3
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

from tcg_reliability.ai_reliability_v8.adaptive_learning import (
    AdaptiveEvidenceLearner,
    validate_prediction_model,
)
from tcg_reliability.ai_reliability_v8.workflow import WorkflowGate
from tcg_reliability_runtime import (
    BINDING_PATH,
    PROJECT,
    TASK_ID,
    initialize_tcg_reliability,
)


class TcgReliabilityV8IntegrationTests(unittest.TestCase):
    def test_binding_is_tcg_only(self):
        binding = json.loads(BINDING_PATH.read_text(encoding="utf-8"))
        self.assertEqual(PROJECT, "tcg_grader")
        self.assertEqual(TASK_ID, "6a9b878f35bc8191963b8685566709c4")
        self.assertEqual(binding["project"], PROJECT)
        self.assertEqual(binding["task_id"], TASK_ID)
        self.assertNotEqual(binding["project"], "instagram_card")

    def test_binding_hashes_match_installed_tcg_package(self):
        binding = json.loads(BINDING_PATH.read_text(encoding="utf-8"))
        package_root = BINDING_PATH.parent
        expected_files = binding.get("files")
        self.assertIsInstance(expected_files, dict)
        self.assertGreaterEqual(len(expected_files), 10)
        for name, expected in expected_files.items():
            path = package_root / name
            self.assertTrue(path.is_file(), name)
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(actual, expected, name)

    def test_bridge_state_is_project_scoped(self):
        with tempfile.TemporaryDirectory() as td:
            bridge, status = initialize_tcg_reliability(td)
            self.assertEqual((bridge.project, bridge.task_id), (PROJECT, TASK_ID))
            self.assertFalse(status["scheduler_mutation"])
            self.assertFalse(status["model_training_started"])
            self.assertTrue(bridge.root.is_relative_to(Path(td)))
            self.assertTrue((bridge.root / "diagnostics" / "evidence.sqlite").is_file())

    def test_neural_training_is_blocked_without_1000_real_labels(self):
        learner = AdaptiveEvidenceLearner(project=PROJECT, purpose="verification_review", revision="v8-tcg")
        report = learner.fit([])
        self.assertIsNone(report.get("model"))
        self.assertNotEqual(report.get("status"), "READY_FOR_REVIEW_RANKING")

    def test_model_integrity_rejects_nan_and_dimension_mismatch(self):
        model = {
            "schema_version": 8,
            "kind": "l2_logistic",
            "weights": [0.0] * 7,
            "features": ["source_match", "freshness", "independent_support", "field_completeness", "conflict", "parser_health"],
            "scope": {"project": PROJECT, "purpose": "verification_review", "revision": "v8-tcg"},
            "calibration_slope": 1.0,
            "calibration_offset": 0.0,
            "operational": True,
            "verification_authority": False,
        }
        self.assertTrue(validate_prediction_model(model))
        with self.assertRaises(ValueError):
            validate_prediction_model(dict(model, weights=[0.0] * 8))
        bad = dict(model, weights=list(model["weights"]))
        bad["weights"][0] = math.nan
        with self.assertRaises(ValueError):
            validate_prediction_model(bad)

    def test_activation_requires_all_pre_activation_receipts(self):
        gate = WorkflowGate()
        result = gate.check(["inventory", "binding", "backup", "read_only_plan", "additive_install"])
        self.assertFalse(result["can_activate"])
        self.assertEqual(result["next_stage"], "wire_one_entrypoint")


if __name__ == "__main__":
    unittest.main()

