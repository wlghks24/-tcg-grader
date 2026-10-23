from __future__ import annotations

import unittest

import verify_current_runtime as runtime


class CurrentRuntimeVerifierV295Tests(unittest.TestCase):
    def test_assert_based_v182_selftest_runs_as_script(self) -> None:
        commands = {name: cmd for name, cmd, _timeout, _optional in runtime._commands()}
        self.assertIn("runtime_resilience_v182", commands)
        cmd = commands["runtime_resilience_v182"]
        self.assertEqual("test_runtime_resilience_v182.py", cmd[-1])
        self.assertNotIn("unittest", cmd)

    def test_unittest_aggregate_no_longer_contains_zero_test_script(self) -> None:
        commands = {name: cmd for name, cmd, _timeout, _optional in runtime._commands()}
        aggregate = commands["current_runtime_regressions"]
        self.assertNotIn("test_runtime_resilience_v182.py", aggregate)
        self.assertIn("test_grading_hierarchy_v17.py", aggregate)
        self.assertIn("test_ocr_multistage_v16.py", aggregate)


if __name__ == "__main__":
    unittest.main(verbosity=2)
