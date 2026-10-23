"""V652 exact successor and functional regressions; no synthetic device claim."""
import unittest

def load_tests(loader,tests,pattern):
    for name in ['execution.tests.test_android_successor_v651', 'execution.tests.test_country_reset_v652', 'execution.tests.test_image_collection_policy', 'execution.tests.test_image_metadata_enrichment', 'execution.tests.test_learning_status_eligibility_v652', 'execution.tests.test_release_date_evidence_v652', 'execution.tests.test_ui_recording_repairs', 'test_tablet_learning_progress', 'test_verified_collection_neural_v211', 'execution.tests.test_continuous_successor_v652']:
        tests.addTests(loader.loadTestsFromName(name))
    return tests

if __name__=="__main__":unittest.main()
