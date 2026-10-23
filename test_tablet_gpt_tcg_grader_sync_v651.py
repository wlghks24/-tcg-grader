"""V651 native Android handoff, update guidance and exact successor evidence."""
import unittest


def load_tests(loader, tests, pattern):
    for module in ('execution.tests.test_android_handoff_v651',
                   'execution.tests.test_update_guidance_consistency_v218',
                   'execution.tests.test_android_successor_v651'):
        tests.addTests(loader.loadTestsFromName(module))
    return tests


if __name__ == '__main__':
    unittest.main()
