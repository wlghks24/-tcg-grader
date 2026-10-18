#!/usr/bin/env python3
"""V643 regression: never infer website failure solely from HEAD 403.

Official GET must actually succeed, and rate limits must never trigger a retry.
No live HTTP or DNS is used in these tests.
"""
import unittest
import urllib.error
from unittest import mock

import update_purchase_sources as purchase

URL = "https://pokemonkorea.co.kr/"
SOURCE = {"name": "공식 제품", "url": URL}


class _Response:
    def __init__(self, url=URL):
        self.url = url

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False


class _Opener:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.methods = []

    def open(self, request, timeout=None):
        self.methods.append(request.get_method())
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _http(code, headers=None):
    return urllib.error.HTTPError(URL, code, "http-error", headers or {}, None)


class OfficialHeadGetFallbackV643Tests(unittest.TestCase):
    def _probe(self, outcomes):
        opener = _Opener(outcomes)
        with (mock.patch.object(purchase, "resolve_public_host"),
              mock.patch.object(purchase, "require_public_https"),
              mock.patch.object(purchase.urllib.request, "build_opener", return_value=opener)):
            result = purchase.probe(SOURCE)
        return result[1], opener.methods

    def test_head_403_public_get_200_proves_live_homepage(self):
        status, methods = self._probe([_http(403), _Response()])
        self.assertEqual(status, "정상")
        self.assertEqual(methods, ["HEAD", "GET"])

    def test_get_403_remains_access_blocked(self):
        status, methods = self._probe([_http(403), _http(403)])
        self.assertEqual(status, "접속 제한·기존 주소 유지 (HTTP 403)")
        self.assertEqual(methods, ["HEAD", "GET"])

    def test_head_403_retry_after_is_not_retried(self):
        status, methods = self._probe([_http(403, {"Retry-After": "120"})])
        self.assertEqual(status, "접속 제한·기존 주소 유지 (HTTP 403)")
        self.assertEqual(methods, ["HEAD"])

    def test_head_429_is_not_retried(self):
        status, methods = self._probe([_http(429, {"Retry-After": "60"})])
        self.assertEqual(status, "접속 제한·기존 주소 유지 (HTTP 429)")
        self.assertEqual(methods, ["HEAD"])

    def test_get_410_still_requires_reconfirmation(self):
        status, methods = self._probe([_http(410), _http(410)])
        self.assertIn("HTTPError: status 410", status)
        self.assertEqual(methods, ["HEAD", "GET"])

    def test_head_200_avoids_second_request(self):
        status, methods = self._probe([_Response()])
        self.assertEqual(status, "정상")
        self.assertEqual(methods, ["HEAD"])

    def test_head_403_then_get_410_never_claims_success(self):
        status, methods = self._probe([_http(403), _http(410)])
        self.assertTrue(status.startswith("재확인 필요"), status)
        self.assertEqual(methods, ["HEAD", "GET"])


if __name__ == "__main__":
    unittest.main()
