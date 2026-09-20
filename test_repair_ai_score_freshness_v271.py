from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import ai_runtime_model_guard as guard
import verified_neural_self_refine as repair_ai

NOW = datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)
FINGERPRINTS = {rule_id: (rule_id.encode("utf-8").hex() + "0" * 64)[:24] for rule_id in repair_ai.RULE_ORDER}


def model_payload(stamp: datetime, *, labels: int | None = None, protocol: int | None = None) -> dict:
    base = repair_ai._init_model(4, 271)
    return {
        "schema": repair_ai.SCHEMA,
        "active": True,
        "trained_at": stamp.isoformat(timespec="seconds"),
        "label_count": repair_ai.MIN_INDEPENDENT_LABELS if labels is None else labels,
        "feature_count": repair_ai.FEATURE_COUNT,
        "hidden": 4,
        "w1": base["w1"],
        "b1": base["b1"],
        "w2": base["w2"],
        "b2": base["b2"],
        "metrics": {"accuracy": 0.72, "logloss": 0.55},
        "protocol_version": repair_ai.PROTOCOL_VERSION if protocol is None else protocol,
        "calibration_slope": 1.0,
        "calibration_offset": 0.0,
        "rule_fingerprints": FINGERPRINTS,
        "safety": repair_ai.SAFETY,
    }


def issue() -> dict:
    return {
        "auto_repair_rule": repair_ai.RULE_ORDER[0],
        "path": "sample.py",
        "stage": "RUNTIME",
        "auto_repair_allowed": True,
    }


class RepairAIScoreFreshnessV271Tests(unittest.TestCase):
    def setUp(self):
        repair_ai._MODEL_CACHE_KEY = None
        repair_ai._MODEL_CACHE_RESULT = None

    def test_runtime_policy_matches_collection_ai_guard(self):
        self.assertEqual(guard.MAX_ACTIVE_MODEL_AGE_SECONDS, repair_ai.MAX_RUNTIME_MODEL_AGE_SECONDS)
        self.assertEqual(guard.FUTURE_CLOCK_TOLERANCE_SECONDS, repair_ai.RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS)
        self.assertFalse(repair_ai.SAFETY["runtime_stale_model_priority_allowed"])
        self.assertFalse(repair_ai.SAFETY["runtime_future_model_priority_allowed"])

    def test_score_is_neutral_for_stale_future_protocol_or_low_label_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "repair.json"
            cases = (
                (model_payload(NOW - timedelta(seconds=repair_ai.MAX_RUNTIME_MODEL_AGE_SECONDS + 1)), "active_model_stale"),
                (model_payload(NOW + timedelta(seconds=repair_ai.RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS + 1)), "trained_at_in_future"),
                (model_payload(NOW, protocol=repair_ai.PROTOCOL_VERSION + 1), "protocol_version_mismatch"),
                (model_payload(NOW, labels=repair_ai.MIN_INDEPENDENT_LABELS - 1), "label_count_below_activation_gate"),
            )
            for index, (payload, reason) in enumerate(cases):
                model.write_text(json.dumps(payload) + ("\n" * index), encoding="utf-8")
                scored = repair_ai.score_issue(issue(), current_rule_fingerprints=FINGERPRINTS, model_path=model, now=NOW)
                self.assertFalse(scored["active"], reason)
                self.assertEqual(0.5, scored["score"])
                self.assertEqual(reason, scored["reason"])

    def test_fresh_model_remains_priority_only_and_rule_fingerprint_gate_stays_first_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "repair.json"
            model.write_text(json.dumps(model_payload(NOW)), encoding="utf-8")
            scored = repair_ai.score_issue(issue(), current_rule_fingerprints=FINGERPRINTS, model_path=model, now=NOW)
            self.assertTrue(scored["active"])
            self.assertTrue(scored["neural_output_is_priority_only"])
            changed = dict(FINGERPRINTS)
            changed[repair_ai.RULE_ORDER[0]] = "f" * 24
            blocked = repair_ai.score_issue(issue(), current_rule_fingerprints=changed, model_path=model, now=NOW)
            self.assertFalse(blocked["active"])
            self.assertEqual("rule_fingerprint_changed", blocked["reason"])

    def test_validated_model_json_is_cached_until_signature_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "repair.json"
            model.write_text(json.dumps(model_payload(NOW)), encoding="utf-8")
            original = repair_ai._load_json
            with patch.object(repair_ai, "_load_json", wraps=original) as loader:
                self.assertTrue(repair_ai.score_issue(issue(), current_rule_fingerprints=FINGERPRINTS, model_path=model, now=NOW)["active"])
                first = loader.call_count
                self.assertGreaterEqual(first, 1)
                self.assertTrue(repair_ai.score_issue(issue(), current_rule_fingerprints=FINGERPRINTS, model_path=model, now=NOW)["active"])
                self.assertEqual(first, loader.call_count)
                model.write_text(json.dumps(model_payload(NOW)) + "\nchanged", encoding="utf-8")
                self.assertFalse(repair_ai.score_issue(issue(), current_rule_fingerprints=FINGERPRINTS, model_path=model, now=NOW)["active"])
                self.assertGreater(loader.call_count, first)


if __name__ == "__main__":
    unittest.main()
