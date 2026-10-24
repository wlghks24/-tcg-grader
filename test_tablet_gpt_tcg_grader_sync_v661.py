"""Exact image-learning successor plus all relocated V619 regression cases."""
import unittest

def load_tests(loader,tests,pattern):
    for name in ('execution.tests.test_image_successor_v661','execution.tests.test_image_autonomy_v661','execution.tests.test_tablet_image_training','execution.tests.test_free_only_ai_code_improver_v619'):
        tests.addTests(loader.loadTestsFromName(name))
    return tests

if __name__=='__main__':unittest.main()
