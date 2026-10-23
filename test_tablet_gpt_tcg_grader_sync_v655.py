"""V655 exact source, discovery and filter regressions."""
import unittest
def load_tests(loader,tests,pattern):
    for name in ['execution.tests.test_source_collection_v655','execution.tests.test_info_filters_v655','execution.tests.test_source_successor_v655','execution.tests.test_current_runtime_verifier_v295']:
        tests.addTests(loader.loadTestsFromName(name))
    return tests
if __name__=='__main__':unittest.main()
