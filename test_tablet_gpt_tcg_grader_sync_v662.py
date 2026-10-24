"""Image-retention successor; every relocated diagnostic case remains executed."""
import unittest

def load_tests(loader,tests,pattern):
    for name in ('execution.tests.test_image_successor_v662','execution.tests.test_image_autonomy_v661','execution.tests.test_tablet_image_training','execution.tests.test_v426_successor_path_diagnostics_v635'):
        tests.addTests(loader.loadTestsFromName(name))
    return tests

if __name__=='__main__':unittest.main()
