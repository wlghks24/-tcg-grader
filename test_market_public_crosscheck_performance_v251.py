import os
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import market_public_crosscheck as crosscheck


class MarketPublicCrosscheckPerformanceV251Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_state,self.old_watch=crosscheck.STATE,crosscheck.WATCH
        crosscheck.STATE=Path(self.tmp.name)/'state.json'
        crosscheck.WATCH=Path(self.tmp.name)/'watch.json'
        crosscheck.WATCH.write_text('{"items":[]}',encoding='utf-8')

    def tearDown(self):
        crosscheck.STATE,crosscheck.WATCH=self.old_state,self.old_watch
        self.tmp.cleanup()

    @staticmethod
    def _db(count=4):
        entries={}
        for i in range(count):
            entries[f'KR|카드{i}|HIT']={
                'game':'POKEMON','card_name':f'테스트카드{i}',
                'card_number':f'{i+1:03d}/100',
            }
        return {'entries':entries}

    @staticmethod
    def _response_for(url):
        parsed=urllib.parse.urlparse(url)
        query=urllib.parse.parse_qs(parsed.query)
        term=(query.get('search') or query.get('keyword') or [''])[0]
        if 'collectory' in parsed.netloc:
            return f'{term} 현재 시세 ₩100,000 최저 ₩90,000'
        return f'{term} 110,000원 관심 10 · 거래 3'

    def test_cross_host_parallelism_never_overlaps_same_source(self):
        db=self._db(4)
        barrier=threading.Barrier(2)
        lock=threading.Lock()
        active={};max_active={};global_active=0;max_global=0;first=set()

        def fetcher(url):
            nonlocal global_active,max_global
            host=urllib.parse.urlparse(url).netloc
            with lock:
                active[host]=active.get(host,0)+1
                max_active[host]=max(max_active.get(host,0),active[host])
                global_active+=1;max_global=max(max_global,global_active)
                is_first=host not in first
                first.add(host)
            try:
                if is_first:
                    barrier.wait(timeout=2)
                return self._response_for(url)
            finally:
                with lock:
                    active[host]-=1;global_active-=1

        env={
            'TCG_MARKET_CROSSCHECK_QUERIES':'4',
            'TCG_MARKET_CROSSCHECK_SOURCE_WORKERS':'2',
            'TCG_MARKET_CROSSCHECK_CACHE_SECONDS':'60',
        }
        with mock.patch.dict(os.environ,env,clear=False):
            summary=crosscheck.crosscheck_market_db(db,fetcher=fetcher)

        self.assertEqual(summary['requests_checked'],8)
        self.assertEqual(summary['matches'],8)
        self.assertEqual(summary['source_workers'],2)
        self.assertEqual(summary['worker_policy'],'max-one-inflight-request-per-source')
        self.assertGreaterEqual(max_global,2)
        self.assertTrue(max_active)
        self.assertTrue(all(value==1 for value in max_active.values()))
        for entry in db['entries'].values():
            self.assertEqual({x['source'] for x in entry['source_crosschecks']},{'Collectory','KREAM'})

    def test_short_cache_absorbs_duplicate_trigger_storm(self):
        db=self._db(2)
        calls=[]

        def fetcher(url):
            calls.append(url)
            return self._response_for(url)

        env={
            'TCG_MARKET_CROSSCHECK_QUERIES':'2',
            'TCG_MARKET_CROSSCHECK_SOURCE_WORKERS':'2',
            'TCG_MARKET_CROSSCHECK_CACHE_SECONDS':'900',
        }
        with mock.patch.dict(os.environ,env,clear=False):
            first=crosscheck.crosscheck_market_db(db,fetcher=fetcher)
            first_calls=len(calls)
            second=crosscheck.crosscheck_market_db(db,fetcher=fetcher)

        self.assertEqual(first['requests_checked'],4)
        self.assertEqual(first_calls,4)
        self.assertEqual(len(calls),4)
        self.assertEqual(second['requests_checked'],0)
        self.assertEqual(second['cache_hits'],4)
        self.assertEqual(second['external_requests_saved'],4)
        self.assertEqual(second['source_workers'],0)

    def test_network_failure_preserves_previous_observation(self):
        db=self._db(1)
        entry=next(iter(db['entries'].values()))
        entry['source_crosschecks']=[{
            'source':'Collectory','price_krw':99000,'confidence':.97,
            'observed_at':'2020-01-01T00:00:00+00:00',
        }]

        def fetcher(url):
            if 'collectory' in urllib.parse.urlparse(url).netloc:
                raise TimeoutError('simulated timeout')
            return self._response_for(url)

        env={
            'TCG_MARKET_CROSSCHECK_QUERIES':'1',
            'TCG_MARKET_CROSSCHECK_SOURCE_WORKERS':'2',
            'TCG_MARKET_CROSSCHECK_CACHE_SECONDS':'60',
        }
        with mock.patch.dict(os.environ,env,clear=False):
            summary=crosscheck.crosscheck_market_db(db,fetcher=fetcher)

        checks={x['source']:x for x in entry['source_crosschecks']}
        self.assertEqual(checks['Collectory']['price_krw'],99000)
        self.assertEqual(checks['KREAM']['price_krw'],110000)
        self.assertEqual(summary['sources']['Collectory']['errors'],1)
        self.assertTrue(summary['errors'])


if __name__=='__main__':
    unittest.main()