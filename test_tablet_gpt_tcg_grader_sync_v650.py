"""V650 exact recovery lineage and retained market parser regressions."""
import unittest


def load_tests(loader, tests, pattern):
    for module in ('execution.tests.test_china_preserved_update_v650',
                   'execution.tests.test_update_market_prices_packmagik_v353',
                   'execution.tests.test_china_successor_v650'):
        tests.addTests(loader.loadTestsFromName(module))
    return tests


if __name__ == '__main__':
    unittest.main()
