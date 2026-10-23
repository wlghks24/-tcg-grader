"""V654 exact source and bounded metadata repair regressions."""
import unittest
def load_tests(loader,tests,pattern):
    for name in ['execution.tests.test_metadata_repair_v654','execution.tests.test_metadata_successor_v654']:
        tests.addTests(loader.loadTestsFromName(name))
    return tests
if __name__=='__main__':unittest.main()
