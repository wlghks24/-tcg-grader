#!/usr/bin/env python3
"""V571 regression: strict official CN catalog -> existing automatic watch -> UI."""
from __future__ import annotations
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import china_official_catalog_v571 as china
import update_market_watch as watch
import auto_update_all

CN = '''<a href="/tcg/product/23939.html">一起嗨皮起来吧！宝可梦卡牌全新嗨皮组合即将发售 Product 2026-09-21</a><a href="/tcg/product/99999.html">嗨皮组合 Product 2026-09-17</a><a href="https://fake.example/box">礼盒 Product 2026-09-20</a>'''
HK = '''<li>擴充包「綠寶石風暴」<a href="/hk/archives/12345/">商品資訊</a></li><li>30th CELEBRATION FUTURISTIC BOX<a href="/hk/archives/8939/">商品資訊</a></li><li>收藏家組合 皮卡丘<a href="/hk/archives/8938/">商品資訊</a></li>'''
TW = '''<li>牌組構築BOX 樂園騰龍<a href="/tw/archives/9283/">商品資訊</a></li>'''

def sample(url):
    return CN if 'pokemon.cn' in url else HK if '/hk/' in url else TW

class ChinaV571Tests(unittest.TestCase):
    def test_distinct_editions_and_exact_official_urls(self):
        result=china.fetch_official_products(fetcher=sample)
        self.assertEqual(len(result['errors']),0)
        rows=result['items']
        self.assertTrue(any(x['region']=='CN-S' for x in rows))
        self.assertTrue(any(x['region']=='CN-T' and x['market_locale']=='HK' for x in rows))
        self.assertTrue(any(x['region']=='CN-T' and x['market_locale']=='TW' for x in rows))
        self.assertFalse(result['prices_verified'])
        self.assertFalse(result['holdings_created'])
        for x in rows:
            self.assertFalse(x['market_eligible'])
            self.assertEqual(x['price_evidence'],'NONE')
            self.assertEqual(x['official_price'],'확인 중')
            self.assertEqual(x['source_grade'],'official_catalog')
            self.assertIsNotNone(china.safe_link(china.SOURCES[0][2] if x['region']=='CN-S' else china.SOURCES[1][2],x['source'],x['region']))
    def test_invalid_urls_and_non_box_are_never_auto_promoted(self):
        for u in ('//evil.example/path','/tcg/product/001.html?token=x','/tcg/product/1.html','http://www.pokemon.cn/tcg/product/123.html'):
            self.assertIsNone(china.safe_link(china.SOURCES[0][2],u,'CN-S'))
        self.assertEqual(len(china.parse_official_html(CN,'CN-S','CN',china.SOURCES[0][2],'now')),2)
    def test_partial_timeout_is_held_and_other_sources_survive(self):
        def fail_hk(u):
            if '/hk/' in u: raise TimeoutError()
            return sample(u)
        result=china.fetch_official_products(fetcher=fail_hk)
        self.assertEqual(result['errors'][0]['locale'],'HK')
        self.assertTrue(result['items'])
    def test_auto_watch_pipeline_and_fail_closed_validator(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            (base/'releases.json').write_text(json.dumps({'items':[]}),encoding='utf-8')
            (base/'market_watch.json').write_text(json.dumps({'items':[]}),encoding='utf-8')
            auto=china.fetch_official_products(fetcher=sample)
            with patch.object(watch,'OUT',base/'market_watch.json'),patch.object(watch,'RELEASES',base/'releases.json'),patch.object(watch.china,'fetch_official_products',return_value=auto),patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
                first=watch.main()
                second=watch.main()
            selected=[x for x in second['items'] if x.get('autodiscovered') is True]
            self.assertEqual(len(selected),len(auto['items']))
            self.assertEqual(len({(x['region'],x['market_locale'],x['name']) for x in selected}),len(selected))
            auto_update_all.validate_json('market_watch.json',second)
            invalid=dict(second)
            invalid['items']=[{**selected[0],'market_eligible':True}]
            with self.assertRaises(ValueError):
                auto_update_all.validate_json('market_watch.json',invalid)
    def test_ui_integration_is_source_only_no_holdings_autowrite(self):
        js=(Path(__file__).resolve().parent/'tcg_market_expanded_v487.js').read_text(encoding='utf-8')
        v=js.split('/* V571: automatic CN-S/CN-T OFFICIAL catalog',1)[1]
        self.assertIn('fetch("market_watch.json"',v)
        self.assertIn('price_evidence!=="NONE"',v)
        self.assertIn('row.market_eligible!==false',v)
        self.assertNotIn('localStorage.setItem(',v)
        self.assertNotIn('innerHTML',v)

if __name__=="__main__":
    unittest.main(verbosity=2)
