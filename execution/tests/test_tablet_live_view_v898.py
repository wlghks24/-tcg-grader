"""Partial-source/cold-photo regressions. Pure projections and mocked HTTP only."""
import copy
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from http.client import IncompleteRead
from types import SimpleNamespace

from execution import tablet_catalog_bridge as bridge
from execution import tablet_image_unified_v888 as images
from execution import tablet_live_view_v898 as live
from execution import tablet_device_readback_v897 as device
from execution.tablet_unified_ui_v890 import render_document

SHA = 'a29e5973d2824958467747a198b4d77d06f9464c'
IMG = '1' * 32
SRC = '2' * 32


def report():
    common = dict(game_id='pokemon', region='JP', kind='CARD', name='Card <script>bad()</script>',
                  product_codes=['SV1S001'], language='ja', printing='Normal', set_code='sv1s')
    return {'ok': True, 'summary': {'source_limit_reached': False}, 'source_errors': [],
            'local_catalog': [dict(common, id=IMG, card_metadata={'card_number': '001', 'language': 'ja'})],
            'source_catalog': [dict(common, source_record_id=SRC, source_health='HEALTHY', source_url='https://api.tcgdex.net/v2/ja/cards/sv1s-001')],
            'catalog_matches': [{'id': IMG, 'source_record_id': SRC, 'match': 'CODE_MATCH', 'game_id': 'pokemon', 'region': 'JP', 'kind': 'CARD'}]}


