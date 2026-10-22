"""Register the rebuilt private bundle in the existing full repository CI."""
import unittest

MODULES=(
 'execution.tests.test_tablet_catalog_bridge','execution.tests.test_restored_private_images',
 'execution.tests.test_image_collection_policy','execution.tests.test_box_country_navigation',
 'execution.tests.test_tablet_navigation_actions','execution.tests.test_ui_navigation_audit',
 'execution.tests.test_feature_source_bundle','tcg_reliability.test_china_official_catalog_v571',
)

def load_tests(loader,tests,pattern):
    for module in MODULES:tests.addTests(loader.loadTestsFromName(module))
    return tests

if __name__=='__main__':unittest.main()
