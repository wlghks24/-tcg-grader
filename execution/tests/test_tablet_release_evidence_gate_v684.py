import unittest
from execution.tablet_release_evidence_gate_v684 import evaluate

SHA_A = "a" * 40
SHA_B = "b" * 40

def valid():
    return {
        "ci_pass": True, "regression_pass": True,
        "runtime_route_pass": True, "data_api_pass": True,
        "rollback_pass": True, "physical_tablet_verified": True,
        "verified_main_sha": SHA_A, "tablet_running_sha": SHA_A,
        "tablet_receipt": {"running_sha": SHA_A, "verified": True},
        "unresolved_required_checks": 0,
    }

class ReleaseGateTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(evaluate(valid()), [])
    def test_missing_evidence(self):
        self.assertTrue(evaluate({}))
    def test_sha_mismatch(self):
        x = valid(); x["tablet_running_sha"] = SHA_B
        self.assertTrue(evaluate(x))
    def test_missing_physical_receipt(self):
        x = valid(); x["physical_tablet_verified"] = False
        self.assertTrue(evaluate(x))
    def test_failed_ci(self):
        x = valid(); x["ci_pass"] = False
        self.assertTrue(evaluate(x))
    def test_unresolved_checks(self):
        x = valid(); x["unresolved_required_checks"] = 1
        self.assertTrue(evaluate(x))

if __name__ == "__main__":
    unittest.main()
