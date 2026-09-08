#!/usr/bin/env python3
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

import tcg_updater
from tcg_grader_reliability.ai_reliability_v8 import ReliabilityBridge
from tcg_grader_reliability.ai_reliability_v8.adaptive_learning import (
    AdaptiveEvidenceLearner,
    validate_prediction_model,
)

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "tcg_grader_reliability" / "ai_reliability_v8"


class TcgReliabilityV8IntegrationTests(unittest.TestCase):
    def test_single_tcg_binding_and_bridge_factory(self):
        self.assertEqual(tcg_updater.AI_RELIABILITY_PROJECT, "tcg_grader")
        self.assertEqual(
            tcg_updater.AI_RELIABILITY_TASK_ID,
            "6a9b878f35bc8191963b8685566709c4",
        )
        with tempfile.TemporaryDirectory() as td:
            bridge = tcg_updater.build_ai_reliability_bridge(td)
            self.assertIsInstance(bridge, ReliabilityBridge)
            self.assertEqual(bridge.project, "tcg_grader")
            self.assertEqual(bridge.task_id, tcg_updater.AI_RELIABILITY_TASK_ID)

    def test_installed_package_matches_verified_binding_hashes(self):
        binding = json.loads((PACKAGE / "binding.json").read_text(encoding="utf-8"))
        self.assertEqual(binding["project"], "tcg_grader")
        self.assertEqual(binding["task_id"], "6a9b878f35bc8191963b8685566709c4")
        for name, expected in binding["files"].items():
            actual = hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, name)
        self.assertEqual(
            binding["files"]["source_registry.json"],
            "0d99cd983a2dd3db3a5cb0ec5116f52d72fbb881a62f103584aa1fab8933917f",
        )

    def test_tcg_package_is_separate_from_other_project_package(self):
        self.assertTrue(PACKAGE.is_dir())
        other = ROOT / "ai_reliability_v8" / "binding.json"
        if other.is_file():
            other_binding = json.loads(other.read_text(encoding="utf-8"))
            self.assertNotEqual(other_binding.get("task_id"), tcg_updater.AI_RELIABILITY_TASK_ID)
            self.assertNotEqual(other_binding.get("project"), "tcg_grader")

    def test_neural_gate_below_1000_does_not_train_mlp(self):
        learner = AdaptiveEvidenceLearner(
            project="tcg_grader",
            purpose="verification_review",
            revision="v8-tcg-integration",
        )
        report = learner.fit([])
        self.assertIsNone(report.get("model"))
        self.assertNotEqual(report.get("status"), "READY_FOR_REVIEW_RANKING")

    def test_model_integrity_rejects_nan_and_dimension_mismatch(self):
        base = {
            "schema_version": 8,
            "kind": "l2_logistic",
            "weights": [0.0] * 7,
            "features": [
                "source_match", "freshness", "independent_support",
                "field_completeness", "conflict", "parser_health",
            ],
            "scope": {
                "project": "tcg_grader",
                "purpose": "verification_review",
                "revision": "v8-tcg-integration",
            },
            "calibration_slope": 1.0,
            "calibration_offset": 0.0,
            "operational": True,
            "verification_authority": False,
        }
        self.assertTrue(validate_prediction_model(base))
        bad = dict(base, weights=[0.0] * 8)
        with self.assertRaises(ValueError):
            validate_prediction_model(bad)
        bad = dict(base, weights=list(base["weights"]))
        bad["weights"][0] = float("nan")
        with self.assertRaises(ValueError):
            validate_prediction_model(bad)

    def test_bridge_factory_has_no_scheduler_or_learning_mutation(self):
        source = Path(tcg_updater.__file__).read_text(encoding="utf-8")
        start = source.index("def build_ai_reliability_bridge")
        end = source.index("\n\ndef ", start + 10)
        body = source[start:end]
        for forbidden in (
            "automations.", "is_enabled", "schedule=", "learning_store.json",
            "vision_calibration.json", "card_identity_learning.json",
        ):
            self.assertNotIn(forbidden, body)


if __name__ == "__main__":
    unittest.main()
