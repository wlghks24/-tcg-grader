"""Offline tests for bounded official China catalog retry behavior."""
import datetime as dt
from email.message import Message
from urllib.error import HTTPError
import unittest

try:
    from tcg_reliability.china_official_catalog_v571 import _fetch_with_retry, _retry_after_seconds
except ImportError:
    from china_official_catalog_v571 import _fetch_with_retry, _retry_after_seconds


def http_error(status, retry_after=None):
    headers = Message()
    if retry_after is not None:
        headers['Retry-After'] = retry_after
    return HTTPError('https://www.pokemon.cn/tcg/product', status, 'mock', headers, None)


class RetryTests(unittest.TestCase):
    def test_success_no_delay(self):
        delays = []
        self.assertEqual(_fetch_with_retry(lambda _: 'ok', 'url', sleep=delays.append), 'ok')
        self.assertEqual(delays, [])

    def test_404_no_retry(self):
        calls = []
        def load(url):
            calls.append(url)
            raise http_error(404)
        with self.assertRaises(HTTPError):
            _fetch_with_retry(load, 'url', sleep=lambda _: None)
        self.assertEqual(len(calls), 1)

    def test_transient_503_then_success(self):
        calls, delays = [], []
        def load(url):
            calls.append(url)
            if len(calls) == 1:
                raise http_error(503, '2')
            return 'ok'
        self.assertEqual(_fetch_with_retry(load, 'url', sleep=delays.append), 'ok')
        self.assertEqual(len(calls), 2)
        self.assertEqual(delays, [2.0])

    def test_429_exhausted(self):
        calls, delays = [], []
        def load(url):
            calls.append(url)
            raise http_error(429, '0')
        with self.assertRaises(HTTPError):
            _fetch_with_retry(load, 'url', sleep=delays.append)
        self.assertEqual(len(calls), 3)
        self.assertEqual(delays, [0.0, 0.0])

    def test_500_bounded(self):
        calls, delays = [], []
        def load(url):
            calls.append(url)
            raise http_error(500)
        with self.assertRaises(HTTPError):
            _fetch_with_retry(load, 'url', sleep=delays.append)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(delays), 2)
        self.assertTrue(all(0 <= x <= 8 for x in delays))

    def test_timeout_bounded(self):
        calls = []
        def load(url):
            calls.append(url)
            raise TimeoutError()
        with self.assertRaises(TimeoutError):
            _fetch_with_retry(load, 'url', sleep=lambda _: None)
        self.assertEqual(len(calls), 3)

    def test_retry_after_date_and_invalid(self):
        now = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc)
        self.assertEqual(_retry_after_seconds('999'), 999)
        self.assertEqual(_retry_after_seconds('invalid', now), None)
        self.assertEqual(_retry_after_seconds('Sun, 25 Oct 2026 00:00:05 GMT', now), 5)


    def test_long_numeric_retry_after_preserves_error_without_early_retry(self):
        calls, delays = [], []
        error = http_error(429, '3600')
        def load(url):
            calls.append(url)
            raise error
        with self.assertRaises(HTTPError) as caught:
            _fetch_with_retry(load, 'url', sleep=delays.append)
        self.assertIs(error, caught.exception)
        self.assertEqual(['url'], calls)
        self.assertEqual([], delays)
        self.assertEqual('3600', caught.exception.headers['Retry-After'])

    def test_long_http_date_retry_after_is_not_truncated(self):
        now = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc)
        header = 'Sun, 25 Oct 2026 01:00:00 GMT'
        self.assertEqual(3600, _retry_after_seconds(header, now))
        calls, delays = [], []
        error = http_error(503, 'Fri, 01 Jan 2100 00:00:00 GMT')
        def load(url):
            calls.append(url)
            raise error
        with self.assertRaises(HTTPError) as caught:
            _fetch_with_retry(load, 'url', sleep=delays.append)
        self.assertIs(error, caught.exception)
        self.assertEqual(1, len(calls))
        self.assertEqual([], delays)

    def test_total_wait_budget_never_shortens_second_server_wait(self):
        calls, delays = [], []
        error = http_error(429, '20')
        def load(url):
            calls.append(url)
            raise error
        with self.assertRaises(HTTPError) as caught:
            _fetch_with_retry(load, 'url', sleep=delays.append)
        self.assertIs(error, caught.exception)
        self.assertEqual(2, len(calls))
        self.assertEqual([20.0], delays)

    def test_attempt_count_cannot_expand_or_disable_policy(self):
        for count in (0, 4, True, 1.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                _fetch_with_retry(lambda _: self.fail('invalid attempts made request'), 'url', attempts=count)

    def test_nonfinite_or_negative_retry_after_is_not_a_valid_delay(self):
        for value in ('nan', 'inf', '-1'):
            self.assertIsNone(_retry_after_seconds(value))


if __name__ == '__main__':
    unittest.main()
