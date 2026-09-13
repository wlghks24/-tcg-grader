import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import grading_company_watch as w


class GradingTransportRecoveryTests(unittest.TestCase):
    url = 'https://www.cgccards.com/news/'

    def response(self, body=b'fresh official page'):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = body
        return response

    def test_read_timeout_closes_response_and_retries_once(self):
        first, second = self.response(), self.response()
        first.read.side_effect = TimeoutError('read timeout')
        with patch.object(w, 'safe_urlopen', side_effect=[first, second]) as fetch, patch.object(w.time, 'sleep') as sleep:
            self.assertEqual(w._fetch_raw(self.url), 'fresh official page')
        self.assertEqual(fetch.call_count, 2)
        first.__exit__.assert_called_once()
        second.__exit__.assert_called_once()
        sleep.assert_called_once_with(1.0)
        self.assertEqual(fetch.call_args.kwargs['allowed_hosts'], w.ALLOWED_HOSTS)

    def test_access_denial_and_host_rejection_are_not_retried(self):
        for error in [HTTPError(self.url, code, 'blocked', {}, None) for code in (401, 403, 404, 429)] + [ValueError('unapproved host')]:
            with self.subTest(error=str(error)), patch.object(w, 'safe_urlopen', side_effect=error) as fetch, patch.object(w.time, 'sleep') as sleep:
                with self.assertRaises(type(error)):
                    w._fetch_raw(self.url)
                self.assertEqual(fetch.call_count, 1)
                sleep.assert_not_called()

    def test_retry_after_is_respected_and_long_wait_is_deferred(self):
        for value, retry in [('2', True), ('68', False), ('invalid', False),
                             ('Wed, 01 Jan 2098 00:00:00 GMT', False)]:
            error = HTTPError(self.url, 503, 'unavailable', {'Retry-After': value}, None)
            with self.subTest(value=value), patch.object(w, 'safe_urlopen', side_effect=[error, self.response()]) as fetch, patch.object(w.time, 'sleep') as sleep:
                if retry:
                    self.assertEqual(w._fetch_raw(self.url), 'fresh official page')
                    sleep.assert_called_once_with(2.0)
                else:
                    with self.assertRaises(HTTPError):
                        w._fetch_raw(self.url)
                    sleep.assert_not_called()
                self.assertEqual(fetch.call_count, 2 if retry else 1)

    def test_exhausted_retry_preserves_last_good(self):
        spec = w.WATCH_SOURCES['CGC'][2]
        previous = {'sources': {spec['id']: {
            'url': spec['url'], 'verified_official_source': True,
            'signal_fingerprint': 'verified-baseline', 'services': [],
            'announcements': [{'url': spec['url'], 'title': 'Verified announcement'}]}}}
        with patch.object(w, 'WATCH_SOURCES', {'CGC': (spec,)}), patch.object(w, 'safe_urlopen', side_effect=URLError(TimeoutError('timeout'))) as fetch, patch.object(w.time, 'sleep') as sleep:
            out = w.collect(previous, fetcher=w._fetch_raw)
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once()
        self.assertEqual(out['sources'][spec['id']]['status'], 'degraded')
        self.assertEqual(out['sources'][spec['id']]['announcements'], previous['sources'][spec['id']]['announcements'])
        self.assertNotEqual(out['collection_status'], '정상')


if __name__ == '__main__':
    unittest.main()
