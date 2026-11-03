"""Offline raw JSON transport fixtures; no real HTTP, images, or device run."""
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import tablet_image_auto_v2 as auto
from execution import tablet_provider_json_v900 as raw

URL = 'https://raw.githubusercontent.com/Kuroro1990/OPTCG/main/english/packs.json'
ORIGINAL_ONEPIECE = auto.candidates_onepiece


class Budget:
    def __init__(self, provider='PunkRecords'):
        self.provider = provider
        self.requests, self.charged, self.blocks = [], [], []
    def byte_allowance(self): return 10000
    def remaining_seconds(self): return 100
    def reserve_request(self, provider):
        self.requests.append(provider); return {'request': len(self.requests)}
    def add_bytes(self, entry, size): self.charged.append(size)
    def block(self, *values): self.blocks.append(values)


class Response:
    def __init__(self, data=b'{"569001":{"raw_title":"Test"}}', mime='text/plain; charset=utf-8', url=URL, status=200, length=None):
        self.raw = io.BytesIO(data)
        self.headers = {'Content-Type': mime}
        if length is not None: self.headers['Content-Length'] = length
        self.url, self.status = url, status
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def geturl(self): return self.url
    def read1(self, size): return self.raw.read(size)
    def read(self, size): return self.raw.read(size)


