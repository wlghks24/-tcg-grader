"""V646 exact sync generation and private feature regressions; device proof separate."""
import unittest
from execution.tests.private_catalog_test_registration_v645 import MODULES

def load_tests(loader,tests,pattern):
    for module in MODULES+("execution.tests.test_tablet_document_locations",
                           "execution.tests.test_tablet_runtime_handoff",
                           "execution.tests.test_tablet_successor_v646"):
        tests.addTests(loader.loadTestsFromName(module))
    return tests

if __name__=="__main__":unittest.main()
