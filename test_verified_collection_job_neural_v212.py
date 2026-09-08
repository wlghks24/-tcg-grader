from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

import verified_collection_job_neural as neural
import auto_update_all


class VerifiedCollectionJobNeuralV212Tests(unittest.TestCase):
    def test_safety_contract(self):
        self.assertEqual(212, neural.RUNTIME_PATCH)
        self.assertEqual((4, 8, 12), neural.HIDDEN_SIZES)
        self.assertEqual(1000, neural.MIN_INDEPENDENT_LABELS)
        self.assertFalse(neural.SAFETY["collector_skip_allowed"])
        self.assertFalse(neural.SAFETY["collector_disable_allowed"])
        self.assertFalse(neural.SAFETY["verification_bypass"])
        self.assertFalse(neural.SAFETY["official_trust_auto_promotion"])
        self.assertTrue(neural.SAFETY["neural_output_is_priority_only"])
        self.assertTrue(neural.SAFETY["all_mandatory_collectors_preserved"])

    def test_postflight_verified_report_ingest_and_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            labels = Path(tmp) / "labels.json"
            report = {
                "postflight_monitor": {"ok": True},
                "results": [
                    {
                        "file": "releases.json",
                        "ok": True,
                        "max_attempts": 2,
                        "adaptive_timeout_seconds": 120,
                        "collection_errors": [],
                    },
                    {
                        "file": "market_prices.json",
                        "ok": False,
                        "max_attempts": 2,
                        "adaptive_timeout_seconds": 180,
                        "error": "TimeoutError",
                    },
                    {
                        "file": "promo_events.json",
                        "ok": True,
                        "max_attempts": 0,
                        "status": "Retry-After 쿨다운 중 · 기존 검증자료 유지",
                    },
                ],
                "integration": {"ok": True, "max_attempts": 2, "degraded": False},
                "link_audit": {"ok": True, "max_attempts": 2, "degraded": False},
            }
            stats = {
                "jobs": {
                    "releases.json": {"runs": 4, "successes": 4, "success_ewma_seconds": 40},
                    "market_prices.json": {"runs": 4, "successes": 2, "timeouts": 2, "consecutive_failures": 1},
                    "__integration__": {"runs": 2, "successes": 2},
                    "__link_audit__": {"runs": 2, "successes": 2},
                }
            }
            now = datetime(2026, 9, 8, 12, 30, tzinfo=timezone.utc)
            first = neural.ingest_verified_report(report, stats, labels_path=labels, now=now)
            second = neural.ingest_verified_report(report, stats, labels_path=labels, now=now)
            self.assertEqual(4, first["eligible"])
            self.assertEqual(4, first["added"])
            self.assertEqual(0, second["added"])
            payload = json.loads(labels.read_text(encoding="utf-8"))
            self.assertEqual(4, len(payload["labels"]))
            self.assertEqual({True, False}, {row["outcome"] for row in payload["labels"]})
            self.assertNotIn("promo_events.json", {row["job_key"] for row in payload["labels"]})

    def test_no_postflight_no_learning(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = neural.ingest_verified_report(
                {"postflight_monitor": {"ok": False}, "results": []},
                {"jobs": {}},
                labels_path=Path(tmp) / "labels.json",
            )
            self.assertEqual(0, result["added"])
            self.assertEqual("postflight_not_verified", result["reason"])

    def test_training_compares_all_hidden_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels_path = root / "labels.json"
            model_path = root / "model.json"
            report_path = root / "report.json"
            rows = []
            for index in range(1000):
                good = index % 2 == 0
                rows.append({
                    "sample_id": hashlib.sha256(f"job-{index}".encode()).hexdigest()[:24],
                    "job_key": neural.JOB_KEYS[index % len(neural.JOB_KEYS)],
                    "runs": 10 + index % 20,
                    "successes": 8 if good else 3,
                    "partial_successes": 0 if good else 3,
                    "recovered_successes": 0 if good else 2,
                    "timeouts": 0 if good else 3,
                    "consecutive_failures": 0 if good else 2,
                    "success_ewma_seconds": 40 if good else 180,
                    "planned_timeout_seconds": 90 if good else 300,
                    "outcome": good,
                    "evidence": "clean_verified_collection" if good else "verified_operational_problem",
                    "observed_at": "2026-09-08T00:00:00+00:00",
                })
            labels_path.write_text(json.dumps({
                "schema": neural.SCHEMA,
                "feature_fingerprint": neural.FEATURE_FINGERPRINT,
                "labels": rows,
                "safety": neural.SAFETY,
            }, ensure_ascii=False), encoding="utf-8")
            old_epochs = neural.EPOCHS
            old_acc = neural.ACTIVATION_MIN_ACCURACY
            old_gain = neural.ACTIVATION_MIN_LOGLOSS_GAIN
            try:
                neural.EPOCHS = 2
                neural.ACTIVATION_MIN_ACCURACY = 0.0
                neural.ACTIVATION_MIN_LOGLOSS_GAIN = -100.0
                result = neural.train_if_ready(
                    labels_path=labels_path,
                    model_path=model_path,
                    report_path=report_path,
                    force=True,
                )
            finally:
                neural.EPOCHS = old_epochs
                neural.ACTIVATION_MIN_ACCURACY = old_acc
                neural.ACTIVATION_MIN_LOGLOSS_GAIN = old_gain
            self.assertEqual([4, 8, 12], [row["hidden"] for row in result["candidates"]])
            self.assertTrue(result["active"])
            score = neural.score_job(
                "releases.json",
                {"runs": 10, "successes": 8, "success_ewma_seconds": 50},
                planned_timeout_seconds=120,
                model_path=model_path,
            )
            self.assertTrue(score["active"])
            self.assertTrue(score["neural_output_is_priority_only"])
            self.assertGreaterEqual(score["risk_priority"], 0.0)
            self.assertLessEqual(score["risk_priority"], 1.0)

    def test_auto_update_order_preserves_all_collectors_and_inactive_ewma(self):
        stats = {
            "jobs": {
                "releases.json": {"ewma_seconds": 10},
                "market_watch.json": {"ewma_seconds": 20},
                "market_prices.json": {"ewma_seconds": 30},
                "promo_events.json": {"ewma_seconds": 40},
                "purchase_sources.json": {"ewma_seconds": 50},
                "exchange_rates.json": {"ewma_seconds": 60},
                "graded_photo_candidates.json": {"ewma_seconds": 70},
            }
        }
        with patch.object(
            auto_update_all.verified_collection_job_neural,
            "score_job",
            return_value={"active": False, "risk_priority": 0.5},
        ):
            inactive = auto_update_all._ordered_jobs(auto_update_all.JOBS, stats)
        self.assertEqual(
            [job[2] for job in inactive],
            [
                "graded_photo_candidates.json",
                "exchange_rates.json",
                "purchase_sources.json",
                "promo_events.json",
                "market_prices.json",
                "market_watch.json",
                "releases.json",
            ],
        )

        def score(filename, _stats, **_kwargs):
            return {
                "active": True,
                "risk_priority": 0.99 if filename == "releases.json" else 0.10,
            }

        with patch.object(auto_update_all.verified_collection_job_neural, "score_job", side_effect=score):
            active = auto_update_all._ordered_jobs(auto_update_all.JOBS, stats)
        self.assertEqual("releases.json", active[0][2])
        self.assertEqual(
            {job[2] for job in auto_update_all.JOBS},
            {job[2] for job in active},
        )
        self.assertEqual(len(auto_update_all.JOBS), len(active))

    def test_corrupt_primary_model_uses_valid_backup_and_rejects_nonfinite_weights(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "model.json"
            backup_path = root / "model.json.bak"
            base = neural._init_model(4, 17)
            payload = {
                "schema": neural.SCHEMA,
                "active": True,
                "feature_fingerprint": neural.FEATURE_FINGERPRINT,
                "feature_count": neural.FEATURE_COUNT,
                "trained_at": "2026-09-08T00:00:00+00:00",
                "label_count": 1000,
                "hidden": 4,
                "w1": base["w1"],
                "b1": base["b1"],
                "w2": base["w2"],
                "b2": base["b2"],
                "metrics": {"accuracy": 0.7, "logloss": 0.5},
                "safety": neural.SAFETY,
            }
            backup_path.write_text(json.dumps(payload), encoding="utf-8")
            broken = dict(payload)
            broken["w1"] = [[float("nan")] * neural.FEATURE_COUNT for _ in range(4)]
            model_path.write_text(json.dumps(broken), encoding="utf-8")
            model, source, recovered = neural._load_model_with_source(model_path)
            self.assertIsNotNone(model)
            self.assertEqual("backup", source)
            self.assertTrue(recovered)

    def test_explicit_disabled_primary_prevents_backup_reactivation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "model.json"
            backup_path = root / "model.json.bak"
            base = neural._init_model(4, 23)
            backup_path.write_text(json.dumps({
                "schema": neural.SCHEMA,
                "active": True,
                "feature_fingerprint": neural.FEATURE_FINGERPRINT,
                "feature_count": neural.FEATURE_COUNT,
                "trained_at": "2026-09-08T00:00:00+00:00",
                "label_count": 1000,
                "hidden": 4,
                "w1": base["w1"],
                "b1": base["b1"],
                "w2": base["w2"],
                "b2": base["b2"],
                "metrics": {"accuracy": 0.7, "logloss": 0.5},
                "safety": neural.SAFETY,
            }), encoding="utf-8")
            model_path.write_text(json.dumps({
                "schema": neural.SCHEMA,
                "active": False,
                "feature_fingerprint": neural.FEATURE_FINGERPRINT,
                "reason": "current_holdout_gate_failed",
            }), encoding="utf-8")
            model, source, recovered = neural._load_model_with_source(model_path)
            self.assertIsNone(model)
            self.assertEqual("disabled", source)
            self.assertFalse(recovered)

    def test_below_threshold_is_inactive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = neural.train_if_ready(
                labels_path=root / "labels.json",
                model_path=root / "model.json",
                report_path=root / "report.json",
            )
            self.assertFalse(result["active"])
            self.assertEqual("waiting_for_independent_labels", result["reason"])


if __name__ == "__main__":
    unittest.main()