class RawJsonTests(unittest.TestCase):
    def setUp(self):
        self.budget = Budget()
        self.previous = getattr(auto._BUDGET_CONTEXT, 'current', None)
        auto._BUDGET_CONTEXT.current = self.budget
        self.addCleanup(self.restore)
    def restore(self):
        if self.previous is None: del auto._BUDGET_CONTEXT.current
        else: auto._BUDGET_CONTEXT.current = self.previous
    def read(self, response=None, url=URL):
        opener = SimpleNamespace(open=lambda *args, **kwargs: response or Response(url=url))
        with patch.object(raw, 'build_opener', return_value=opener):
            return raw.read_json(auto, url, raw.provider_for(url))

    def test_original_rejects_valid_plaintext_json_but_new_path_decodes_it(self):
        opener = SimpleNamespace(open=lambda *a, **k: Response())
        with patch.object(auto.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(auto.ProviderError, 'MIME'):
                auto.fetch_binary(URL, auto.MAX_PROVIDER_BYTES)
        self.assertIn('569001', self.read())
        self.assertEqual(['PunkRecords', 'PunkRecords'], self.budget.requests)
        self.assertGreater(self.budget.charged[-1], 0)

    def test_image_transport_still_rejects_plaintext(self):
        opener = SimpleNamespace(open=lambda *a, **k: Response(url='https://assets.tcgdex.net/en/test.png'))
        with patch.object(auto.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(auto.ProviderError, 'MIME'):
                auto.fetch_binary('https://assets.tcgdex.net/en/test.png')

    def test_exact_raw_paths_only(self):
        valid = [URL, URL.replace('english', 'japanese'), URL.replace('english', 'chinese-taiwan'),
                 URL.replace('packs.json', 'data/569001.json'), raw.RIFTBOUND]
        for url in valid: self.assertIsNotNone(raw.provider_for(url))
        for url in [URL+'?x=1', URL+'#x', URL.replace('main', 'other'), URL.replace('english', 'korean'),
                    URL.replace('packs.json', '../cards.json'), URL.replace('https://', 'http://'),
                    URL.replace('raw.githubusercontent.com', 'raw.githubusercontent.com.evil.invalid'),
                    URL.replace('https://', 'https://user@'), None, [], raw.RIFTBOUND+'/']:
            self.assertIsNone(raw.provider_for(url))

    def test_missing_or_wrong_budget_does_not_open_http(self):
        for current in (None, Budget('TCGdex')):
            auto._BUDGET_CONTEXT.current = current
            with patch.object(raw, 'build_opener') as build:
                with self.assertRaises(auto.ProviderError): raw.read_json(auto, URL, 'PunkRecords')
                build.assert_not_called()

    def test_bad_json_duplicates_nan_scalars_and_html_rejected(self):
        for data in [b'<html>private</html>', b'{"x":1,"x":2}', b'{"x":NaN}', b'null', b'42', b'"text"', b'\xff']:
            with self.assertRaises(auto.ProviderError): self.read(Response(data=data))

    def test_valid_json_mimes_and_containers(self):
        for mime in raw.MIMES:
            for value in ({'name': '한글'}, [{'id': '001'}]):
                self.assertEqual(value, self.read(Response(data=json.dumps(value).encode(), mime=mime)))

    def test_missing_html_and_image_mime_rejected_even_with_json_body(self):
        for mime in ('', 'text/html', 'image/png'):
            with self.assertRaisesRegex(auto.ProviderError, 'MIME'): self.read(Response(mime=mime))

    def test_size_limits_charge_bytes_and_never_return_partial_json(self):
        for length in ('10001', '-1', 'invalid'):
            with self.assertRaises(auto.ProviderError): self.read(Response(length=length))
        with self.assertRaises(auto.ProviderError): self.read(Response(data=b' ' * 10001))
        self.assertEqual(10000, self.budget.charged[-1])

    def test_changed_status_or_response_url_rejected(self):
        for response in (Response(status=201), Response(url=URL+'?changed')):
            with self.assertRaises(auto.ProviderError): self.read(response)

    def test_valid_json_with_declared_truncated_or_overlong_body_is_not_success(self):
        for length in ('1', '20'):
            with self.assertRaisesRegex(auto.ProviderError, '길이'):
                self.read(Response(data=b'[]', length=length))
        self.assertEqual([], self.read(Response(data=b'[]', length='2')))

    def test_direct_reader_rejects_nonallowlisted_url_even_with_none_provider(self):
        self.budget.provider = None
        with patch.object(raw, 'build_opener') as build:
            with self.assertRaises(auto.ProviderError):
                raw.read_json(auto, 'https://raw.githubusercontent.com/other/data/main/list.json', None)
            build.assert_not_called()

    def test_http_403_429_preserves_cooldown_and_closes_body_without_reading(self):
        for code in (403, 429):
            body = io.BytesIO(b'private provider body')
            error = HTTPError(URL, code, 'private', {'Retry-After': '7200'}, body)
            opener = SimpleNamespace(open=lambda *a, **k: (_ for _ in ()).throw(error))
            with patch.object(raw, 'build_opener', return_value=opener):
                with self.assertRaisesRegex(auto.ProviderError, str(code)):
                    raw.read_json(auto, URL, 'PunkRecords')
            self.assertTrue(body.closed)
            self.assertEqual(('PunkRecords', code, '7200'), self.budget.blocks[-1])

    def test_deadline_after_read_including_eof_is_not_success(self):
        for times in ([0, 0, 13], [0, 13]):
            with patch.object(raw.time, 'monotonic', side_effect=times):
                with self.assertRaises(auto.policy.Deferred): self.read()

    def test_proxy_disabled_redirect_denied_and_read_method_is_get(self):
        opened = []
        def open_request(request, **kwargs): opened.append(request); return Response()
        with patch.object(raw, 'build_opener', return_value=SimpleNamespace(open=open_request)) as build:
            raw.read_json(auto, URL, 'PunkRecords')
        self.assertEqual({}, build.call_args.args[0].proxies)
        with self.assertRaises(auto.ProviderError):
            build.call_args.args[1].redirect_request(None, None, 302, '', {}, URL+'?moved')
        self.assertEqual('GET', opened[0].get_method())

    def test_no_allowance_or_exhausted_request_budget_blocks_network(self):
        with patch.object(self.budget, 'byte_allowance', return_value=0), patch.object(raw, 'build_opener') as build:
            with self.assertRaises(auto.policy.Deferred): self.read()
            build.assert_not_called()
        with patch.object(self.budget, 'reserve_request', side_effect=auto.policy.Deferred('quota')), patch.object(raw, 'build_opener') as build:
            with self.assertRaises(auto.policy.Deferred): self.read()
            build.assert_not_called()

    def test_installer_idempotent_falls_back_for_other_urls_and_refuses_live_worker(self):
        seen = []
        original = lambda url: seen.append(url) or 'fallback'
        fake = SimpleNamespace(fetch_json=original, _THREAD=None, _SCHEDULER=None)
        raw.install(fake); installed = fake.fetch_json; raw.install(fake)
        self.assertIs(installed, fake.fetch_json)
        self.assertEqual('fallback', fake.fetch_json('https://api.tcgdex.net/v2/en/cards'))
        with patch.object(raw, 'read_json', return_value={'cards': []}) as read:
            self.assertEqual({'cards': []}, fake.fetch_json(URL))
            read.assert_called_once_with(fake, URL, 'PunkRecords')
        self.assertEqual(['https://api.tcgdex.net/v2/en/cards'], seen)
        fake.fetch_json = original; fake._THREAD = object()
        with self.assertRaises(RuntimeError): raw.install(fake)
        self.assertIs(original, fake.fetch_json)


class PagingTests(unittest.TestCase):
    def records(self, count=306, region='US'):
        host = auto.ONEPIECE_LOCALES[region][1]
        return [{'id': 'OP01-' + str(index).zfill(3), 'pack_id': '569901', 'name': 'Card',
                 'img_full_url': 'https://' + host + '/images/cardlist/card/OP01-' + str(index).zfill(3) + '.png'}
                for index in range(1, count + 1)]

    def source(self, rows):
        return lambda url: {'569901': {'raw_title': 'Test pack'}} if url.endswith('/packs.json') else rows

    def test_306_card_set_original_loses_tail_new_paging_preserves_all_and_old_cursors(self):
        with patch.object(auto, 'fetch_json', side_effect=self.source(self.records())):
            original, fixed = [], []
            for page in range(1, 26):
                original.extend(ORIGINAL_ONEPIECE('US', page)[0])
                result, next_page = raw.onepiece_candidates(auto, 'US', page)
                fixed.extend(result)
                self.assertEqual(page + 1, next_page)
            self.assertEqual(200, len(original))
            self.assertEqual(306, len(fixed))
            self.assertEqual(306, len({row['key'] for row in fixed}))
            self.assertEqual(original[:192], fixed[:192])

    def test_tail_still_uses_exact_country_host_and_source_identity(self):
        rows = self.records(306, 'JP')
        rows[200]['img_full_url'] = self.records(201, 'US')[200]['img_full_url']
        with patch.object(auto, 'fetch_json', side_effect=self.source(rows)):
            result, next_page = raw.onepiece_candidates(auto, 'JP', 25)
        self.assertEqual(113, len(result))
        self.assertEqual(26, next_page)
        self.assertTrue(all(row['region'] == 'JP' and '/japanese/' in row['source'] for row in result))

    def test_oversized_sets_and_bad_cursor_refuse_and_empty_set_ends(self):
        with patch.object(auto, 'fetch_json', side_effect=self.source(self.records(1501))):
            with self.assertRaises(auto.ProviderError): raw.onepiece_candidates(auto, 'US', 25)
        for page in (0, True, 100001):
            with self.assertRaises(auto.ProviderError): raw.onepiece_candidates(auto, 'US', page)
        with patch.object(auto, 'fetch_json', return_value={}):
            self.assertEqual(([], 1), raw.onepiece_candidates(auto, 'US', 25))


if __name__ == '__main__':
    unittest.main()
