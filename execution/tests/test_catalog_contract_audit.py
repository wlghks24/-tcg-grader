import unittest
from execution.catalog_contract_audit import audit

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

    def test_fail_closed(self):
        self.assertEqual(audit("unknown", "unknown")["status"], "UNKNOWN")

if __name__ == "__main__":
    unittest.main()
