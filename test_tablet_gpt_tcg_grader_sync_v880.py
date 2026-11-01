"""V880 catalog/image successor, including every existing market evidence test."""
import unittest

def load_tests(loader, tests, pattern):
    for name in ('execution.tests.test_catalog_image_successor_v880',
                 'execution.tests.test_catalog_image_runtime_v880',
                 'execution.tests.test_market_catalog_evidence_v547',
                 'execution.tests.test_catalog_contract_audit'):
        tests.addTests(loader.loadTestsFromName(name))
    return tests

if __name__ == '__main__':
    unittest.main()
