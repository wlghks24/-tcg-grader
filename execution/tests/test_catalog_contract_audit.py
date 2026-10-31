import unittest
from execution.catalog_contract_audit import audit, audit_surfaces

class CatalogContractAuditTests(unittest.TestCase):
    def test_mismatch_detected(self):
        js = "if(!['KR','JP','US','GLOBAL'].includes(country))return false;"
        py = 'REGIONS = frozenset({"KR","JP","US","CN-S","CN-T"})'
        result = audit(js, py)
        self.assertEqual(result["status"], "MISMATCH")
        self.assertEqual(result["image_only"], ["CN-S", "CN-T"])
        self.assertEqual(result["expander_only"], ["GLOBAL"])

    def test_match(self):
        js = "if(!['KR','JP'].includes(country))return false;"
        py = 'REGIONS = frozenset({"KR","JP"})'
        self.assertEqual(audit(js, py)["status"], "MATCH")

    def test_surface_mismatch_and_image_paths(self):
        expander = "if(!['KR','JP','US','GLOBAL'].includes(country))return false; value.image_url"
        detail = 'const REGIONS = {KR:"한국",JP:"일본",US:"미국",CN:"중국", "CN-S":"간체", "CN-T":"번체"};'
        # Real detail declarations use unquoted hyphenated region keys.
        detail = 'const REGIONS = {KR:"한국",JP:"일본",US:"미국",CN:"중국",CN-S:"간체",CN-T:"번체"};'
        result = audit_surfaces(expander, detail, '"/catalog-links"', "def _set_box_image(")
        self.assertEqual(result["status"], "MISMATCH")
        self.assertIn("CN", result["detail_only"])
        self.assertTrue(result["static_reviewed_box_sync"])
        self.assertTrue(result["local_image_reconciliation"])

    def test_fail_closed(self):
        self.assertEqual(audit("unknown", "unknown")["status"], "UNKNOWN")

if __name__ == "__main__":
    unittest.main()
