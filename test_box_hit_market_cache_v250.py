import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import box_hit_market_discovery as m


class BoxHitMarketCacheV250Tests(unittest.TestCase):
    def _payload(self, when, name='Cached Candidate'):
        return {
            'version': 2,
            'updated_at': when.isoformat(timespec='seconds'),
            'candidates': [{
                'country': 'US', 'game': 'Pokémon', 'asset': 'BOX', 'name': name,
                'source_count': 2, 'promoted': True, 'image_url': '', 'score': 1.8,
                'source_names': ['A', 'B'], 'source_urls': ['https://example.com/item'],
            }],
            'summary': {'total': 1, 'promoted': 1, 'with_image': 0, 'source_count': 2},
            'source_stats': {'a': {'results': 1}},
            'errors': [],
            'notice': 'test',
        }

    def _write(self, path, payload):
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

    def test_fresh_cache_skips_all_discovery_network_work(self):
        now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'box_hit_market_candidates.json'
            self._write(out,self._payload(now-dt.timedelta(minutes=10)))
            db={'entries':{}}
            with mock.patch.object(m,'OUT',out), \
                 mock.patch.object(m,'discover_market_catalog',side_effect=AssertionError('fresh cache must skip discovery')), \
                 mock.patch.object(m,'_rss',side_effect=AssertionError('fresh cache must skip Bing RSS')), \
                 mock.patch.object(m,'_page_image',side_effect=AssertionError('fresh cache must skip image fetch')):
                result=m.merge_market_catalog(db)
        self.assertTrue(result['cache_reused'])
        self.assertTrue(db['box_hit_market_discovery']['cache_reused'])
        self.assertIn('US|Cached Candidate|BOX',db['entries'])

    def test_cache_reuse_does_not_refresh_original_timestamp(self):
        now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        stamped=now-dt.timedelta(minutes=15)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'box_hit_market_candidates.json'
            self._write(out,self._payload(stamped))
            before=json.loads(out.read_text(encoding='utf-8'))['updated_at']
            with mock.patch.object(m,'OUT',out):
                cached=m._load_fresh_discovery_cache(now=now)
            after=json.loads(out.read_text(encoding='utf-8'))['updated_at']
        self.assertIsNotNone(cached)
        self.assertEqual(before,after)
        self.assertEqual(cached['updated_at'],before)

    def test_stale_cache_forces_fresh_discovery(self):
        now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        fresh=self._payload(now,'Fresh Candidate')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'box_hit_market_candidates.json'
            self._write(out,self._payload(now-dt.timedelta(seconds=m.MARKET_DISCOVERY_CACHE_TTL_SECONDS+1)))
            db={'entries':{}}
            with mock.patch.object(m,'OUT',out), mock.patch.object(m,'discover_market_catalog',return_value=fresh) as discover:
                result=m.merge_market_catalog(db)
        discover.assert_called_once_with()
        self.assertFalse(result.get('cache_reused',False))
        self.assertIn('US|Fresh Candidate|BOX',db['entries'])

    def test_corrupt_or_future_cache_never_suppresses_refresh(self):
        now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'box_hit_market_candidates.json'
            out.write_text('{broken',encoding='utf-8')
            with mock.patch.object(m,'OUT',out):
                self.assertIsNone(m._load_fresh_discovery_cache(now=now))
            self._write(out,self._payload(now+dt.timedelta(seconds=m.MARKET_DISCOVERY_CACHE_FUTURE_SKEW_SECONDS+1)))
            with mock.patch.object(m,'OUT',out):
                self.assertIsNone(m._load_fresh_discovery_cache(now=now))

    def test_symlink_cache_is_rejected(self):
        now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); real=root/'real.json'; link=root/'cache.json'
            self._write(real,self._payload(now))
            try:
                link.symlink_to(real)
            except (OSError,NotImplementedError):
                self.skipTest('symlink unavailable')
            with mock.patch.object(m,'OUT',link):
                self.assertIsNone(m._load_fresh_discovery_cache(now=now))

    def test_force_refresh_bypasses_fresh_cache(self):
        now=dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        fresh=self._payload(now,'Forced Fresh')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'box_hit_market_candidates.json'
            self._write(out,self._payload(now,'Cached Candidate'))
            db={'entries':{}}
            with mock.patch.object(m,'OUT',out), mock.patch.object(m,'discover_market_catalog',return_value=fresh) as discover:
                result=m.merge_market_catalog(db,force_refresh=True)
        discover.assert_called_once_with()
        self.assertIn('US|Forced Fresh|BOX',db['entries'])
        self.assertNotIn('US|Cached Candidate|BOX',db['entries'])
        self.assertFalse(result.get('cache_reused',False))


if __name__=='__main__':
    unittest.main()
