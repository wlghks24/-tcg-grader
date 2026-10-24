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
        self.assertEqual(_retry_after_seconds('999'), 30)
        self.assertEqual(_retry_after_seconds('invalid', now), None)
        self.assertEqual(_retry_after_seconds('Sun, 25 Oct 2026 00:00:05 GMT', now), 5)


if __name__ == '__main__':
    unittest.main()
