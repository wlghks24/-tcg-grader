"""Image-cache budget successor; every relocated link regression remains executed."""
import unittest

def load_tests(loader,tests,pattern):
    for name in ('execution.tests.test_image_successor_v663','execution.tests.test_image_cache_budget_v663','execution.tests.test_tablet_image_training','execution.tests.test_pokemon_retired_link_migration_v356'):
        tests.addTests(loader.loadTestsFromName(name))
    return tests

if __name__=='__main__':unittest.main()
