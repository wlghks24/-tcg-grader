"""V658 standard HTML parsing and complete relocated regression coverage."""
import unittest

def load_tests(loader,tests,pattern):
    for name in ('execution.tests.test_alignment_partitions_v659','execution.tests.test_verification_successor_v658','execution.tests.test_info_filters_v655','execution.tests.test_collection_coverage_completion_v143','execution.tests.test_card_catalog_region_isolation_v317','execution.tests.test_tablet_local_ui_review'):
        tests.addTests(loader.loadTestsFromName(name))
    return tests

if __name__=='__main__':unittest.main()
