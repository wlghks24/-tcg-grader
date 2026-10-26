"""Offline attack regressions for fixed-origin lookup and bounded regex work."""
from __future__ import annotations

import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

import multi_market_price_collector as market
import purchase_intelligence as purchase
import safe_runtime


ROOT = Path(__file__).resolve().parents[2]


class MarketCollectorSecurityTests(unittest.TestCase):
    def test_ambiguous_whitespace_does_not_consume_quadratic_cpu(self):
        # A separate process supplies an execution bound and cannot freeze the
        # remaining suite if these adversarial expressions regress. At 100k
        # spaces the old adjacent stars take tens of seconds per failed match.
        code = """
import multi_market_price_collector as m
for prefix in ('PSA', 'BGS:', 'SWSH', 'PAL'):
    text = prefix + ' ' * 100_000 + 'X'
    assert list(m.GRADER_QUERY_RE.finditer(text)) == []
    assert list(m.CARD_NUMBER_QUERY_RE.finditer(text)) == []
    assert m._tcgdex_query_parts(text)[1] == ''
"""
        completed = subprocess.run(
            [sys.executable, '-c', code], cwd=ROOT, capture_output=True,
            text=True, timeout=8, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_whitespace_and_optional_separators_preserve_card_identity(self):
        for token, expected in (
            ('SWSH 025', 'SWSH025'), ('SWSH - 025', 'SWSH025'),
            ('SVP\t-\t025', 'SVP025'), ('PAL 185/193', 'PAL185/193'),
            ('PAL - 185/193', 'PAL-185/193'), ('OP13-007', 'OP13-007'),
        ):
            with self.subTest(token=token):
                _, number = market._tcgdex_query_parts('Pikachu ' + token)
                self.assertEqual(market._normalize_card_number(number), expected)

    def test_grader_separators_and_decimal_grades_never_become_card_ids(self):
        for label in ('PSA 10', 'PSA : 10', 'PSA # 10', 'PSA - 10.0',
                      'BGS\t:\t9.5', 'BGS 10 BLACK LABEL', 'CGC 9.5'):
            with self.subTest(label=label):
                name, number = market._tcgdex_query_parts('Pikachu ' + label)
                self.assertEqual(name, 'Pikachu')
                self.assertEqual(number, '')
                self.assertEqual(market._identity_blob_numbers(label), [])

    def test_query_url_payloads_remain_on_fixed_search_origin(self):
        attack = 'https://127.0.0.1:443/#@evil.test/?x=1&q=override\r\nX:1'
        response = b'<rss><channel/></rss>'
        for loader, owner in ((lambda: market._rss(attack), market),
                              (lambda: purchase._BASE_SEARCH_WEB_SIGNALS_V112(attack), purchase)):
            with self.subTest(module=owner.__name__), \
                 patch.object(owner, 'safe_urlopen', return_value=io.BytesIO(response)) as opened:
                loader()
                request = opened.call_args.args[0]
                parsed = urlsplit(request.full_url)
                self.assertEqual((parsed.scheme, parsed.netloc, parsed.path),
                                 ('https', 'www.bing.com', '/search'))
                params = parse_qs(parsed.query)
                self.assertEqual(set(params), {'format', 'q'})
                self.assertIn(attack, params['q'][0])
                self.assertEqual(opened.call_args.kwargs['allowed_hosts'],
                                 {'www.bing.com', 'bing.com'})

    def test_ebay_authorization_uses_no_redirect_transport(self):
        attack = 'https://127.0.0.1/#@evil.test/?q=x&limit=999'
        with patch.dict(market.os.environ, {'EBAY_OAUTH_TOKEN': 'fixture-token'}), \
             patch.object(market, 'safe_urlopen') as ordinary, \
             patch.object(market, 'safe_urlopen_no_redirect',
                          return_value=io.BytesIO(b'{"itemSummaries":[]}')) as protected:
            self.assertEqual(market._ebay_api(attack, 'US', {'KRW': 1}), [])
        ordinary.assert_not_called()
        request = protected.call_args.args[0]
        parsed = urlsplit(request.full_url)
        self.assertEqual((parsed.scheme, parsed.netloc, parsed.path),
                         ('https', 'api.ebay.com', '/buy/browse/v1/item_summary/search'))
        params = parse_qs(parsed.query)
        self.assertEqual(set(params), {'q', 'limit'})
        self.assertEqual(params['limit'], ['20'])
        self.assertEqual(params['q'], [attack + ' English'])
        self.assertEqual(protected.call_args.kwargs['allowed_hosts'], {'api.ebay.com'})

    def test_authenticated_transport_rejects_same_host_redirect(self):
        request = Request('https://api.ebay.com/buy/browse/v1/item_summary/search?q=x',
                          headers={'Authorization': 'Bearer fixture-token'})

        class RedirectResponse:
            def __init__(self, handler):
                self.handler = handler

            def open(self, req, timeout):
                return self.handler.redirect_request(
                    req, None, 302, 'redirect', {}, 'https://api.ebay.com/other',
                )

        with patch.object(safe_runtime, 'require_public_https') as validate, \
             patch.object(safe_runtime.urllib.request, 'build_opener',
                          side_effect=lambda handler: RedirectResponse(handler)):
            with self.assertRaises(HTTPError) as raised:
                safe_runtime.safe_urlopen_no_redirect(
                    request, timeout=15, allowed_hosts={'api.ebay.com'},
                )
        self.assertEqual(raised.exception.code, 302)
        self.assertEqual(validate.call_count, 1)

    def test_search_redirects_cannot_leave_allowlisted_origins(self):
        request = Request('https://www.bing.com/search?q=fixture')
        handler = safe_runtime.PublicHTTPSRedirect({'www.bing.com', 'bing.com'})
        for destination in ('https://127.0.0.1/private', 'https://evil.example/',
                            'https://www.bing.com.evil.example/',
                            'https://www.bing.com@evil.example/'):
            with self.subTest(destination=destination), \
                 patch.object(safe_runtime.socket, 'getaddrinfo') as dns:
                with self.assertRaises(ValueError):
                    handler.redirect_request(request, None, 302, 'redirect', {}, destination)
                dns.assert_not_called()

    def test_allowlisted_name_resolving_to_private_ip_is_blocked_before_open(self):
        with patch.object(safe_runtime.socket, 'getaddrinfo',
                          return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]), \
             patch.object(safe_runtime.urllib.request, 'build_opener') as opener:
            with self.assertRaisesRegex(ValueError, 'private dns target blocked'):
                safe_runtime.safe_urlopen(
                    Request('https://www.bing.com/search?q=fixture'), timeout=12,
                    allowed_hosts={'www.bing.com', 'bing.com'},
                )
        opener.assert_not_called()


if __name__ == '__main__':
    unittest.main()
