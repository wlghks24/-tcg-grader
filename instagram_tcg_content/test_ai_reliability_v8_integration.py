#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone
import hashlib
import json
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
from ai_reliability_v8.verification import TTL, Verifier
from ai_reliability_v8.diverse_collection import SourceCoveragePlanner
from instagram_tcg_content.source_verification_engine import (
    validate_production_verification_receipt,
)
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

    def test_training_readiness_matches_1000_real_label_gate(self):
        planner = SourceCoveragePlanner()

        def rows(count, *, synthetic_index=None, owner_mod=4):
            result = []
            for i in range(count):
                result.append({
                    "project": "instagram_card",
                    "label": i % 2,
                    "id": f"id-{i}",
                    "origin_group": f"origin-{i}",
                    "owner_group": f"owner-{i % owner_mod}",
                    "label_source": "human_audit",
                    "label_reference": f"ref-{i}",
                    "synthetic": i == synthetic_index,
                })
            return result

        under = planner.audit_labels(rows(200))
        self.assertFalse(under["ready_for_training"])
        self.assertEqual(under["minimum_real_labels"], 1000)
        self.assertIn("INSUFFICIENT_REAL_LABEL_COUNT", under["readiness_reasons"])

        eligible = planner.audit_labels(rows(1000))
        self.assertTrue(eligible["ready_for_training"])
        self.assertEqual(eligible["independent_real_label_rows"], 1000)
        self.assertLessEqual(eligible["owner_dominance"], 0.70)

        synthetic = planner.audit_labels(rows(1000, synthetic_index=999))
        self.assertFalse(synthetic["ready_for_training"])
        self.assertIn("NON_REAL_OR_SYNTHETIC_LABEL_PRESENT", synthetic["readiness_reasons"])

        concentrated = planner.audit_labels(rows(1000, owner_mod=1))
        self.assertFalse(concentrated["ready_for_training"])
        self.assertIn("INSUFFICIENT_OWNER_DIVERSITY", concentrated["readiness_reasons"])
        self.assertIn("OWNER_CONCENTRATION_TOO_HIGH", concentrated["readiness_reasons"])

    def test_label_schema_and_split_source_concentration_fail_closed(self):
        base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

        def make_rows():
            rows = []
            for i in range(1000):
                observed = base_time + timedelta(minutes=i)
                labeled = observed + timedelta(seconds=1)
                owner = f"owner-{i % 4}" if i < 800 else "owner-0"
                rows.append({
                    "project": "instagram_card",
                    "purpose": "verification_review",
                    "revision": "v8-integration",
                    "label_source": "human_audit",
                    "label_reference": f"ref-{i}",
                    "label": i % 2,
                    "id": f"id-{i}",
                    "origin_group": f"origin-{i}",
                    "owner_group": owner,
                    "synthetic": False,
                    "observed_at": observed.isoformat(),
                    "labeled_at": labeled.isoformat(),
                    "features": {name: 0.5 for name in FEATURES},
                })
            return rows

        for learner_cls in (EvidenceLearner, AdaptiveEvidenceLearner):
            learner = learner_cls(
                project="instagram_card",
                purpose="verification_review",
                revision="v8-integration",
            )

            malformed = make_rows()
            malformed[0]["label_reference"] = 123
            with self.assertRaisesRegex(ValueError, "INDEPENDENT_LABEL_REQUIRED"):
                learner.fit(malformed)

            malformed_time = make_rows()
            malformed_time[0]["observed_at"] = 123
            with self.assertRaisesRegex(ValueError, "TIMESTAMP_REQUIRED"):
                learner.fit(malformed_time)

            split_biased = make_rows()
            report = learner.fit(split_biased)
            self.assertEqual(report["status"], "INSUFFICIENT_SOURCE_DIVERSITY")
            self.assertIsNone(report["model"])
            self.assertTrue(report.get("existing_model_preserved"))
            split_quality = report["data_quality"]["split_source_quality"]
            final_test = next(row for row in split_quality if row["split"] == "test")
            self.assertEqual(final_test["owner_groups"], 1)
            self.assertEqual(final_test["owner_dominance"], 1.0)

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

    def test_ai_score_cannot_authorize_production_verification(self):
        learner = AdaptiveEvidenceLearner(
            project="instagram_card",
            purpose="verification_review",
            revision="v8-integration",
        )
        model = {
            "schema_version": 8,
            "kind": "l2_logistic",
            "weights": [0.0] * 7,
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
        ranked = learner.rank(
            {
                "source_match": 1.0,
                "freshness": 1.0,
                "independent_support": 1.0,
                "field_completeness": 1.0,
                "conflict": 0.0,
                "parser_health": 1.0,
            },
            model,
        )
        self.assertFalse(ranked["can_verify"])
        errors = validate_production_verification_receipt(
            {
                "status": "pass",
                "model_probability": ranked["estimated_label_probability"],
            },
            expected_snapshot_id="snapshot-1",
        )
        self.assertIn("verification_receipt field set mismatch", errors)

    def test_completed_sale_verifier_requires_two_fresh_independent_sources(self):
        self.assertEqual(TTL["completed_sale"], 36 * 3600)
        now = datetime(2026, 9, 9, 3, 0, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = {
                "sources": [
                    {
                        "id": "sale-a",
                        "url": "https://a.example/",
                        "allowed_hosts": ["a.example"],
                        "projects": ["instagram_card"],
                        "kinds": ["completed_sale"],
                        "regions": ["KR"],
                        "subjects": ["cards"],
                        "owner_group": "owner-a",
                        "evidence_role": "primary",
                        "discovery_status": "PAGE_READ",
                    },
                    {
                        "id": "sale-b",
                        "url": "https://b.example/",
                        "allowed_hosts": ["b.example"],
                        "projects": ["instagram_card"],
                        "kinds": ["completed_sale"],
                        "regions": ["KR"],
                        "subjects": ["cards"],
                        "owner_group": "owner-b",
                        "evidence_role": "primary",
                        "discovery_status": "PAGE_READ",
                    },
                ]
            }
            registry_path = root / "registry.json"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            verifier = Verifier(root, project="instagram_card", registry_path=registry_path)

            claim = {
                "project": "instagram_card",
                "id": "sale-claim",
                "entity": "pokemon:test:psa10",
                "region": "KR",
                "language": "EN",
                "subject": "pokemon",
                "kind": "completed_sale",
                "value": 100.0,
                "scope": {
                    "condition": "graded",
                    "grade": "PSA 10",
                    "currency": "USD",
                    "unit": "card",
                    "quantity": 1,
                    "price_basis": "realized",
                    "transaction_id": "tx-1",
                },
            }

            def evidence(source_id, host, body_name, body_text, origin):
                body_path = root / body_name
                body_path.write_text(body_text, encoding="utf-8")
                return {
                    "id": source_id,
                    "source_id": source_id,
                    "project": claim["project"],
                    "entity": claim["entity"],
                    "region": claim["region"],
                    "language": claim["language"],
                    "kind": claim["kind"],
                    "scope": claim["scope"],
                    "url": f"https://{host}/lot/1",
                    "fetched_at": (now - timedelta(hours=1)).isoformat(),
                    "snippet_only": False,
                    "origin_key": origin,
                    "body_file": body_name,
                    "sha256": hashlib.sha256(body_path.read_bytes()).hexdigest(),
                }

            def inspect(_source, _claim, item, _body):
                return {
                    "inspected": True,
                    "reference": "manual-test-reference",
                    "source_capture_verified": True,
                    "source_capture_reference": "capture:" + item["id"],
                    "contradicts": False,
                    "matches": True,
                    "value": claim["value"],
                    "sale": {
                        "final": True,
                        "status": "SOLD",
                        "hidden_price": False,
                        "transaction_id": claim["scope"]["transaction_id"],
                        "currency": claim["scope"]["currency"],
                        "sold_at": (now - timedelta(days=20)).isoformat(),
                        "amount": claim["value"],
                    },
                }

            a = evidence("sale-a", "a.example", "a.txt", "sale-a-body", "origin-a")
            b = evidence("sale-b", "b.example", "b.txt", "sale-b-body", "origin-b")

            one = verifier.verify(claim, [a], inspect=inspect, now=now.isoformat())
            self.assertEqual(one["status"], "NEEDS_EVIDENCE")
            self.assertEqual(one["required_groups"], 2)

            two = verifier.verify(claim, [a, b], inspect=inspect, now=now.isoformat())
            self.assertEqual(two["status"], "VERIFIED_CROSSCHECK")
            self.assertEqual(two["independent_groups"], 2)

            def old_sale_inspect(source, local_claim, item, body):
                result = inspect(source, local_claim, item, body)
                result["sale"]["sold_at"] = (now - timedelta(days=31)).isoformat()
                return result

            old_sale = verifier.verify(claim, [a, b], inspect=old_sale_inspect, now=now.isoformat())
            self.assertEqual(old_sale["status"], "NEEDS_EVIDENCE")
            self.assertTrue(
                all(row["code"] == "SALE_OUTSIDE_30_DAY_WINDOW" for row in old_sale["rejected"])
            )

            stale_a = dict(a)
            stale_a["fetched_at"] = (now - timedelta(hours=37)).isoformat()
            stale = verifier.verify(claim, [stale_a, b], inspect=inspect, now=now.isoformat())
            self.assertEqual(stale["status"], "NEEDS_EVIDENCE")
            self.assertTrue(
                any(row["code"] == "STALE_OR_FUTURE_EVIDENCE" for row in stale["rejected"])
            )

    def test_activation_gate_requires_all_nine_pre_activation_receipts(self):
        gate = WorkflowGate()
        self.assertFalse(gate.check(["inventory", "binding", "backup"])["can_activate"])


if __name__ == "__main__":
    unittest.main()
