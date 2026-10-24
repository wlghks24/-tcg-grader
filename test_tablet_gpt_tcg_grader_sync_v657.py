"""V657 exact-source, learning scan budget, provider wait and preview regression."""
import unittest

def load_tests(loader,tests,pattern):
    for name in ('execution.tests.test_learning_successor_v657','execution.tests.test_learning_scan_budget_v657','execution.tests.test_provider_wait_v657','execution.tests.test_tablet_local_ui_review','execution.tests.test_info_filters_v655','execution.tests.test_collection_coverage_completion_v143'):
        tests.addTests(loader.loadTestsFromName(name))
    return tests

if __name__=='__main__':unittest.main()
