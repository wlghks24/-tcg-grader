"""Offline real-registry discovery, cursor persistence and evidence isolation."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from xml.sax.saxutils import escape

from execution import tablet_event_coverage_v896 as events
from tcg_game_registry import load_registry

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)


def rss(title, source='https://magic.wizards.com/news/test?utm_source=mirror', description=''):
    return ('<rss><channel><item><title>' + escape(title) + '</title><link>' + escape(source) + '</link><description>' + escape(description) + '</description></item></channel></rss>').encode()


class EventCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'tcg_game_registry.json').write_bytes((ROOT / 'tcg_game_registry.json').read_bytes())
        self.configured = events.cells(load_registry(self.root))
        self.magic = next(c for c in self.configured if c['game_id'] == 'mtg' and c['region'] == 'US')

    def empty(self, cell, scoped, now):
        return []

    def test_real_registry_all_thirty_games_including_watch(self):
        registry = load_registry(self.root)
        self.assertEqual({g['id'] for g in registry['games']}, {c['game_id'] for c in self.configured})
        self.assertEqual(30, len({c['game_id'] for c in self.configured}))
        self.assertEqual(55, len(self.configured))
        self.assertTrue(any(c['state'] == 'watch' for c in self.configured))
        self.assertEqual(registry, load_registry(self.root))

    def test_twelve_requests_and_durable_cursor_cover_every_declared_pair(self):
        seen = []
        def record(cell, scoped, now):
            seen.append((cell['key'], scoped))
            return []
        for cycle in range(10):
            summary = events.collect(self.root, fetcher=record, now=NOW + timedelta(minutes=31 * cycle), clock=lambda: 0)
            self.assertLessEqual(summary['requests_this_run'], 12)
            self.assertNotIn('items', summary)
        self.assertEqual({c['key'] for c in self.configured}, {key for key, _ in seen})
        self.assertEqual(110, len(seen))
        self.assertEqual(55, len({key for key, scoped in seen if scoped}))
        self.assertTrue(all(c['status'] == 'SEARCHED_UNCONFIRMED' for c in summary['cells']))
        self.assertEqual(0, events.collect(self.root, fetcher=record, now=NOW, clock=lambda: 0)['requests_this_run'])

    def test_new_registry_game_is_discovered_without_a_hardcoded_allowlist(self):
        registry = load_registry(self.root)
        game = dict(registry['games'][-1])
        game.update(id='new-tcg', canonical='New TCG', label_ko='새 TCG', promo_value='새 TCG')
        registry['games'].append(game)
        self.assertIn('new-tcg', {c['game_id'] for c in events.cells(registry)})

    def test_queries_include_rerelease_and_collab_for_each_language(self):
        for region, token in [('KR', '재개봉'), ('JP', '再上映'), ('US', 're-release')]:
            cell = next(c for c in self.configured if c['region'] == region)
            from urllib.parse import parse_qs, urlsplit
            query = parse_qs(urlsplit(events.query_url(cell, True)).query)['q'][0]
            self.assertIn(token, query)
            self.assertIn('site:', query)
            self.assertLessEqual(len(events.query_url(cell, False)), 2048)

    def test_movie_without_card_reward_is_retained_as_unconfirmed_lead(self):
        cell = next(c for c in self.configured if c['game_id'] == 'onepiece')
        rows = events.parse_rss(rss('ONE PIECE FILM GOLD 재개봉 영화 예고편', 'https://example.org/movie'), cell, NOW)
        self.assertEqual(1, len(rows))
        self.assertIn('movie', rows[0]['topics'])
        self.assertFalse(rows[0]['card_reward_confirmed'])
        self.assertFalse(rows[0]['verified'])
        self.assertEqual('UNKNOWN', rows[0]['region'])
        self.assertEqual('UNCONFIRMED', rows[0]['date_status'])
        self.assertNotIn('dates', rows[0])

    def test_other_tcg_collab_and_promo_not_onepiece_only(self):
        rows = events.parse_rss(rss('Magic: The Gathering Secret Lair collaboration promo'), self.magic, NOW)
        self.assertEqual({'collab', 'promo'}, set(rows[0]['topics']))
        self.assertTrue(rows[0]['official_domain_match'])
        self.assertFalse(rows[0]['verified'])

    def test_unrelated_generic_and_private_urls_are_rejected(self):
        for title, source in [('ONE PIECE promo', 'https://magic.wizards.com/x'), ('Magic: The Gathering deck guide', 'https://magic.wizards.com/x'), ('Magic: The Gathering promo', 'https://127.0.0.1/x'), ('Magic: The Gathering promo', 'javascript:alert(1)')]:
            self.assertEqual([], events.parse_rss(rss(title, source), self.magic, NOW))

    def test_xml_entities_and_oversized_or_wrong_schema_fail(self):
        for raw in [b'<!DOCTYPE rss [<!ENTITY x "payload">]><rss/>', b'x' * 400001, b'<html/>']:
            with self.assertRaises(ValueError):
                events.parse_rss(raw, self.magic, NOW)

    def test_same_source_across_regions_or_utm_merges_once_without_crosscheck(self):
        def source(cell, scoped, now):
            row = events.parse_rss(rss(cell['canonical'] + ' collaboration promo', 'https://example.org/' + cell['game_id'] + '?utm_source=' + cell['region']), cell, now)
            return row
        for cycle in range(10):
            events.collect(self.root, fetcher=source, now=NOW + timedelta(minutes=31 * cycle), clock=lambda: 0)
        data = events._load(self.root)
        self.assertEqual(30, len(data['items']))
        row = next(r for r in data['items'] if r['game_id'] == 'pokemon')
        self.assertEqual(['JP', 'KR', 'US'], row['search_regions'])
        self.assertNotIn('cross_checked', row)
        self.assertFalse(row['verified'])

    def test_403_and_429_stop_requests_and_persist_provider_cooldown(self):
        for code in (403, 429):
            path = self.root / events.STATE
            path.unlink(missing_ok=True)
            def blocked(*args):
                raise HTTPError('https://www.bing.com', code, 'blocked', {}, None)
            summary = events.collect(self.root, fetcher=blocked, now=NOW, clock=lambda: 0)
            self.assertEqual(1, summary['requests_this_run'])
            self.assertEqual(0, events.collect(self.root, fetcher=blocked, now=NOW + timedelta(hours=1), clock=lambda: 0)['requests_this_run'])

    def test_partial_failure_and_zero_results_are_distinct_from_no_events(self):
        def partial(cell, scoped, now):
            if scoped:
                raise OSError('offline')
            return []
        summary = events.collect(self.root, fetcher=partial, now=NOW, clock=lambda: 0)
        self.assertEqual(6, sum(c['status'] == 'PARTIAL_SEARCH' for c in summary['cells']))
        self.assertEqual(49, sum(c['status'] == 'NOT_SEARCHED' for c in summary['cells']))
        self.assertEqual(0, summary['candidate_count'])
        self.assertIn('증거가 아닙니다', summary['policy'])

    def test_deadline_defers_without_advancing_unattempted_cursor(self):
        summary = events.collect(self.root, fetcher=self.empty, now=NOW, clock=iter([0, 40]).__next__)
        self.assertEqual(0, summary['requests_this_run'])
        self.assertEqual('', events._load(self.root)['cursor'])

    def test_deadline_after_first_fetch_prevents_second_request(self):
        elapsed = [0]
        def slow(*args):
            elapsed[0] = 44
            return []
        summary = events.collect(self.root, fetcher=slow, now=NOW, clock=lambda: elapsed[0])
        self.assertEqual(1, summary['requests_this_run'])
        self.assertTrue(any('DEFERRED_DEADLINE' in e for e in summary['errors_this_run']))

    def test_malformed_nested_counts_fail_before_file_replacement(self):
        events.collect(self.root, fetcher=self.empty, now=NOW, clock=lambda: 0)
        path = self.root / events.STATE
        data = json.loads(path.read_text())
        for value in ('broken', True, -1, 3):
            data['cells'][self.configured[0]['key']]['successes'] = value
            path.write_text(json.dumps(data))
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                events.collect(self.root, fetcher=self.empty, now=NOW, clock=lambda: 0)
            self.assertEqual(before, path.read_bytes())

    def test_transport_checks_deadline_while_reading_body(self):
        elapsed = [0]
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read1(self, size):
                elapsed[0] = 46
                return b'<rss>'
        with patch.object(events, 'safe_urlopen', return_value=Response()):
            with self.assertRaises(TimeoutError):
                events.fetch(self.magic, True, NOW, deadline=45, clock=lambda: elapsed[0])

    def test_malformed_previous_state_is_preserved_and_symlinks_refused(self):
        path = self.root / events.STATE
        path.write_bytes(b'{"version":896,"items":false}')
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            events.collect(self.root, fetcher=self.empty, now=NOW)
        self.assertEqual(before, path.read_bytes())
        path.unlink()
        target = self.root / 'outside.json'
        target.write_bytes(before)
        path.symlink_to(target)
        with self.assertRaises((OSError, ValueError)):
            events.collect(self.root, fetcher=self.empty, now=NOW)
        self.assertEqual(before, target.read_bytes())

    def test_stale_and_future_searches_do_not_fill_fresh_coverage(self):
        events.collect(self.root, fetcher=self.empty, now=NOW, clock=lambda: 0)
        data = events._load(self.root)
        for moment in (NOW + timedelta(days=8), NOW - timedelta(days=1)):
            summary = events.report(self.configured, data, now=moment)
            self.assertEqual(6, sum(c['status'] == 'STALE_SEARCH' for c in summary['cells']))

    def test_wrapper_preserves_original_rows_errors_status_and_is_idempotent(self):
        original = lambda: ([{'legacy': True}], ['old-error'], {'legacy': 'status'})
        module = SimpleNamespace(collect_all=original)
        events.install(module, self.root)
        installed = module.collect_all
        events.install(module, self.root)
        self.assertIs(installed, module.collect_all)
        with patch.object(events, 'collect', return_value={'game_count': 30}):
            rows, errors, status = module.collect_all()
        self.assertEqual([{'legacy': True}], rows)
        self.assertEqual(['old-error'], errors)
        self.assertEqual('status', status['legacy'])
        self.assertEqual(30, status['registry_coverage_v896']['game_count'])

    def test_wrapper_read_error_keeps_original_and_reports_hold(self):
        module = SimpleNamespace(collect_all=lambda: ([], [], {'legacy': True}))
        events.install(module, self.root)
        with patch.object(events, 'collect', side_effect=ValueError('invalid')):
            _, errors, status = module.collect_all()
        self.assertEqual('HOLD_PREVIOUS_COVERAGE', status['registry_coverage_v896']['status'])
        self.assertTrue(errors)

    def test_view_contains_all_games_before_search_and_escapes_external_text(self):
        page = events.render(self.root)
        for cell in self.configured:
            self.assertIn(escape(cell['game']), page)
        row = events.parse_rss(rss('Magic: The Gathering promo <script>alert(1)</script>'), self.magic, NOW)[0]
        data = events._load(self.root); data['items'] = [row]
        from safe_runtime import atomic_write_json
        atomic_write_json(self.root / events.STATE, data)
        page = events.render(self.root)
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertIn('카드 특전 미확인', page)
        self.assertIn('NOT_SEARCHED', page)

    def test_aware_clock_required(self):
        with self.assertRaises(ValueError):
            events.collect(self.root, fetcher=self.empty, now=datetime(2026, 11, 3))

    def test_country_and_game_filter_rejects_unknown_values(self):
        page = events.render(self.root, game_id='mtg', region='US')
        self.assertIn('value="mtg" selected', page)
        self.assertNotIn('<td>원피스 카드</td>', page)
        for game, region in [('missing', 'US'), ('mtg', '<script>')]:
            with self.assertRaises(ValueError):
                events.render(self.root, game_id=game, region=region)

    def test_repeated_manual_calls_cannot_burst_through_registry(self):
        events.collect(self.root, fetcher=self.empty, now=NOW, clock=lambda: 0)
        summary = events.collect(self.root, fetcher=self.empty, now=NOW + timedelta(minutes=1), clock=lambda: 0)
        self.assertEqual(0, summary['requests_this_run'])
        self.assertEqual(['RUN_INTERVAL_DEFERRED'], summary['errors_this_run'])

    def test_existing_update_parent_runs_collection_and_original_without_new_worker(self):
        core = SimpleNamespace(update_cycle=lambda *a, **k: {'legacy': a[0]})
        events.install_update(core, self.root)
        first = core.update_cycle
        events.install_update(core, self.root)
        self.assertIs(first, core.update_cycle)
        with patch.object(events, 'collect', return_value={'game_count': 30}) as scan:
            result = core.update_cycle('manual')
        scan.assert_called_once_with(self.root)
        self.assertEqual('manual', result['legacy'])
        self.assertEqual(30, result['registry_event_coverage_v896']['game_count'])
        with patch.object(events, 'collect', side_effect=ValueError('bad')):
            result = core.update_cycle('automatic')
        self.assertEqual('automatic', result['legacy'])
        self.assertEqual('HOLD_PREVIOUS_COVERAGE', result['registry_event_coverage_v896']['status'])

    def test_eof_after_deadline_is_not_a_success(self):
        elapsed = [0]
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read1(self, size):
                if elapsed[0] == 0:
                    elapsed[0] = 44
                    return b'<rss><channel/></rss>'
                elapsed[0] = 46
                return b''
        with patch.object(events, 'safe_urlopen', return_value=Response()):
            with self.assertRaises(TimeoutError):
                events.fetch(self.magic, True, NOW, deadline=45, clock=lambda: elapsed[0])


if __name__ == '__main__':
    unittest.main()
