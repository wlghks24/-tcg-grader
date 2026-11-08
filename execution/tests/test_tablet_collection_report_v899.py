"""Mock HTTP + temporary event store. No real runtime, private device or network."""
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from execution import tablet_collection_report_v899 as report
from execution import tablet_event_coverage_v896 as events
from tcg_game_registry import load_registry

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)
PRIVATE = 'PRIVATE_CARD_NAME_SECRET_ID_URL_TOKEN'


def snapshots():
    auto = {'ok': True, 'local_folder': PRIVATE, 'last_result': {
        'run_at': NOW.isoformat(), 'scanned': 22, 'saved': 13, 'errors': 5,
        'metadata_enriched': 0, 'metadata_repair_attempted': 4, 'metadata_repair_pending': 10,
        'deferred': True, 'stopped': False, 'issues': ['HTTP 429 ' + PRIVATE, 'storage budget ' + PRIVATE],
        'per_source': {'pokemon/JP': {'source': 'TCGdex', 'saved': 2, 'errors': 1},
                       PRIVATE: {'source': PRIVATE, 'saved': 9},
                       'pokemon/US': {'source': PRIVATE, 'errors': 9}},
        'unified_metadata_repair': {'attempted': 4, 'enriched': 0, 'pending': 10, 'deferred': True, 'issues': ['metadata ' + PRIVATE]},
        'target_image_repair': {'attempted': 3, 'saved': 1, 'stored_bytes': 300, 'compression_bytes_saved': 100, 'issues': [], 'deferred': False},
        'canonical_store': {'ok': True, 'records': 1161, 'current': 1161, 'pending_work': 2322}},
        'job': {'running': False, 'scanned': 22, 'saved': 13, 'errors': 5, 'message': PRIVATE,
                'error_class': PRIVATE, 'started_at': NOW.isoformat(), 'finished_at': NOW.isoformat()}}
    inventory = {'ok': True, 'count': 2, 'folder': PRIVATE, 'items': [
        {'name': PRIVATE, 'id': PRIVATE, 'card_metadata': {'card_code': PRIVATE, 'language': 'ja', 'set_name': PRIVATE}},
        {'source_url': PRIVATE, 'card_metadata': {'card_number': '001', 'printing': 'Normal'}}]}
    projection = {'ok': True, 'unified_catalog': [
        {'entity_id': PRIVATE, 'name': PRIVATE, 'link_status': 'NEEDS_IMAGE', 'work_items': [{'action': 'COLLECT_EXACT_IMAGE', 'url': PRIVATE}]},
        {'entity_id': PRIVATE, 'link_status': PRIVATE, 'work_items': [{'action': PRIVATE}]}]}
    return dict(zip(report.ROUTES.values(), [auto, inventory, projection]))


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'tcg_game_registry.json').write_bytes((ROOT / 'tcg_game_registry.json').read_bytes())
        self.data = snapshots()

    def run_report(self, reader=None):
        return report.collection_report(self.root, reader=reader or self.data.__getitem__, now=NOW)

    def test_job_snapshot_counts_are_preserved_without_cycle_or_training_claims(self):
        result = self.run_report(); auto = result['routes']['auto']['summary']
        self.assertTrue(all(result['snapshot_readable'].values()))
        self.assertEqual(22, auto['last_result']['scanned'])
        self.assertEqual(13, auto['last_result']['saved'])
        self.assertEqual(5, auto['last_result']['errors'])
        self.assertTrue(auto['last_result']['deferred'])
        self.assertEqual(1161, auto['canonical_store']['records'])
        self.assertEqual(2322, auto['canonical_store']['pending_work'])
        self.assertFalse(result['collector_verified'])
        self.assertFalse(result['current_build_cycle_verified'])
        self.assertFalse(result['run_generation_recorded'])
        self.assertEqual('NOT_RUN', result['touch_camera_verification'])
        self.assertEqual('NOT_RUN', result['model_training_verification'])

    def test_issue_hints_do_not_equal_error_count_and_raw_text_is_redacted(self):
        result = self.run_report(); hints = result['routes']['auto']['summary']['issue_hints']
        self.assertEqual(2, hints['message_count'])
        self.assertFalse(hints['counts_are_error_count'])
        self.assertEqual(1, hints['hint_counts']['HTTP_429'])
        self.assertEqual(1, hints['hint_counts']['STORAGE'])
        self.assertEqual(1, hints['hint_counts']['BUDGET'])
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assertNotIn('source_url', json.dumps(result))

    def test_existing_update_zero_is_separate_from_new_photo_metadata_presence(self):
        result = self.run_report()
        self.assertEqual(0, result['routes']['auto']['summary']['last_result']['metadata_enriched'])
        inventory = result['routes']['inventory']['summary']
        self.assertEqual(2, inventory['rows_with_known_metadata_fields'])
        self.assertEqual(1, inventory['metadata_field_presence']['card_code'])
        self.assertEqual(1, inventory['metadata_field_presence']['card_number'])
        self.assertIn('existing photos', result['routes']['auto']['summary']['metadata_counter_semantics'])

    def test_per_source_only_public_registry_pairs_and_eight_known_providers(self):
        auto = self.run_report()['routes']['auto']['summary']
        self.assertEqual(1, len(auto['per_source']))
        self.assertEqual('pokemon', auto['per_source'][0]['game_id'])
        self.assertEqual('JP', auto['per_source'][0]['region'])
        self.assertEqual('TCGdex', auto['per_source'][0]['provider'])
        self.assertEqual(2, auto['other_source_count'])

    def test_projection_counts_only_allowlisted_actions_and_statuses(self):
        projection = self.run_report()['routes']['projection']['summary']
        self.assertEqual(2, projection['projection_rows'])
        self.assertEqual({'COLLECT_EXACT_IMAGE': 1, 'OTHER': 1}, projection['work_action_counts'])
        self.assertEqual({'NEEDS_IMAGE': 1, 'OTHER': 1}, projection['link_status_counts'])
        self.assertFalse(projection['projection_is_completed_collection_proof'])

    def test_missing_event_file_is_not_run_not_zero_events(self):
        result = self.run_report()['events']
        self.assertEqual('NOT_RUN_OR_NOT_RECORDED', result['status'])
        self.assertNotIn('candidate_count', result)

    def test_event_snapshot_retains_thirty_games_fifty_five_cells_discovery_only(self):
        configured = events.cells(load_registry(self.root))
        data = {'version': 896, 'cursor': configured[2]['key'], 'items': [], 'cells': {}}
        for cell, successes in zip(configured[:3], [2, 1, 0]):
            data['cells'][cell['key']] = {'attempted_at': NOW.isoformat(), 'requests': 2, 'successes': successes,
                                         'results': 0, 'errors': []}
        data['cells'][configured[3]['key']] = {'attempted_at': (NOW - timedelta(days=8)).isoformat(),
                                             'requests': 2, 'successes': 2, 'results': 0, 'errors': []}
        path = self.root / events.STATE; path.write_text(json.dumps(data)); before = path.read_bytes()
        result = self.run_report()['events']
        self.assertEqual(30, result['configured_games'])
        self.assertEqual(55, result['configured_cells'])
        self.assertEqual(4, result['attempted_cells'])
        self.assertEqual(1, result['fresh_success_cells'])
        self.assertEqual(1, result['partial_cells'])
        self.assertEqual(1, result['failed_cells'])
        self.assertEqual(1, result['stale_cells'])
        self.assertEqual(51, result['not_searched_cells'])
        self.assertEqual('NOT_VERIFIED', result['confirmed_events_or_rewards'])
        self.assertTrue(result['discovery_only'])
        self.assertEqual(before, path.read_bytes())

    def test_invalid_event_store_is_hold_not_success_and_symlink_is_not_followed(self):
        path = self.root / events.STATE; path.write_bytes(b'{"version":896,"items":false}')
        self.assertEqual('HOLD_EVENT_STORE_SCHEMA', self.run_report()['events']['status'])
        path.unlink(); path.symlink_to(self.root / 'missing-secret.json')
        self.assertEqual('HOLD_EVENT_STORE_SCHEMA', self.run_report()['events']['status'])

    def test_http_failures_have_fixed_categories_and_no_exception_body(self):
        for code, expected in [(403, 'HTTP_403'), (429, 'HTTP_429'), (404, 'HTTP_404'), (503, 'HTTP_5XX'), (418, 'OTHER')]:
            def reader(path):
                if path == report.ROUTES['auto']: raise HTTPError('http://127.0.0.1', code, PRIVATE, {}, io.BytesIO(PRIVATE.encode()))
                return self.data[path]
            result = self.run_report(reader)
            self.assertEqual(expected, result['routes']['auto']['reason'])
            self.assertFalse(result['snapshot_readable']['auto'])
            self.assertNotIn(PRIVATE, json.dumps(result))

    def test_timeout_direct_and_wrapped_are_fixed_timeout(self):
        for error in (TimeoutError(PRIVATE), URLError(TimeoutError(PRIVATE))):
            def reader(path): raise error
            result = self.run_report(reader)
            self.assertTrue(all(route['reason'] == 'TIMEOUT' for route in result['routes'].values()))
            self.assertNotIn(PRIVATE, json.dumps(result))

    def test_malformed_counts_boolean_and_unknown_shapes_fail_closed(self):
        for data in ({'ok': True, 'last_result': False}, {'ok': True, 'last_result': {'scanned': True}},
                     {'ok': False}, [], {'ok': True, 'job': {'running': 1}}):
            result = self.run_report(lambda path: data if path == report.ROUTES['auto'] else self.data[path])
            self.assertFalse(result['snapshot_readable']['auto'])
            self.assertEqual('SCHEMA', result['routes']['auto']['reason'])

    def test_unrecorded_job_is_not_a_success_receipt(self):
        self.data[report.ROUTES['auto']] = {'ok': True, 'last_result': None, 'job': {'running': False}}
        auto = self.run_report()['routes']['auto']['summary']
        self.assertEqual('NOT_RUN_OR_NOT_RECORDED', auto['last_result_status'])
        self.assertFalse(auto['current_build_cycle_verified'])


