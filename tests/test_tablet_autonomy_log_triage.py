"""Regression tests for read-only autonomy log classification."""
import json
import tempfile
import unittest
from pathlib import Path

from execution.tablet_autonomy_log_triage import classify_log


class AutonomyLogTriageTests(unittest.TestCase):
    def classify(self, *lines):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "autonomy.log"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return classify_log(path)

    def test_verified_hold_not_reported_as_success(self):
        report = self.classify(json.dumps({
            "v387_autonomous_gate": {"reasons": ["LOW_VERIFIED_CONFIDENCE", "HIGH_UNCERTAINTY"]},
            "v400_autonomous_gate": {"allow_execution": False, "status": "V400_UPSTREAM_HOLD"},
            "execution": {"executed": False, "status": "V400_UPSTREAM_HOLD"},
        }))
        self.assertEqual(report["classification"], "SAFETY_HOLD")
        self.assertFalse(report["execution_observed"])
        self.assertEqual(report["reasons"], ["LOW_VERIFIED_CONFIDENCE", "HIGH_UNCERTAINTY"])

    def test_status_only_is_not_proof_of_hold(self):
        report = self.classify(json.dumps({
            "v400_autonomous_gate": {"status": "V400_UPSTREAM_HOLD"},
            "execution": {"status": "V400_UPSTREAM_HOLD"},
        }))
        self.assertEqual(report["classification"], "UNKNOWN")

    def test_executed_does_not_claim_success(self):
        report = self.classify(json.dumps({
            "v400_autonomous_gate": {"allow_execution": True, "status": "V400_VERIFIED_ALLOW"},
            "execution": {"executed": True, "status": "FAILED"},
        }))
        self.assertEqual(report["classification"], "EXECUTION_OBSERVED")

    def test_malformed_log(self):
        self.assertEqual(self.classify("bad-json")["classification"], "INVALID_LOG")

    def test_oversized_line_is_rejected_without_unbounded_read(self):
        report = self.classify("x" * 5_000_001)
        self.assertEqual(report["classification"], "INVALID_LOG")
        self.assertEqual(report["reasons"], ["OVERSIZE_LINE"])

    def test_exactly_100000_lines_are_allowed(self):
        hold = json.dumps({
            "v400_autonomous_gate": {"allow_execution": False, "status": "V400_UPSTREAM_HOLD"},
            "execution": {"executed": False, "status": "V400_UPSTREAM_HOLD"},
        })
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "at-limit.log"
            path.write_text("{}\n" * 99_999 + hold + "\n", encoding="utf-8")
            report = classify_log(path)
        self.assertEqual(report["classification"], "SAFETY_HOLD")
        self.assertNotIn("TOO_MANY_LINES", report["reasons"])

    def test_100001_lines_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "over-limit.log"
            path.write_text("{}\n" * 100_001, encoding="utf-8")
            report = classify_log(path)
        self.assertEqual(report["classification"], "INVALID_LOG")
        self.assertEqual(report["reasons"], ["TOO_MANY_LINES"])

    def test_bounded_reader_still_accepts_normal_hold(self):
        self.test_verified_hold_not_reported_as_success()

    def test_malformed_trailing_record_fails_closed(self):
        hold = json.dumps({
            "v400_autonomous_gate": {"allow_execution": False, "status": "UPSTREAM_HOLD"},
            "execution": {"executed": False, "status": "UPSTREAM_HOLD"},
        })
        report = self.classify(hold, '{"v400_autonomous_gate":')
        self.assertEqual(report["classification"], "INVALID_LOG")
        self.assertEqual(report["reasons"], ["MALFORMED_RECORD"])
        self.assertFalse(report["execution_observed"])

    def test_plain_text_noise_does_not_override_gate(self):
        hold = json.dumps({
            "v400_autonomous_gate": {"allow_execution": False, "status": "UPSTREAM_HOLD"},
            "execution": {"executed": False, "status": "UPSTREAM_HOLD"},
        })
        self.assertEqual(self.classify(hold, "process exited")["classification"], "SAFETY_HOLD")

    def test_missing_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = classify_log(Path(tmp) / "missing.log")
            self.assertEqual(report["classification"], "LOG_READ_ERROR")

    def test_unrelated_json(self):
        self.assertEqual(self.classify('{"ok":true}')["classification"], "UNKNOWN")

    def test_last_complete_gate_record_wins(self):
        hold = json.dumps({
            "v400_autonomous_gate": {"allow_execution": False, "status": "V400_UPSTREAM_HOLD"},
            "execution": {"executed": False, "status": "V400_UPSTREAM_HOLD"},
        })
        failed = json.dumps({
            "v400_autonomous_gate": {"allow_execution": True, "status": "V400_VERIFIED_ALLOW"},
            "execution": {"executed": False, "status": "FAILED"},
        })
        self.assertEqual(self.classify(hold, failed)["classification"], "UNKNOWN")

    def test_previous_hold_reasons_do_not_leak_into_later_failure(self):
        hold = json.dumps({
            "v387_autonomous_gate": {"reasons": ["LOW_VERIFIED_CONFIDENCE"]},
            "v400_autonomous_gate": {"allow_execution": False, "status": "UPSTREAM_HOLD"},
            "execution": {"executed": False, "status": "UPSTREAM_HOLD"},
        })
        failed = json.dumps({
            "v400_autonomous_gate": {"allow_execution": True, "status": "VERIFIED_ALLOW"},
            "execution": {"executed": False, "status": "FAILED"},
        })
        report = self.classify(hold, failed)
        self.assertEqual(report["classification"], "UNKNOWN")
        self.assertEqual(report["reasons"], [])

    def test_hold_requires_both_statuses(self):
        report = self.classify(json.dumps({
            "v400_autonomous_gate": {"allow_execution": False, "status": "V400_UPSTREAM_HOLD"},
            "execution": {"executed": False, "status": "FAILED"},
        }))
        self.assertEqual(report["classification"], "UNKNOWN")

    def test_concurrent_hold_classified_safely(self):
        report = self.classify(json.dumps({
            "v400_autonomous_gate": {"allow_execution": False, "status": "V400_CONCURRENT_AUTONOMY_HOLD"},
            "execution": {"executed": False, "status": "V400_CONCURRENT_AUTONOMY_HOLD"},
        }))
        self.assertEqual(report["classification"], "SAFETY_HOLD")


if __name__ == "__main__":
    unittest.main()
