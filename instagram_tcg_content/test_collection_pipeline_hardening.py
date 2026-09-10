#!/usr/bin/env python3
from __future__ import annotations
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from instagram_tcg_content.collector_runtime import (
    AutoTracker, ResilientHTTPClient, RetryPolicy, SourceSpec,
    classify_error, validate_source_url,
)
from instagram_tcg_content.official_collection_bridge import verify_tracker_summary
from instagram_tcg_content.official_source_adapters import onepiece_kr_topics_validator
from instagram_tcg_content.collector_runtime import FetchResult
from instagram_tcg_content.source_registry import validate_registry

ROOT = Path(__file__).resolve().parent


class CollectionPipelineHardeningTests(unittest.TestCase):
    def test_registry_resolves_every_route_provider(self):
        registry=json.loads((ROOT/'source_registry.json').read_text(encoding='utf-8'))
        routes=json.loads((ROOT/'source_routes.json').read_text(encoding='utf-8'))
        report=validate_registry(registry,routes)
        self.assertEqual(report['status'],'PASS',report)
        self.assertEqual(report['referenced_provider_count'],30)
        self.assertEqual(report['registry_provider_count'],30)

    def test_private_source_url_fails_before_network(self):
        for url in ('http://127.0.0.1/x','http://localhost/x','http://10.0.0.1/x'):
            with self.assertRaisesRegex(Exception,'PRIVATE_SOURCE_URL_FORBIDDEN'):
                validate_source_url(url)

    def test_429_does_not_fall_through_to_same_provider_fallback(self):
        calls=[]
        def fake_open(req,timeout=0):
            calls.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url,429,'rate',{'Retry-After':'3600'},None)
        with tempfile.TemporaryDirectory() as td, patch('urllib.request.urlopen',side_effect=fake_open):
            tracker=AutoTracker(Path(td)/'state.sqlite3',ResilientHTTPClient(RetryPolicy(max_attempts=2,max_delay_s=20,total_wait_cap_s=20)))
            spec=SourceSpec('TEST',['https://example.com/primary'],fallback_urls=['https://example.org/fallback'],provider_id='test-provider')
            with self.assertRaises(Exception) as caught:
                tracker.track_source(spec)
            self.assertIn(classify_error(caught.exception),{'SOURCE_DEFERRED','RATE_LIMITED_429'})
            self.assertEqual(len(calls),1,calls)

    def test_official_product_news_reaches_verification_bridge(self):
        stamp=datetime.now(timezone.utc).isoformat(timespec='seconds')
        body='원피스 카드게임 공지사항 PRODUCTS 신제품 카드 상품 안내 2026-09-04'.encode('utf-8')
        result=FetchResult('https://onepiece-cardgame.kr/topics.do',200,{'Content-Type':'text/html'},body,1,0.01)
        bundle=dict(onepiece_kr_topics_validator(result))
        bundle['provider_id']='onepiece-cardgame-regional'
        bundle['checked_at']=stamp
        for row in bundle['records']:
            row['checked_at']=stamp
        summary={'sources':{'ONEPIECE_KR_TOPICS':{'status':'healthy','records':[bundle]}}}
        verified=verify_tracker_summary(summary)
        self.assertGreaterEqual(verified['verified_fact_count'],1,verified)
        row=verified['verified_records'][0]
        self.assertEqual(row['content_type'],'product_news')
        self.assertEqual(row['information_family'],'official_release')
        self.assertEqual(row['verification_status'],'verified')


if __name__=='__main__':
    unittest.main()
