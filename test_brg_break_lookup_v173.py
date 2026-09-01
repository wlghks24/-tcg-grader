import importlib
import unittest

import grading_cert_verifier as verifier
import manual_official_proof as proof
import pending_official_candidate_v161 as pending


class BrgBreakLookupV173Tests(unittest.TestCase):
    def test_brg_direct_url_uses_break_korea_and_preserves_leading_zero(self):
        self.assertEqual(
            verifier.lookup_url("BRG", "0175992"),
            "https://break.co.kr/certification/0175992",
        )

    def test_brg_hosts_are_break_korea(self):
        cfg = verifier.OFFICIAL["BRG"]
        self.assertEqual(cfg["home"], "https://break.co.kr/certification")
        self.assertIn("break.co.kr", cfg["hosts"])
        self.assertNotIn("brgcard.com", cfg["hosts"])

    def test_manual_proof_public_refreshes_legacy_brg_link(self):
        row = {
            "registration_id": "manual-20260902000000-abcdefabcdef",
            "company": "BRG",
            "certification_id": "0175992",
            "claimed_grade": 10.0,
            "official_reference_url": "https://www.brgcard.com/certification?cert=0175992",
        }
        public = proof._proof_public(row)
        self.assertEqual(public["official_reference_url"], "https://break.co.kr/certification/0175992")

    def test_break_brand_is_accepted_for_manual_proof_and_negative_proof(self):
        self.assertTrue(proof._company_in_text("BREAK grading certification", "BRG"))
        self.assertIn("BREAK", pending._COMPANY_BRANDS["BRG"])


if __name__ == "__main__":
    unittest.main()