class LiveViewTests(unittest.TestCase):
    def partial(self, *, error=False):
        data = report(); data['catalog_matches'] = []
        if error: data['source_errors'] = [{'dataset': 'market_prices.json', 'error': 'ValueError'}]
        else: data['summary']['source_limit_reached'] = True
        return data

    def test_strict_collector_default_still_rejects_incomplete_report(self):
        for data in (self.partial(), self.partial(error=True)):
            with self.assertRaises(ValueError): images.unified_feed(data)
            with self.assertRaises(ValueError): images.export_html(data)

    def test_explicit_display_keeps_both_objects_unlinked_and_does_not_change_report(self):
        data = self.partial(); before = copy.deepcopy(data)
        rows = images.unified_feed(data, allow_partial_display=True)
        self.assertEqual(2, len(rows))
        self.assertEqual(data, before)
        self.assertTrue(all(r['display_only'] and r['catalog_overlay'] is None for r in rows))
        self.assertEqual({'SOURCE_COVERAGE_INCOMPLETE'}, {r['link_status'] for r in rows})
        self.assertEqual('001', next(r for r in rows if r['image_id'])['card_metadata']['card_number'])

    def test_partial_report_cannot_smuggle_a_match(self):
        data = self.partial(); data['catalog_matches'] = report()['catalog_matches']
        with self.assertRaises(ValueError): images.unified_feed(data, allow_partial_display=True)

    def test_display_mode_never_accepts_invalid_identity_or_failed_catalog(self):
        for mutate in [lambda r: r.update(ok=False), lambda r: r['local_catalog'][0].update(id='../unsafe'),
                       lambda r: r['source_catalog'][0].update(region='invalid')]:
            data = self.partial(); mutate(data)
            with self.assertRaises(ValueError): images.unified_feed(data, allow_partial_display=True)
        with self.assertRaises(ValueError): images.unified_feed(report(), allow_partial_display='yes')

    def test_partial_view_skips_canonical_projection_and_creates_no_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(live, 'build_report', return_value=self.partial()), patch.object(live, 'project') as project, patch.object(live, 'read_event_summary', return_value={'ok': False}):
                view = live.read_view(root)
                page = live.render_live(view)
                project.assert_not_called()
            self.assertEqual([], list(root.iterdir()))
        self.assertEqual('PARTIAL_READ_ONLY', view['view_state'])
        self.assertIn('일부 자료만 표시 중', page)
        self.assertIn('자동 연결·저장·학습하지 않습니다', page)
        self.assertNotIn('사진·정보 연결됨', page)

    def test_complete_view_retains_verified_pair_and_uses_canonical_projection(self):
        data = report(); expected = images.unified_feed(data)
        with patch.object(live, 'build_report', return_value=data), patch.object(live, 'project', return_value=expected) as project, patch.object(live, 'read_event_summary', return_value={'ok': False}), patch.object(live.library, 'storage_root', return_value=Path('/fixture')):
            view = live.read_view(Path('/fixture'))
        self.assertEqual('COMPLETE', view['view_state'])
        self.assertEqual('VERIFIED_PAIR', view['rows'][0]['link_status'])
        project.assert_called_once()

    def test_page_does_not_encode_or_read_photo_bytes_even_with_many_photos(self):
        rows = images.unified_feed(report())
        rows = [dict(rows[0], image_id=f'{i:032x}', image_url='/api/local-card-images/file/' + f'{i:032x}') for i in range(100)]
        with patch.object(images, 'cached_display', side_effect=AssertionError('encoding in page GET')), patch.object(live.library, 'get_image', side_effect=AssertionError('photo bytes in page GET')):
            page = live.render_live({'view_state': 'COMPLETE', 'rows': rows})
        self.assertEqual(100, page.count('/api/local-card-images/display/'))
        self.assertEqual(100, page.count('data-original="/api/local-card-images/file/'))
        self.assertLess(page.index("document.addEventListener('error'"), page.index('<img '))
        self.assertIn('loading="lazy"', page)
        self.assertNotIn('data:image/', page)
        self.assertIn('원본 확대', page)
        self.assertNotIn('<script>bad()</script>', page)

    def test_live_images_are_same_origin_and_standalone_remains_data_only(self):
        self.assertIn("img-src data: 'self';", render_document([], [], live=True))
        self.assertIn('img-src data:;', render_document([], []))
        self.assertNotIn('img-src *', render_document([], [], live=True))

    def test_real_ten_thousand_price_row_guard_can_render_partial_view_without_waiver(self):
        def payload(path, max_bytes):
            return {'entries': {str(i): {} for i in range(10001)}} if path.name == 'market_prices.json' else {'items': []}
        with patch.object(bridge, 'read_json', side_effect=payload):
            sources, errors, _, truncated = bridge.source_rows(Path('/fixture'), {}, {})
        self.assertTrue(errors)
        data = self.partial(error=True); data['source_errors'] = errors
        data['source_catalog'] = sources; data['summary']['source_limit_reached'] = truncated
        with patch.object(live, 'build_report', return_value=data), patch.object(live, 'read_event_summary', return_value={'ok': False}), patch.object(live, 'project') as project:
            page = live.render_live(live.read_view(Path('/fixture')))
        self.assertIn('TCG 카드·BOX 라이브러리', page)
        self.assertIn('PARTIAL_READ_ONLY', page)
        project.assert_not_called()
        with self.assertRaises(ValueError): images.unified_feed(data)

    def test_real_source_window_limit_remains_bounded_and_cannot_teach_a_match(self):
        source_rows = [{'registry_game_id': 'pokemon', 'region': 'JP', 'kind': 'CARD',
                        'name': 'Card ' + str(i), 'source': 'https://official.example/card/' + str(i)}
                       for i in range(bridge.MAX_SOURCES + 1)]
        def payload(path, max_bytes):
            return {'items': source_rows} if path.name == 'releases.json' else {'entries': {}} if path.name == 'market_prices.json' else {'items': []}
        with patch.object(bridge, 'read_json', side_effect=payload):
            sources, errors, _, truncated = bridge.source_rows(Path('/fixture'), {'pokemon': {}}, {})
        self.assertEqual(1500, len(sources))
        self.assertTrue(truncated)
        self.assertEqual([], errors)
        data = self.partial(); data['source_catalog'] = sources
        rows = images.unified_feed(data, allow_partial_display=True)
        self.assertEqual(1501, len(rows))
        self.assertTrue(all(r['display_only'] for r in rows))
        with self.assertRaises(ValueError): images.unified_feed(data)

    def test_corrupt_index_feed_or_entity_state_is_a_safe_stage_error_not_a_blank_success(self):
        with patch.object(live, 'build_report', return_value={'ok': False}):
            with self.assertRaises(live.ViewUnavailable) as error: live.read_view(Path('/fixture'))
            self.assertEqual('CATALOG_READ_FAILED', error.exception.code)
        data = report(); data['local_catalog'][0]['id'] = 'unsafe'
        with patch.object(live, 'build_report', return_value=data):
            with self.assertRaises(live.ViewUnavailable) as error: live.read_view(Path('/fixture'))
            self.assertEqual('FEED_INVALID', error.exception.code)
        with patch.object(live, 'build_report', return_value=report()), patch.object(live.library, 'storage_root', return_value=Path('/fixture')), patch.object(live, 'project', side_effect=ValueError('private existing state')):
            with self.assertRaises(live.ViewUnavailable) as error: live.read_view(Path('/fixture'))
            self.assertEqual('ENTITY_STATE_INVALID', error.exception.code)


