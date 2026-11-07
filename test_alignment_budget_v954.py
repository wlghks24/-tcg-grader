"""Root-suite registration: execute V954 successor negatives in isolated CI shards.

The behavior fixtures live under execution/tests; only this registration
runs them in the existing four-shard Exhaustive SELFREFINE root suite.
"""
from execution.tests.test_alignment_budget_v954 import AlignmentBudgetV954Tests


if __name__ == "__main__":
    import unittest
    unittest.main()
