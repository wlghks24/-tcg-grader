import unittest
import grading_cert_verifier as g

class CertVerifierTests(unittest.TestCase):
    def test_supported_companies_have_official_lookup(self):
        for c in ('PSA','BGS','CGC','TAG','BRG'):
            self.assertTrue(g.lookup_url(c,'12345678').startswith('https://'))
    def test_short_cert_is_not_verified(self):
        r=g.verify_cert('PSA','12')
        self.assertFalse(r['verified'])
    def test_unknown_company_rejected(self):
        r=g.verify_cert('UNKNOWN','12345678')
        self.assertFalse(r['ok'])
    def test_parser_requires_grade_context(self):
        self.assertIsNone(g._grade_from_text('BGS','cert 12345678 population 10'))
        self.assertEqual(g._grade_from_text('BGS','FINAL GRADE 9.5 CERT NUMBER 12345678'),9.5)

if __name__=='__main__': unittest.main()
