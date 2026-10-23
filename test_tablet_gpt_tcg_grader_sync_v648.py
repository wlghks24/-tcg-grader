"""Exact V648 sync boundary and retained private-data recovery regressions."""
import unittest


def load_tests(loader, tests, pattern):
    for module in ('execution.tests.test_graphify_preserved_update_v648',
                   'execution.tests.test_tcg_local_collection_v505',
                   'execution.tests.test_graphify_successor_v648'):
        tests.addTests(loader.loadTestsFromName(module))
    return tests


if __name__ == '__main__':
    unittest.main()
