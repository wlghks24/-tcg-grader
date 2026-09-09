#!/usr/bin/env python3
import random
import tempfile
import unittest
from pathlib import Path

from ai_reliability_v8 import EvidenceLearner, ReliabilityBridge
from ai_reliability_v8.adaptive_learning import (
    ALLOWED_HIDDEN_SIZES,
    ALLOWED_MLP_SEEDS,
    AdaptiveEvidenceLearner,
    FEATURES,
    _train_mlp,
    validate_prediction_model,
)
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

    def test_neural_gate_below_1000_preserves_existing_model_without_training(self):
        for learner_cls in (EvidenceLearner, AdaptiveEvidenceLearner):
            learner = learner_cls(
                project="instagram_card",
                purpose="verification_review",
                revision="v8-integration",
            )
            report = learner.fit([])
            self.assertEqual(report.get("status"), "MODEL_UPDATE_SKIPPED_KEEP_EXISTING")
            self.assertIsNone(report.get("model"))
            self.assertTrue(report.get("existing_model_preserved"))

        with tempfile.TemporaryDirectory() as td:
            bridge = build_ai_reliability_bridge(td)
            learner = bridge.evidence_learner(
                purpose="verification_review",
                revision="v8-integration",
            )
            self.assertIsInstance(learner, AdaptiveEvidenceLearner)

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
            "training_label_count": 1000,
            "temporal_split_policy": "50_15_15_20",
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

    def test_synthetic_labels_never_train_even_above_threshold(self):
        learner = AdaptiveEvidenceLearner(
            project="instagram_card",
            purpose="verification_review",
            revision="v8-integration",
        )
        rows = []
        for i in range(1000):
            rows.append({
                "project": "instagram_card",
                "purpose": "verification_review",
                "revision": "v8-integration",
                "label_source": "human_audit",
                "label_reference": f"ref-{i}",
                "label": i % 2,
                "id": f"id-{i}",
                "origin_group": f"origin-{i}",
                "owner_group": f"owner-{i % 4}",
                "synthetic": i == 999,
                "observed_at": f"2026-01-{1 + (i % 28):02d}T00:00:00+00:00",
                "labeled_at": f"2026-06-{1 + (i % 28):02d}T00:00:00+00:00",
                "features": {name: 0.5 for name in FEATURES},
            })
        report = learner.fit(rows)
        self.assertEqual(report["status"], "SYNTHETIC_LABELS_FORBIDDEN")
        self.assertIsNone(report["model"])
        self.assertTrue(report["existing_model_preserved"])

    def test_operational_neural_model_requires_exact_sizes_seeds_and_1000_labels(self):
        member = {
            "kind": "shallow_mlp",
            "hidden_size": 4,
            "hidden_weights": [[0.0] * len(FEATURES) for _ in range(4)],
            "hidden_bias": [0.0] * 4,
            "output_weights": [0.0] * 4,
            "output_bias": 0.0,
        }
        base = {
            "schema_version": 8,
            "kind": "mlp_ensemble",
            "hidden_size": 4,
            "seeds": list(ALLOWED_MLP_SEEDS),
            "members": [dict(member) for _ in range(3)],
            "features": list(FEATURES),
            "scope": {
                "project": "instagram_card",
                "purpose": "verification_review",
                "revision": "v8-integration",
            },
            "calibration_slope": 1.0,
            "calibration_offset": 0.0,
            "operational": True,
            "training_label_count": 1000,
            "temporal_split_policy": "50_15_15_20",
            "verification_authority": False,
        }
        self.assertTrue(validate_prediction_model(base))
        self.assertEqual(ALLOWED_HIDDEN_SIZES, (4, 8, 12))

        bad = dict(base, hidden_size=16)
        with self.assertRaises(ValueError):
            validate_prediction_model(bad)
        bad = dict(base, seeds=[1, 2, 3])
        with self.assertRaises(ValueError):
            validate_prediction_model(bad)
        bad = dict(base, training_label_count=999)
        with self.assertRaises(ValueError):
            validate_prediction_model(bad)

    def test_mlp_regularization_and_ensemble_integrity(self):
        seed = 20260907
        hidden = 4
        rng = random.Random(seed)
        _ = [[rng.uniform(-.18, .18) for _ in FEATURES] for _ in range(hidden)]
        initial_output = [rng.uniform(-.18, .18) for _ in range(hidden)]
        rows = [(float(i), [0.0] * len(FEATURES), i % 2, str(i)) for i in range(1000)]
        model = _train_mlp(rows, hidden_size=hidden, seed=seed)
        self.assertLess(
            sum(abs(x) for x in model["output_weights"]),
            sum(abs(x) for x in initial_output) * .70,
        )

        member = {
            "kind": "shallow_mlp",
            "hidden_size": 4,
            "hidden_weights": [[0.0] * len(FEATURES) for _ in range(4)],
            "hidden_bias": [0.0] * 4,
            "output_weights": [0.0] * 4,
            "output_bias": 0.0,
        }
        ensemble = {
            "schema_version": 8,
            "kind": "mlp_ensemble",
            "hidden_size": 8,
            "seeds": [1, 2, 3],
            "members": [dict(member) for _ in range(3)],
            "features": list(FEATURES),
            "scope": {"project": "instagram_card", "purpose": "verification_review", "revision": "v8-integration"},
            "calibration_slope": 1.0,
            "calibration_offset": 0.0,
            "operational": True,
            "verification_authority": False,
        }
        with self.assertRaises(ValueError):
            validate_prediction_model(ensemble)

    def test_activation_gate_requires_all_nine_pre_activation_receipts(self):
        gate = WorkflowGate()
        self.assertFalse(gate.check(["inventory", "binding", "backup"])["can_activate"])


if __name__ == "__main__":
    unittest.main()
