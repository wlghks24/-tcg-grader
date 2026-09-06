from __future__ import annotations
import unittest

from market_ai_learning_memory import (
    VerifiedOutcome,
    apply_confidence_cap,
    calibration_report,
    detect_distribution_drift,
    explain_anomaly,
    recurring_error_memory,
    verified_only,
)


class MarketAILearningMemoryTests(unittest.TestCase):
    def outcome(self, **overrides):
        base = dict(
            key="pokemon:test:001",
            predicted_value=100000.0,
            observed_value=100000.0,
            predicted_confidence=0.90,
            verified=True,
            source_family="official",
            region="KR",
            category="card_price",
            timestamp="2026-09-06T09:00:00+09:00",
        )
        base.update(overrides)
        return VerifiedOutcome(**base)

    def test_unverified_history_is_excluded(self):
        rows = [self.outcome(), self.outcome(key="x", verified=False)]
        self.assertEqual(len(verified_only(rows)), 1)

    def test_insufficient_history_caps_confidence(self):
        report = calibration_report([self.outcome()], min_samples=5)
        self.assertEqual(report.status, "INSUFFICIENT_VERIFIED_HISTORY")
        self.assertLessEqual(report.recommended_confidence_cap, 0.65)

    def test_overconfidence_is_detected(self):
        rows = [
            self.outcome(key=str(i), observed_value=150000.0, predicted_confidence=0.95)
            for i in range(6)
        ]
        report = calibration_report(rows, relative_tolerance=0.10, min_samples=5)
        self.assertIn(report.status, {"OVERCONFIDENT", "DEGRADED"})
        self.assertLess(report.recommended_confidence_cap, 0.95)

    def test_confidence_cap_never_increases_score(self):
        report = calibration_report([self.outcome(key=str(i)) for i in range(5)], min_samples=5)
        self.assertLessEqual(apply_confidence_cap(0.80, report), 0.80)
        self.assertLessEqual(apply_confidence_cap(0.99, report), 0.99)

    def test_calibration_consumes_single_pass_iterable_once(self):
        owner = self

        class SinglePass:
            def __init__(self):
                self.used = False

            def __iter__(self):
                if self.used:
                    raise AssertionError("calibration attempted a second pass")
                self.used = True
                for i in range(10):
                    yield owner.outcome(key=str(i), predicted_value=100.0, observed_value=101.0)

        rows = SinglePass()
        report = calibration_report(rows, min_samples=5)
        self.assertTrue(rows.used)
        self.assertEqual(report.sample_count, 10)
        self.assertIsNotNone(report.mae)

    def test_stable_distribution_is_not_drift(self):
        result = detect_distribution_drift(
            [100, 101, 99, 100, 102],
            [101, 100, 102, 99, 100],
            min_samples=5,
        )
        self.assertFalse(result["drift"])
        self.assertEqual(result["status"], "STABLE")

    def test_large_shift_is_drift(self):
        result = detect_distribution_drift(
            [100, 101, 99, 100, 102],
            [150, 151, 149, 152, 150],
            min_samples=5,
        )
        self.assertTrue(result["drift"])
        self.assertIn("MEDIAN_SHIFT_EXCEEDED", result["reason_codes"])

    def test_recurring_errors_require_strategy_change(self):
        result = recurring_error_memory(["HTTP_429", "HTTP_429", "HTTP_429", "TIMEOUT"])
        self.assertTrue(result["requires_strategy_change"])
        self.assertEqual(result["recurring"][0]["error_code"], "HTTP_429")

    def test_identity_mismatch_quarantines_anomaly(self):
        result = explain_anomaly(
            observed=100,
            expected_center=100,
            expected_spread=5,
            identity_match=False,
        )
        self.assertEqual(result["severity"], "high")
        self.assertEqual(result["recommended_action"], "quarantine_and_reverify")
        self.assertFalse(result["confidence_override_allowed"])

    def test_novel_lineage_stays_provisional(self):
        result = explain_anomaly(
            observed=101,
            expected_center=100,
            expected_spread=5,
            lineage_novel=True,
        )
        self.assertEqual(result["recommended_action"], "provisional_until_corroborated")


if __name__ == "__main__":
    unittest.main()
