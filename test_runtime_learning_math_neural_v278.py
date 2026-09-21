#!/usr/bin/env python3
from __future__ import annotations

import math
import unittest

import grading_accuracy_v99 as grading
import search_method_learning as search_learning
import verified_collection_neural as neural


class RuntimeLearningMathNeuralV278Tests(unittest.TestCase):
    def test_neural_feature_vector_sanitizes_nonfinite_and_malformed_values(self):
        row = {
            "game": "pokemon",
            "region": "KR",
            "family": "official-site",
            "runs": "NaN",
            "hits": "Infinity",
            "relevant": "-Infinity",
            "official": "bad-number",
            "errors": None,
            "empty": {},
            "learned_score": float("nan"),
            "verified_gap_priority": float("inf"),
            "coverage_gap_score": -float("inf"),
        }
        vector = neural.feature_vector(row)
        self.assertEqual(len(vector), neural.FEATURE_COUNT)
        self.assertTrue(all(math.isfinite(value) for value in vector))
        self.assertTrue(all(0.0 <= value <= 1.0 for value in vector))

    def test_grading_math_rejects_nan_and_infinity(self):
        self.assertIsNone(grading.finite(float("nan")))
        self.assertIsNone(grading.finite(float("inf")))
        self.assertIsNone(grading.finite(-float("inf")))
        self.assertEqual(grading.quantize_down("PSA", float("nan")), 1.0)
        self.assertEqual(grading.risk_to_grade(float("inf")), 1.0)

    def test_search_method_math_stays_finite_with_corrupt_numeric_state(self):
        learner = search_learning.SearchMethodLearner()
        learner.data = {
            "rotation": 0,
            "methods": {
                "ddg_html": {
                    "attempts": "NaN",
                    "responses": "Infinity",
                    "results": {},
                    "selected": None,
                    "blocked": -float("inf"),
                    "rate_limited": float("nan"),
                    "timeouts": "bad",
                    "errors": "bad",
                    "avg_latency_ms": float("inf"),
                    "failure_streak": "bad",
                }
            },
            "contexts": {},
            "totals": {},
        }
        score = learner.method_score("ddg_html", "KR", "web")
        policy = learner.route_policy("ddg_html", region="KR", family="web")
        self.assertTrue(math.isfinite(score))
        self.assertTrue(math.isfinite(float(policy["score"])))
        self.assertGreaterEqual(policy["timeout_seconds"], 7)
        self.assertLessEqual(policy["timeout_seconds"], 55)
        self.assertIn(policy["max_attempts"], (1, 2))


if __name__ == "__main__":
    unittest.main()
