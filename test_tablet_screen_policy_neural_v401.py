import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import tablet_screen_policy_neural_v401 as neural

NOW = datetime(2026, 10, 3, 9, 30, tzinfo=timezone.utc)


def portfolio():
    rows = []
    for i, surface in enumerate(neural.SURFACES):
        rows.append({
            "surface": surface,
            "urgency": round(0.10 + i * 0.08, 6),
            "confidence": round(0.90 - i * 0.07, 6),
        })
    return {"surfaces": rows}


def activity():
    return {"release_activity": 0.7, "event_activity": 0.4, "market_activity": 0.8}


def history_rows():
    features = neural.policy_features(portfolio(), activity())
    rows = []
    scores = [
        {"ui": 0.60, "card_measurement": 0.40, "card_market": 0.45, "card_release": 0.50,
         "collab_event": 0.55, "purchase_availability": 0.50, "tablet_ops": 0.65},
        {"ui": 0.62, "card_measurement": 0.46, "card_market": 0.51, "card_release": 0.52,
         "collab_event": 0.56, "purchase_availability": 0.54, "tablet_ops": 0.67},
        {"ui": 0.63, "card_measurement": 0.52, "card_market": 0.56, "card_release": 0.55,
         "collab_event": 0.58, "purchase_availability": 0.58, "tablet_ops": 0.69},
    ]
    tops = [
        ["precision-grade", "market-search", "purchase-finder", "release-info", "code-audit"],
        ["auto-grade", "trading-catalog", "purchase-distance", "promo-event-info", "tablet-manager"],
        ["verified-grade", "grading-economics", "box-knowledge", "learning-status", "code-validation"],
    ]
    for i in range(3):
        rows.append({
            "observed_at": f"2026-10-03T09:0{i}:00+00:00",
            "cycle": i + 1,
            "adaptive_applied": True,
            "top_features": tops[i],
            "surface_scores": scores[i],
            "policy_features": features,
        })
    return rows


class TabletScreenPolicyNeuralV401Tests(unittest.TestCase):
    def test_feature_vector_is_exact_bounded_operational_evidence(self):
        features = neural.policy_features(portfolio(), activity())
        self.assertEqual(neural.INPUT_DIM, len(features))
        self.assertTrue(all(0.0 <= value <= 1.0 for value in features))
        self.assertEqual(17, neural.INPUT_DIM)
        self.assertEqual(12, neural.HIDDEN_DIM)
        self.assertEqual(18, len(neural.FEATURE_KEYS))

    def test_training_rows_require_applied_allowlisted_plan_and_verified_scores(self):
        current = {
            "ui": 0.64, "card_measurement": 0.57, "card_market": 0.60, "card_release": 0.58,
            "collab_event": 0.61, "purchase_availability": 0.62, "tablet_ops": 0.71,
        }
        rows = neural.training_rows(history_rows(), current_surface_scores=current)
        self.assertGreaterEqual(len(rows), neural.MIN_TRAINING_ROWS)
        self.assertTrue(all(row["feature_key"] in neural.FEATURE_KEYS for row in rows))
        self.assertTrue(all(len(row["features"]) == neural.INPUT_DIM for row in rows))
        self.assertTrue(all(-1.0 <= row["target"] <= 1.0 for row in rows))
        self.assertTrue(all(0.60 <= row["rank_weight"] <= 1.0 for row in rows))

        poisoned = history_rows()
        poisoned[0]["adaptive_applied"] = False
        poisoned[1]["policy_features"] = [99.0] * neural.INPUT_DIM
        filtered = neural.training_rows(poisoned, current_surface_scores=current)
        self.assertLess(len(filtered), len(rows))

    def test_model_trains_only_after_minimum_verified_rows_and_bias_is_bounded(self):
        current = {
            "ui": 0.64, "card_measurement": 0.57, "card_market": 0.60, "card_release": 0.58,
            "collab_event": 0.61, "purchase_availability": 0.62, "tablet_ops": 0.71,
        }
        rows = neural.training_rows(history_rows(), current_surface_scores=current)
        self.assertIsNone(neural.train_model(rows[: neural.MIN_TRAINING_ROWS - 1], now=NOW))
        model = neural.train_model(rows, now=NOW)
        self.assertIsNotNone(model)
        self.assertTrue(neural.validate_model(model, now=NOW))
        self.assertEqual(len(rows), model["sample_count"])

        output = neural.feature_bias(model, neural.policy_features(portfolio(), activity()), now=NOW)
        self.assertTrue(output["active"])
        self.assertEqual(set(neural.FEATURE_KEYS), set(output["feature_biases"]))
        self.assertLessEqual(output["max_abs_bias"], neural.MAX_FEATURE_BIAS)
        self.assertTrue(output["verified_surface_outcomes_only"])
        self.assertTrue(output["advisory_only"])

    def test_corrupt_model_fails_closed_to_zero_bias_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "screen.json"
            path.write_text('{"schema_version":1,"bad":true}', encoding="utf-8")
            loaded = neural.load_model(path, now=NOW)
            self.assertTrue(loaded["corruption_hold"])
            self.assertIsNone(loaded["model"])
            output = neural.feature_bias(None, neural.policy_features(portfolio(), activity()), now=NOW)
            self.assertFalse(output["active"])
            self.assertEqual(0.0, output["max_abs_bias"])
            self.assertTrue(all(value == 0.0 for value in output["feature_biases"].values()))

    def test_persist_and_reload_round_trip_keeps_exact_contract(self):
        current = {
            "ui": 0.64, "card_measurement": 0.57, "card_market": 0.60, "card_release": 0.58,
            "collab_event": 0.61, "purchase_availability": 0.62, "tablet_ops": 0.71,
        }
        rows = neural.training_rows(history_rows(), current_surface_scores=current)
        model = neural.train_model(rows, now=NOW)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "screen.json"
            write = neural.persist_model(model, path, now=NOW)
            self.assertTrue(write["written"])
            loaded = neural.load_model(path, now=NOW)
            self.assertFalse(loaded["corruption_hold"])
            self.assertEqual("SCREEN_NEURAL_LOADED", loaded["status"])
            self.assertEqual(list(neural.FEATURE_KEYS), loaded["model"]["features"])

    def test_safety_contract_forbids_unbounded_self_modification_and_behavior_tracking(self):
        self.assertTrue(neural.SAFETY["verified_surface_outcomes_only"])
        self.assertTrue(neural.SAFETY["allowlisted_features_only"])
        self.assertTrue(neural.SAFETY["advisory_only"])
        self.assertFalse(neural.SAFETY["user_behavior_tracking"])
        self.assertFalse(neural.SAFETY["market_direction_inferred"])
        self.assertFalse(neural.SAFETY["source_code_generation"])
        self.assertFalse(neural.SAFETY["source_code_rewrite"])
        self.assertFalse(neural.SAFETY["arbitrary_command_execution"])
        self.assertFalse(neural.SAFETY["git_write"])
        self.assertFalse(neural.SAFETY["direct_main_write"])
        self.assertFalse(neural.SAFETY["verification_bypass"])
        self.assertFalse(neural.SAFETY["price_grade_stock_release_event_fact_invention"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
