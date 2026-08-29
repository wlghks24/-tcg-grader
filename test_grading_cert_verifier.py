import unittest
from unittest import mock
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

    def test_all_companies_require_company_cert_and_grade(self):
        pages={
            'PSA':'PSA CERTIFICATION NUMBER 12345678 ITEM GRADE GEM MT 10',
            'BGS':'BECKETT BGS CERT NUMBER 12345678 FINAL GRADE 9.5',
            'CGC':'CGC CERTIFICATION 12345678 CARD GRADE PRISTINE 10',
            'TAG':'TAG CERT 12345678 CARD GRADE 10',
            'BRG':'BRG CERTIFICATION 12345678 CARD GRADE 10',
        }
        for company,page in pages.items():
            expected=9.5 if company=='BGS' else 10.0
            with self.subTest(company=company),mock.patch.object(g,'_fetch',return_value=page):
                result=g.verify_cert(company,'12345678',expected_grade=expected)
                self.assertTrue(result['verified'])
                self.assertEqual(result['grade'],expected)

    def test_official_grade_mismatch_is_conflict_not_verified(self):
        page='PSA CERTIFICATION NUMBER 12345678 ITEM GRADE GEM MT 10'
        with mock.patch.object(g,'_fetch',return_value=page):
            result=g.verify_cert('PSA','12345678',expected_grade=9)
        self.assertFalse(result['verified'])
        self.assertTrue(result['conflict'])

    def test_company_marker_without_exact_cert_is_not_verified(self):
        page='PSA CERTIFICATION NUMBER 87654321 ITEM GRADE GEM MT 10'
        with mock.patch.object(g,'_fetch',return_value=page):
            result=g.verify_cert('PSA','12345678',expected_grade=10)
        self.assertFalse(result['verified'])

if __name__=='__main__': unittest.main()
