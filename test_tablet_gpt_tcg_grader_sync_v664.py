"""Image-retention successor; every relocated diagnostic case remains executed."""
import unittest

def load_tests(loader,tests,pattern):
    for name in ('execution.tests.test_image_successor_v664','execution.tests.test_image_worker_isolation_v664','execution.tests.test_tablet_image_training','execution.tests.test_promo_discovery_worker_isolation_v513'):
        tests.addTests(loader.loadTestsFromName(name))
    return tests

if __name__=='__main__':unittest.main()