class DiagnosticTests(unittest.TestCase):
    def healthy(self, route):
        if route == '/api/health':
            return 200, 'application/json', json.dumps({'ok': True, 'collection_health': {'runtime_build_sha': SHA, 'runtime_build_sha_verified': True, 'healthy': True, 'requires_attention': False}}).encode()
        page = {'/tablet-unified': 'TCG 카드·BOX 라이브러리', '/tablet-events-all': '전체 TCG · 행사·콜라보·영화·프로모', '/tablet-features': '/index.html?target=one'}[route]
        return 200, 'text/html', page.encode()

    def test_http_error_timeout_and_marker_failure_are_distinguishable_without_body(self):
        cases = [('HTTP_ERROR', HTTPError('http://127.0.0.1', 503, 'PRIVATE_NAME', {}, None)),
                 ('TIMEOUT', TimeoutError('PRIVATE_NAME')), ('TIMEOUT', URLError(TimeoutError('PRIVATE_NAME')))]
        for reason, error in cases:
            def reader(route):
                if route == '/tablet-unified': raise error
                return self.healthy(route)
            result = device.probe(SHA, reader=reader, git_sha=SHA)
            self.assertFalse(result['ok'])
            self.assertEqual(reason, result['route_details']['unified']['reason'])
            self.assertNotIn('PRIVATE_NAME', json.dumps(result))
        result = device.probe(SHA, git_sha=SHA, reader=lambda route: (200, 'text/html', b'old page'))
        self.assertEqual('RESPONSE_MISMATCH', result['route_details']['unified']['reason'])

    def test_partial_page_is_reported_as_partial_not_complete_data_or_device_proof(self):
        def reader(route):
            status, mime, raw = self.healthy(route)
            if route == '/tablet-unified': raw += b'<html data-tcg-view-state="PARTIAL_READ_ONLY">'
            return status, mime, raw
        result = device.probe(SHA, git_sha=SHA, reader=reader)
        self.assertTrue(result['ok'])
        self.assertEqual('PARTIAL_READ_ONLY', result['route_details']['unified']['data_state'])
        self.assertEqual('NOT_VERIFIED', result['image_metadata_repair_cycle'])
        self.assertEqual('NOT_RUN', result['touch_camera_verification'])

    def test_truncated_connection_is_a_hold_without_exception_body(self):
        def reader(route): raise IncompleteRead(b'PRIVATE_NAME', 300)
        result = device.probe(SHA, git_sha=SHA, reader=reader)
        self.assertFalse(result['ok'])
        self.assertNotIn('PRIVATE_NAME', json.dumps(result))

    def test_error_body_only_exports_allowlisted_stage_never_raw_details(self):
        for code in ('CATALOG_READ_FAILED', 'PRIVATE_NAME', {'secret': 'PRIVATE_NAME'}):
            payload = json.dumps({'error_code': code, 'error': 'PRIVATE_NAME'}).encode()
            error = HTTPError('http://127.0.0.1:8765/tablet-unified', 503, 'PRIVATE_NAME', {}, io.BytesIO(payload))
            opener = SimpleNamespace(open=lambda *a, **k: (_ for _ in ()).throw(error))
            with patch.object(device, 'build_opener', return_value=opener):
                with self.assertRaises(HTTPError) as raised: device.read('/tablet-unified')
            self.assertEqual('CATALOG_READ_FAILED' if code == 'CATALOG_READ_FAILED' else None,
                             getattr(raised.exception, 'tcg_error_code', None))
            def reader(route):
                if route == '/tablet-unified': raise raised.exception
                return self.healthy(route)
            result = device.probe(SHA, git_sha=SHA, reader=reader)
            self.assertNotIn('PRIVATE_NAME', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
