"""Exact V649 boundary and retained recovery / card identity behavior checks."""
import unittest


def load_tests(loader, tests, pattern):
    for module in ('execution.tests.test_observed_source_recovery_v649',
                   'execution.tests.test_update_market_price_identity_v523',
                   'execution.tests.test_observed_source_successor_v649'):
        tests.addTests(loader.loadTestsFromName(module))
    return tests


if __name__ == '__main__':
    unittest.main()
