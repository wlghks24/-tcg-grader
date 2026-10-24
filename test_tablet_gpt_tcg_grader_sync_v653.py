"""V653 exact successor and workspace event/image regressions."""
import unittest
def load_tests(loader,tests,pattern):
    for name in ['execution.tests.test_workspace_features_v653','execution.tests.test_workspace_successor_v653']:
        tests.addTests(loader.loadTestsFromName(name))
    return tests
if __name__=='__main__':unittest.main()
