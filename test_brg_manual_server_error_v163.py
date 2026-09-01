import unittest
from pathlib import Path
import pending_official_candidate_v161 as pending

class Tests(unittest.TestCase):
    def test_server_error_not_no_record(self):
        s=pending._negative_ocr("Application error: a server-side exception has occurred. Digest: 3089131211",{},"BRG")
        self.assertTrue(s["site_error_detected"])
        self.assertFalse(s["negative_text_detected"])
    def test_no_record(self):
        s=pending._negative_ocr("BRG no records found",{},"BRG")
        self.assertFalse(s["site_error_detected"])
        self.assertTrue(s["negative_text_detected"])
        self.assertTrue(s["company_brand_detected"])
    def test_brg_form_url(self):
        src=Path("pending_official_candidate_bridge_v161.js").read_text(encoding="utf-8")
        self.assertIn("if(c==='BRG')return 'https://www.brgcard.com/certification'",src)
        self.assertIn("Application error / server-side exception / Digest",src)
        self.assertNotIn("const url=bgsDirect(",src)

if __name__=='__main__': unittest.main()
