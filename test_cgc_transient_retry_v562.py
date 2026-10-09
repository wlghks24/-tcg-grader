#!/usr/bin/env python3
"""V562 bounded retry behavior for official CGC endpoints (offline)."""
from __future__ import annotations
import urllib.error
import unittest
from unittest import mock

import grading_company_watch_resilient as watch


class CgcTransientRetryV562Tests(unittest.TestCase):
    @staticmethod
    def cgc():
        return next(iter(watch.CGC_CANONICAL_URLS))

    @staticmethod
    def http_error(url, code):
        return urllib.error.HTTPError(url, code, "mock", {}, None)

    def test_timeout_recovers_once_and_success_is_memoized(self):
        url = self.cgc()
        calls = []
        def request(raw):
            calls.append(raw)
            if len(calls) == 1:
                raise urllib.error.URLError(TimeoutError("read timed out"))
            return ("CGC official", raw)
        with mock.patch.object(watch.time, "sleep") as delay:
            cached, stats = watch._make_cached_requester(request)
            self.assertEqual(("CGC official", url), cached(url))
            self.assertEqual(("CGC official", url), cached(url))
        self.assertEqual(calls, [url, url])
        self.assertEqual(stats["transient_cgc_retry_attempts"], 1)
        self.assertEqual(stats["transient_cgc_retry_recovered"], 1)
        self.assertEqual(stats["transient_cgc_retry_exhausted"], 0)
        self.assertEqual(stats["network_calls"], 1)
        self.assertEqual(stats["cache_hits"], 1)
        delay.assert_called_once_with(watch.CGC_TRANSIENT_RETRY_SECONDS)

    def test_temporary_server_errors_get_one_identical_url_retry(self):
        for code in (408, 425, 500, 502, 503, 504):
            with self.subTest(status=code):
                url = self.cgc()
                calls = []
                def requester(raw):
                    calls.append(raw)
                    if len(calls) == 1:
                        raise self.http_error(raw, code)
                    return ("verified html", raw)
                with mock.patch.object(watch.time, "sleep"):
                    cached, stats = watch._make_cached_requester(requester)
                    self.assertEqual(cached(url)[1], url)
                self.assertEqual(calls, [url, url])
                self.assertEqual(stats["transient_cgc_retry_recovered"], 1)

    def test_restricted_and_broken_errors_never_retry(self):
        for code in (400, 401, 403, 404, 410, 429, 451, 501):
            with self.subTest(status=code):
                url = self.cgc()
                calls = []
                def requester(raw):
                    calls.append(raw)
                    raise self.http_error(raw, code)
                with mock.patch.object(watch.time, "sleep") as delay:
                    cached, stats = watch._make_cached_requester(requester)
                    with self.assertRaises(urllib.error.HTTPError):
                        cached(url)
                self.assertEqual(calls, [url])
                self.assertEqual(stats["transient_cgc_retry_attempts"], 0)
                delay.assert_not_called()

    def test_non_cgc_and_unregistered_urls_are_never_retried(self):
        for url in ("https://www.psacard.com/services/tradingcardgrading",
                    "https://www.cgccards.com/other/path",
                    "https://www.cgccards.com.evil.invalid/news/"):
            with self.subTest(url=url):
                calls = []
                def requester(raw):
                    calls.append(raw)
                    raise self.http_error(raw, 502)
                cached, stats = watch._make_cached_requester(requester)
                with mock.patch.object(watch.time, "sleep") as delay:
                    with self.assertRaises(urllib.error.HTTPError):
                        cached(url)
                self.assertEqual(calls, [url])
                self.assertEqual(stats["transient_cgc_retry_attempts"], 0)
                delay.assert_not_called()

    def test_parser_security_and_nontransient_network_failures_never_retry(self):
        failures = (ValueError("parser schema changed"),
                    urllib.error.URLError("Name or service not known"),
                    PermissionError("access denied"))
        for failure in failures:
            with self.subTest(error=str(failure)):
                url = self.cgc()
                calls = []
                def requester(raw):
                    calls.append(raw)
                    raise failure
                cached, stats = watch._make_cached_requester(requester)
                with mock.patch.object(watch.time, "sleep") as delay:
                    with self.assertRaises(type(failure)):
                        cached(url)
                self.assertEqual(calls, [url])
                self.assertEqual(stats["transient_cgc_retry_attempts"], 0)
                delay.assert_not_called()

    def test_retry_is_bounded_and_failed_responses_are_not_cached(self):
        url = self.cgc()
        calls = []
        def requester(raw):
            calls.append(raw)
            raise self.http_error(raw, 502)
        cached, stats = watch._make_cached_requester(requester)
        with mock.patch.object(watch.time, "sleep") as delay:
            with self.assertRaises(urllib.error.HTTPError):
                cached(url)
        self.assertEqual(len(calls), 2, "one additional attempt maximum")
        self.assertEqual(stats["transient_cgc_retry_attempts"], 1)
        self.assertEqual(stats["transient_cgc_retry_exhausted"], 1)
        self.assertEqual(stats["transient_cgc_retry_recovered"], 0)
        self.assertEqual(stats["network_calls"], 0)
        delay.assert_called_once()
        # A future explicit caller may retry, but no stale error/success is
        # cached and this layer never misrepresents provider health.
        fresh, fresh_stats = watch._make_cached_requester(lambda _: ("", url))
        self.assertEqual(fresh_stats["network_calls"], 0)

    def test_successful_cgc_without_failure_does_not_retry(self):
        url = self.cgc()
        calls = []
        def requester(raw):
            calls.append(raw)
            return ("ok", raw)
        cached, stats = watch._make_cached_requester(requester)
        cached(url)
        self.assertEqual(calls, [url])
        self.assertEqual(stats["transient_cgc_retry_attempts"], 0)

if __name__ == "__main__":
    unittest.main()
