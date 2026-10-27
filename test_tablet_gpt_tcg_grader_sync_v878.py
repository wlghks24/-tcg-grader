"""Register exact dock source evidence and executable local navigation coverage."""
import unittest


def load_tests(loader, tests, pattern):
    for name in ('execution.tests.test_dock_successor_v878',
                 'execution.tests.test_dock_behavior_v878',
                 'execution.tests.test_tablet_app_dock_v275',
                 'execution.tests.test_tablet_dock_navigation_contract',
                 'tests.test_dock_navigation_source_contract_v877'):
        tests.addTests(loader.loadTestsFromName(name))
    return tests


if __name__ == '__main__': unittest.main()
