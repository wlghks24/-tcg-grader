"""Fail-closed V400 cold-start classification tests (synthetic fixture only)."""
import json
import tempfile
import unittest
from pathlib import Path
from execution.tablet_autonomy_bootstrap_status import classify

def blocked_report():
    return {
        "v400_status": "V400_UPSTREAM_HOLD",
        "execution": {
            "status": "V400_UPSTREAM_HOLD",
            "executed": False,
            "source_code_modified": False,
            "git_write": False,
        },
        "v400_autonomous_gate": {"allow_execution": False},
        "v387_autonomous_gate": {
            "status": "V387_UNCERTAINTY_HOLD",
            "allow_execution": False,
            "reasons": ["LOW_VERIFIED_CONFIDENCE", "HIGH_UNCERTAINTY"],
        },
    }

class TabletAutonomyBootstrapStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / "log.txt"

    def record(self, data):
        self.log.write_text("preflight ok\nself-test ok\n" + json.dumps(data) + "\n", encoding="utf-8")

    def test_missing_all_evidence_is_bootstrap_hold_not_failed(self):
        self.record(blocked_report())
        self.assertEqual("BOOTSTRAP_EVIDENCE_HOLD", classify(self.root, self.log))

    def test_existing_meta_outcome_is_not_assumed_valid(self):
        (self.root / "tablet_autonomy_verified_outcomes.jsonl").write_text("invalid\n", encoding="utf-8")
        self.record(blocked_report())
        self.assertEqual("VERIFIED_UPSTREAM_HOLD", classify(self.root, self.log))

    def test_symlink_input_cannot_be_reported_as_missing(self):
        (self.root / "tablet_autonomy_verified_outcomes.jsonl").symlink_to(self.root / "nonexistent")
        self.record(blocked_report())
        self.assertEqual("VERIFIED_UPSTREAM_HOLD", classify(self.root, self.log))

    def test_other_hold_keeps_protection(self):
        payload = blocked_report()
        payload["v387_autonomous_gate"]["reasons"] = ["STATE_CORRUPTION_HOLD"]
        self.record(payload)
        self.assertEqual("VERIFIED_UPSTREAM_HOLD", classify(self.root, self.log))

    def test_success_is_not_a_hold(self):
        payload = blocked_report()
        payload["v400_status"] = "V400_VERIFIED_ALLOW"
        self.record(payload)
        self.assertEqual("FAILED", classify(self.root, self.log))

    def test_claimed_execution_not_misclassified(self):
        payload = blocked_report()
        payload["execution"]["executed"] = True
        self.record(payload)
        self.assertEqual("FAILED", classify(self.root, self.log))

    def test_malformed_and_missing_logs_are_failed(self):
        self.assertEqual("FAILED", classify(self.root, self.log))
        self.log.write_text("not a report\n", encoding="utf-8")
        self.assertEqual("FAILED", classify(self.root, self.log))

    def test_log_symlink_is_failed(self):
        real = self.root / "real.txt"
        real.write_text(json.dumps(blocked_report()) + "\n", encoding="utf-8")
        self.log.symlink_to(real)
        self.assertEqual("FAILED", classify(self.root, self.log))

    def test_scheduler_integration_is_fail_closed(self):
        source = Path(__file__).with_name("TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        self.assertIn('if [ "$rc" -eq 2 ]; then', source)
        self.assertIn('python "$ROOT/execution/tablet_autonomy_bootstrap_status.py"', source)
        self.assertIn('write_autonomy_status "EVIDENCE_BOOTSTRAP_HOLD"', source)
        self.assertIn('return "$rc"', source)

if __name__ == "__main__":
    unittest.main()
