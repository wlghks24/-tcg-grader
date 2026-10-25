from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import ai_runtime_model_guard as guard
import verified_collection_neural as query_ai
import verified_collection_job_neural as job_ai


NOW = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)


def query_model(stamp: datetime) -> dict:
    hidden = 4
    return {
        "schema": query_ai.SCHEMA,
        "active": True,
        "feature_fingerprint": query_ai.FEATURE_FINGERPRINT,
        "feature_count": query_ai.FEATURE_COUNT,
        "trained_at": stamp.isoformat(timespec="seconds"),
        "label_count": query_ai.MIN_INDEPENDENT_LABELS,
        "hidden": hidden,
        "w1": [[0.0] * query_ai.FEATURE_COUNT for _ in range(hidden)],
        "b1": [0.0] * hidden,
        "w2": [0.0] * hidden,
        "b2": 0.0,
        "metrics": {"accuracy": 0.7, "logloss": 0.6},
        "protocol_version": query_ai.PROTOCOL_VERSION,
        "calibration_slope": 1.0,
        "calibration_offset": 0.0,
    }


def job_model(stamp: datetime, *, labels: int | None = None, protocol: int | None = None) -> dict:
    hidden = 4
    return {
        "schema": job_ai.SCHEMA,
        "active": True,
        "feature_fingerprint": job_ai.FEATURE_FINGERPRINT,
        "feature_count": job_ai.FEATURE_COUNT,
        "trained_at": stamp.isoformat(timespec="seconds"),
        "label_count": job_ai.MIN_INDEPENDENT_LABELS if labels is None else labels,
        "hidden": hidden,
        "w1": [[0.0] * job_ai.FEATURE_COUNT for _ in range(hidden)],
        "b1": [0.0] * hidden,
        "w2": [0.0] * hidden,
        "b2": 0.0,
        "metrics": {"accuracy": 0.7, "logloss": 0.6},
        "protocol_version": job_ai.PROTOCOL_VERSION if protocol is None else protocol,
        "calibration_slope": 1.0,
        "calibration_offset": 0.0,
    }


class AIScoreFreshnessV270Tests(unittest.TestCase):
    def setUp(self):
        query_ai._MODEL_CACHE_KEY = None
        query_ai._MODEL_CACHE_RESULT = None
        job_ai._MODEL_CACHE_KEY = None
        job_ai._MODEL_CACHE_RESULT = None

    def test_runtime_policy_matches_health_guard(self):
        self.assertEqual(guard.MAX_ACTIVE_MODEL_AGE_SECONDS, query_ai.MAX_RUNTIME_MODEL_AGE_SECONDS)
        self.assertEqual(guard.MAX_ACTIVE_MODEL_AGE_SECONDS, job_ai.MAX_RUNTIME_MODEL_AGE_SECONDS)
        self.assertEqual(guard.FUTURE_CLOCK_TOLERANCE_SECONDS, query_ai.RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS)
        self.assertEqual(guard.FUTURE_CLOCK_TOLERANCE_SECONDS, job_ai.RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS)
        self.assertFalse(query_ai.SAFETY["runtime_stale_model_priority_allowed"])
        self.assertFalse(job_ai.SAFETY["runtime_stale_model_priority_allowed"])

    def test_query_score_disables_stale_and_future_model_but_keeps_fresh_model(self):
        row = {"game": "포켓몬", "region": "KR", "family": "official-site"}
        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "query.json"
            model_path.write_text(json.dumps(query_model(NOW)), encoding="utf-8")
            fresh = query_ai.score_query(row, model_path=model_path, now=NOW)
            self.assertTrue(fresh["active"])

            model_path.write_text(json.dumps(query_model(NOW - timedelta(seconds=query_ai.MAX_RUNTIME_MODEL_AGE_SECONDS + 1))) + "\n", encoding="utf-8")
            stale = query_ai.score_query(row, model_path=model_path, now=NOW)
            self.assertFalse(stale["active"])
            self.assertEqual(0.5, stale["score"])
            self.assertEqual("active_model_stale", stale["reason"])

            model_path.write_text(json.dumps(query_model(NOW + timedelta(seconds=query_ai.RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS + 1))) + "\n\n", encoding="utf-8")
            future = query_ai.score_query(row, model_path=model_path, now=NOW)
            self.assertFalse(future["active"])
            self.assertEqual("trained_at_in_future", future["reason"])

    def test_job_score_disables_stale_model_and_rejects_weak_artifact_contract(self):
        stats = {"runs": 20, "successes": 18, "success_ewma_seconds": 30.0}
        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "job.json"
            model_path.write_text(json.dumps(job_model(NOW)), encoding="utf-8")
            fresh = job_ai.score_job("market_prices.json", stats, model_path=model_path, now=NOW)
            self.assertTrue(fresh["active"])

            model_path.write_text(json.dumps(job_model(NOW - timedelta(seconds=job_ai.MAX_RUNTIME_MODEL_AGE_SECONDS + 1))) + "\n", encoding="utf-8")
            stale = job_ai.score_job("market_prices.json", stats, model_path=model_path, now=NOW)
            self.assertFalse(stale["active"])
            self.assertEqual(0.5, stale["risk_priority"])
            self.assertEqual("active_model_stale", stale["reason"])

            model_path.write_text(json.dumps(job_model(NOW, labels=999)) + "\n\n", encoding="utf-8")
            low_labels = job_ai.score_job("market_prices.json", stats, model_path=model_path, now=NOW)
            self.assertFalse(low_labels["active"])
            self.assertEqual("label_count_below_activation_gate", low_labels["reason"])

            model_path.write_text(json.dumps(job_model(NOW, protocol=job_ai.PROTOCOL_VERSION + 1)) + "\n\n\n", encoding="utf-8")
            bad_protocol = job_ai.score_job("market_prices.json", stats, model_path=model_path, now=NOW)
            self.assertFalse(bad_protocol["active"])

    def test_model_json_is_cached_until_file_signature_changes(self):
        row = {"game": "포켓몬", "region": "US", "family": "official-site"}
        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "query.json"
            model_path.write_text(json.dumps(query_model(NOW)), encoding="utf-8")
            original = query_ai._load_json
            with patch.object(query_ai, "_load_json", wraps=original) as loader:
                self.assertTrue(query_ai.score_query(row, model_path=model_path, now=NOW)["active"])
                first_calls = loader.call_count
                self.assertGreaterEqual(first_calls, 1)
                self.assertTrue(query_ai.score_query(row, model_path=model_path, now=NOW)["active"])
                self.assertEqual(first_calls, loader.call_count)
                model_path.write_text(json.dumps(query_model(NOW)) + "\nchanged-signature", encoding="utf-8")
                self.assertFalse(query_ai.score_query(row, model_path=model_path, now=NOW)["active"])
                self.assertGreater(loader.call_count, first_calls)


if __name__ == "__main__":
    unittest.main()
