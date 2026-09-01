import unittest
import manual_official_proof as proof

class PsaManualProofV166Tests(unittest.TestCase):
    def test_korean_translated_psa_gem_mt_10_matches(self):
        text = 'PSA 인증번호 87105158 품목 등급 젬 MT 10 PSA 추정치 75.00달러'
        result = proof._match_proof(
            row={}, text=text, evidence={}, company='PSA', cert='87105158', expected_grade=10.0
        )
        self.assertTrue(result['company_match'])
        self.assertTrue(result['cert_match'])
        self.assertTrue(result['grade_match'])
        self.assertTrue(result['matched'])

    def test_pending_candidate_can_use_exact_existing_slab_grade_fallback(self):
        text = 'PSA Certification 87105158'
        row = {'ocr_company':'PSA','ocr_certification_id':'87105158','ocr_grade':10.0}
        result = proof._match_proof(
            row=row, text=text, evidence={}, company='PSA', cert='87105158', expected_grade=10.0
        )
        self.assertTrue(result['matched'])
        self.assertTrue(result['slab_grade_fallback'])

    def test_wrong_cert_still_rejected(self):
        text = 'PSA 인증번호 87105159 품목 등급 젬 MT 10'
        result = proof._match_proof(
            row={}, text=text, evidence={}, company='PSA', cert='87105158', expected_grade=10.0
        )
        self.assertFalse(result['cert_match'])
        self.assertFalse(result['matched'])

if __name__ == '__main__':
    unittest.main()
