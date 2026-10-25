"""Exact evidence successor, all relocated and new boundary cases executed."""
import unittest

def load_tests(loader,tests,pattern):
    for name in ('execution.tests.test_evidence_successor_v667','execution.tests.test_source_object_cache_v667','execution.tests.test_manual_registration_delete_v151','tcg_reliability.test_neural_label_safety_20261025','test_collection_scope_compat_v214','execution.tests.test_pr814_source_preflight_v665'):
        tests.addTests(loader.loadTestsFromName(name))
    return tests

if __name__=='__main__':unittest.main()
