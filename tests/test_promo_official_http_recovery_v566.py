#!/usr/bin/env python3
"""Official HTTP outage simulation, without network or fabricated event facts."""
from __future__ import annotations

import urllib.error
import unittest
from unittest import mock
import update_promo_events as promo

SOURCE = promo.POKEMON_KR_NEWS


class Response:
    def __init__(self, payload: bytes, url: str = SOURCE):
        self.payload, self.url, self.read_limit = payload, url, None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self.url

    def read(self, count):
        self.read_limit = count
        return self.payload[:count]


def http_error(code: int, retry_after: str | None = None):
    headers = {} if retry_after is None else {"Retry-After": retry_after}
    return urllib.error.HTTPError(SOURCE, code, "simulated outage", headers, None)


class OfficialPromoHttpRecoveryTests(unittest.TestCase):
    def invoke(self, effects):
        opener = mock.Mock()
        opener.open.side_effect = effects
        with mock.patch.object(promo.urllib.request, "build_opener", return_value=opener), \
             mock.patch.object(promo.time, "sleep") as sleeper:
            result = promo.fetch(SOURCE)
        return result, opener, sleeper

    def test_503_same_url_retry_once(self):
        result, opener, sleeper = self.invoke([http_error(503), Response(b"verified source")])
        self.assertEqual(result, "verified source")
        self.assertEqual([call.args[0].full_url for call in opener.open.call_args_list], [SOURCE, SOURCE])
        sleeper.assert_called_once_with(0.25)

    def test_short_retry_after_respected(self):
        result, opener, sleeper = self.invoke([http_error(503, "1"), Response(b"ok")])
        self.assertEqual(result, "ok")
        self.assertEqual(opener.open.call_count, 2)
        sleeper.assert_called_once_with(1.0)

    def test_never_retry_blocked_or_rate_limited(self):
        for code in (401, 403, 429, 451):
            with self.subTest(code=code):
                opener = mock.Mock()
                opener.open.side_effect = http_error(code)
                with mock.patch.object(promo.urllib.request, "build_opener", return_value=opener), \
                     mock.patch.object(promo.time, "sleep") as sleeper:
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        promo.fetch(SOURCE)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(opener.open.call_count, 1)
                sleeper.assert_not_called()

    def test_unbounded_retry_after_defers(self):
        for raw in ("60", "999", "Wed, 21 Oct 2026 15:00:00 GMT", "invalid"):
            with self.subTest(raw=raw):
                opener = mock.Mock()
                opener.open.side_effect = http_error(503, raw)
                with mock.patch.object(promo.urllib.request, "build_opener", return_value=opener), \
                     mock.patch.object(promo.time, "sleep") as sleeper:
                    with self.assertRaises(urllib.error.HTTPError):
                        promo.fetch(SOURCE)
                self.assertEqual(opener.open.call_count, 1)
                sleeper.assert_not_called()

    def test_retry_exhaustion_does_not_fabricate_success(self):
        opener = mock.Mock()
        opener.open.side_effect = [http_error(503), http_error(503)]
        with mock.patch.object(promo.urllib.request, "build_opener", return_value=opener), \
             mock.patch.object(promo.time, "sleep") as sleeper:
            with self.assertRaises(urllib.error.HTTPError):
                promo.fetch(SOURCE)
        self.assertEqual(opener.open.call_count, 2)
        sleeper.assert_called_once()

    def test_oversized_response_rejected_not_truncated_to_fact(self):
        response = Response(b"x" * (promo.EVENT_PAGE_LIMIT + 1))
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(promo.urllib.request, "build_opener", return_value=opener), \
             mock.patch.object(promo.time, "sleep") as sleeper:
            with self.assertRaisesRegex(ValueError, "exceeded"):
                promo.fetch(SOURCE)
        self.assertEqual(response.read_limit, promo.EVENT_PAGE_LIMIT + 1)
        self.assertEqual(opener.open.call_count, 1)
        sleeper.assert_not_called()

    def test_invalid_origin_blocked_before_request(self):
        with mock.patch.object(promo.urllib.request, "build_opener") as opener:
            with self.assertRaises(ValueError):
                promo.fetch("https://unapproved.example/data")
        opener.assert_not_called()

    def test_redirect_escape_blocked_even_after_response(self):
        opener = mock.Mock()
        opener.open.return_value = Response(b"untrusted", "https://unapproved.example")
        with mock.patch.object(promo.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(ValueError):
                promo.fetch(SOURCE)
        self.assertEqual(opener.open.call_count, 1)

    def test_protocol_contract(self):
        self.assertEqual(promo.EVENT_TRANSIENT_HTTP, {408, 425, 500, 502, 503, 504})
        self.assertEqual(promo.OfficialRedirect.max_redirections, 3)


if __name__ == "__main__":
    unittest.main()
