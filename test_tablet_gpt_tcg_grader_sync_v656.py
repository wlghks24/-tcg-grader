"""V656 exact source, registry recovery and account scheduling regressions."""
import unittest
def load_tests(loader,tests,pattern):
    for name in ['execution.tests.test_source_recovery_v656','execution.tests.test_source_recovery_successor_v656','execution.tests.test_grading_proxy_costs','execution.tests.test_tablet_local_automation_v656','execution.tests.test_tablet_learning_entrypoint']:
        tests.addTests(loader.loadTestsFromName(name))
    return tests
if __name__=='__main__':unittest.main()
