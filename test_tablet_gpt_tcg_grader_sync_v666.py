"""Exact evidence successor, all relocated and new boundary cases executed."""
import unittest

def load_tests(loader,tests,pattern):
    for name in ('execution.tests.test_evidence_successor_v666','execution.tests.test_image_receipt_integrity_v666','execution.tests.test_dashboard_verified_boundary_v246','tcg_reliability.test_neural_label_safety_20261025','tcg_reliability.test_job_neural_postflight_20261025','tcg_reliability.test_event_title_date_safety_20261025','tcg_reliability.test_china_catalog_retry_20261025','tcg_reliability.test_china_official_catalog_v571'):
        tests.addTests(loader.loadTestsFromName(name))
    return tests

if __name__=='__main__':unittest.main()
