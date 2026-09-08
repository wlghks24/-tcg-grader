#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

from ai_reliability_v8 import ReliabilityBridge
from ai_reliability_v8.adaptive_learning import AdaptiveEvidenceLearner, validate_prediction_model
from ai_reliability_v8.workflow import WorkflowGate
from instagram_tcg_content.automation_state_guard import (
    AI_RELIABILITY_PROJECT,
    AI_RELIABILITY_TASK_ID,
    CANONICAL_ID,
    build_ai_reliability_bridge,
    runtime_failure_policy,
)


class InstagramCardReliabilityV8IntegrationTests(unittest.TestCase):
    def test_single_binding_and_bridge_factory(self):
        self.assertEqual(AI_RELIABILITY_PROJECT, "instagram_card")
        self.assertEqual(AI_RELIABILITY_TASK_ID, CANONICAL_ID)
        self.assertEqual(CANONICAL_ID, "6a9b8a22e72c8191849c273e1240378e")
        with tempfile.TemporaryDirectory() as td:
            bridge = build_ai_reliability_bridge(td)
            self.assertIsInstance(bridge, ReliabilityBridge)
            self.assertEqual(bridge.project, "instagram_card")
            self.assertEqual(bridge.task_id, CANONICAL_ID)

    def test_runtime_failures_never_mutate_scheduler(self):
        for stage, code, retryable in (
            ("revision_preflight", "REVISION_BASELINE_MISSING", False),
            ("render", "ARTIFACT_GENERATION_FAILED", False),
            ("source", "429", True),
        ):
            policy = runtime_failure_policy(stage=stage, error_code=code, retryable=retryable)
            self.assertFalse(policy["automation_state_mutation_allowed"])
            self.assertFalse(policy["self_disable_allowed"])
            self.assertFalse(policy["self_pause_allowed"])
            self.assertFalse(policy["self_reschedule_allowed"])
            self.assertTrue(policy["preserve_enabled_state"])
            self.assertFalse(policy["scheduler_terminal"])
            self.assertTrue(policy["automation_continues"])

    def test_neural_gate_below_1000_keeps_non_neural_path(self):
        learner = AdaptiveEvidenceLearner(project="instagram_card", purpose="verification_review", revision="v8-integration")
        report = learner.fit([])
        self.assertIsNone(report.get("model"))
        self.assertNotEqual(report.get("status"), "READY_FOR_REVIEW_RANKING")

    def test_model_integrity_rejects_nan_and_dimension_mismatch(self):
        base = {
            "schema_version": 8,
            "kind": "l2_logistic",
            "weights": [0.0] * 7,
            "features": ["source_match", "freshness", "independent_support", "field_completeness", "conflict", "parser_health"],
            "scope": {"project": "instagram_card", "purpose": "verification_review", "revision": "v8-integration"},
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

    def test_activation_gate_requires_all_nine_pre_activation_receipts(self):
        gate = WorkflowGate()
        self.assertFalse(gate.check(["inventory", "binding", "backup"])["can_activate"])


if __name__ == "__main__":
    unittest.main()
