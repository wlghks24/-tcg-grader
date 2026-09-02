import os
import unittest
from unittest import mock

import grading_cert_verifier as g


class CertVerifierTests(unittest.TestCase):
    def test_supported_companies_have_official_lookup_links(self):
        for company in ('PSA', 'BGS', 'CGC', 'TAG', 'BRG'):
            with self.subTest(company=company):
                self.assertTrue(g.lookup_url(company, '12345678').startswith('https://'))

    def test_brg_uses_current_break_certification_route(self):
        self.assertEqual(
            g.lookup_url('BRG', '0346643'),
            'https://break.co.kr/certification/0346643',
        )

    def test_short_cert_is_not_verified(self):
        result = g.verify_cert('PSA', '12')
        self.assertFalse(result['verified'])

    def test_unknown_company_rejected(self):
        result = g.verify_cert('UNKNOWN', '12345678')
        self.assertFalse(result['ok'])

    def test_parser_requires_grade_context(self):
        self.assertIsNone(g._grade_from_text('BGS', 'cert 12345678 population 10'))
        self.assertEqual(
            g._grade_from_text('BGS', 'FINAL GRADE 9.5 CERT NUMBER 12345678'),
            9.5,
        )

    def _assert_manual_only(self, company, env_value):
        with mock.patch.dict(
            os.environ,
            {g.DISABLE_AUTO_LOOKUP_ENV: env_value},
            clear=False,
        ), mock.patch.object(g, '_fetch') as fetch:
            result = g.verify_cert(company, '12345678', expected_grade=10)
        fetch.assert_not_called()
        self.assertFalse(result['verified'])
        self.assertTrue(result['automatic_lookup_disabled'])
        self.assertTrue(result['manual_verification_required'])
        self.assertEqual(result['mode'], 'manual_user_browser_required')
        self.assertTrue(result['official_url'].startswith('https://'))

    def test_all_companies_are_manual_only(self):
        for company in ('PSA', 'BGS', 'CGC', 'TAG', 'BRG'):
            with self.subTest(company=company):
                self._assert_manual_only(company, '1')

    def test_environment_cannot_reenable_automatic_lookup(self):
        for company in ('PSA', 'BGS', 'CGC', 'TAG', 'BRG'):
            with self.subTest(company=company):
                self._assert_manual_only(company, '0')


if __name__ == '__main__':
    unittest.main()