class HttpReaderTests(unittest.TestCase):
    def response(self, payload=b'{"ok":true}', mime='application/json', status=200):
        class Response:
            def __init__(self): self.raw = io.BytesIO(payload); self.headers = SimpleNamespace(get_content_type=lambda: mime); self.status = status
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read1(self, size): return self.raw.read(size)
        return Response()

    def test_fixed_get_host_proxy_bypass_and_no_redirect_handler(self):
        opened = []
        def open_request(request, **kwargs):
            opened.append(request); return self.response()
        with patch.object(report, 'build_opener', return_value=SimpleNamespace(open=open_request)) as build:
            result = report.read_snapshot(report.ROUTES['auto'])
        self.assertTrue(result['ok'])
        self.assertEqual('http://127.0.0.1:8765/api/local-card-images/auto-status', opened[0].full_url)
        self.assertEqual('GET', opened[0].get_method())
        self.assertEqual({}, build.call_args.args[0].proxies)
        with self.assertRaises(report.SnapshotError): report.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://private.invalid')

    def test_unallowlisted_route_is_rejected_before_network(self):
        with patch.object(report, 'build_opener') as build:
            for path in ('/api/run-auto-update', 'https://evil.invalid', report.ROUTES['auto'] + '?query=x'):
                with self.assertRaises(report.SnapshotError): report.read_snapshot(path)
            build.assert_not_called()

    def test_duplicate_keys_nan_wrong_mime_and_size_are_rejected(self):
        cases = [(b'{"ok":true,"ok":false}', 'application/json'), (b'{"n":NaN}', 'application/json'),
                 (b'[]', 'application/json'), (b'{}', 'text/html')]
        for raw, mime in cases:
            with patch.object(report, 'build_opener', return_value=SimpleNamespace(open=lambda *a, **k: self.response(raw, mime))):
                with self.assertRaises((report.SnapshotError, ValueError)): report.read_snapshot(report.ROUTES['auto'])
        with patch.object(report, 'MAX_RESPONSE_BYTES', 10), patch.object(report, 'build_opener', return_value=SimpleNamespace(open=lambda *a, **k: self.response(b'x' * 11))):
            with self.assertRaises(report.SnapshotError): report.read_snapshot(report.ROUTES['auto'])

    def test_late_read_even_at_eof_never_returns_success(self):
        clock = iter([0, 0, 7])
        with patch.object(report.time, 'monotonic', side_effect=lambda: next(clock)), patch.object(report, 'build_opener', return_value=SimpleNamespace(open=lambda *a, **k: self.response())):
            with self.assertRaises(report.SnapshotError) as error: report.read_snapshot(report.ROUTES['auto'])
        self.assertEqual('TIMEOUT', error.exception.reason)

    def test_http_error_body_is_closed_without_being_read(self):
        class Body(io.BytesIO):
            def read(self, *args): raise AssertionError('private body read')
        body = Body(PRIVATE.encode())
        error = HTTPError('http://127.0.0.1', 429, PRIVATE, {}, body)
        opener = SimpleNamespace(open=lambda *a, **k: (_ for _ in ()).throw(error))
        with patch.object(report, 'build_opener', return_value=opener):
            with self.assertRaises(report.SnapshotError) as raised:
                report.read_snapshot(report.ROUTES['auto'])
        self.assertEqual('HTTP_429', raised.exception.reason)
        self.assertTrue(body.closed)

    def test_cli_never_exposes_exception_details(self):
        import contextlib
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(report, 'collection_report', side_effect=ValueError(PRIVATE)):
            code = report.main(['--repo', '/unused'])
        self.assertEqual(1, code)
        self.assertNotIn(PRIVATE, output.getvalue())
        self.assertEqual('HOLD_REPORT_UNAVAILABLE', json.loads(output.getvalue())['status'])


if __name__ == '__main__':
    unittest.main()
