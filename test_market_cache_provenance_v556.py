#!/usr/bin/env python3
"""V556: a recent timestamp alone never verifies an old market quote."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import market_public_crosscheck as market

KEY="KR|인페르노X|HIT"
NAME="메가리자몽X ex"
ROW={"key":KEY,"card_name":NAME,"card_number":"116/080","name":NAME,"region":"KR","game":"Pokémon"}
C_TEXT=f"{NAME} 116/080 공식 카드별 시세 ₩375,000"
K_TEXT=f"Pokemon TCG {NAME} 116/080 390,000원 거래 45"


class CacheProvenanceV556(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base=Path(tmp.name)
        patches=[
            mock.patch.object(market,"WATCH",base/"watch.json"),
            mock.patch.object(market,"STATE",base/"state.json"),
            mock.patch.object(market,"HEALTH",base/"link_health.json"),
        ]
        for patcher in patches:
            patcher.start();self.addCleanup(patcher.stop)
        market.WATCH.write_text('{"items":[]}',encoding="utf-8")
        self.db={"entries":{KEY:dict(ROW)}}
        self.calls=[]
        def fetch(url):
            self.calls.append(url)
            return C_TEXT if "collectory.cc" in url else K_TEXT
        self.fetch=fetch

    def cycle(self):
        with mock.patch.dict("os.environ",{
            "TCG_MARKET_CROSSCHECK_QUERIES":"1",
            "TCG_MARKET_CROSSCHECK_CACHE_SECONDS":"900",
            "TCG_MARKET_CROSSCHECK_SOURCE_WORKERS":"2"
        },clear=False):
            return market.crosscheck_market_db(self.db,fetcher=self.fetch)

    def test_fresh_exact_evidence_can_be_reused(self):
        first=self.cycle()
        self.assertEqual(first["matches"],2)
        second=self.cycle()
        self.assertEqual(second["cache_hits"],2)
        self.assertEqual(second["requests_checked"],0)
        self.assertEqual(len(self.calls),2)

    def test_changed_number_invalidates_both_quotes(self):
        self.cycle()
        self.db["entries"][KEY]["card_number"]="116/081"
        def fail(url):
            self.calls.append(url)
            raise TimeoutError("test only")
        self.fetch=fail
        result=self.cycle()
        self.assertEqual(result["cache_hits"],0)
        self.assertEqual(result["requests_checked"],2)
        self.assertEqual(result["matches"],0)
        self.assertEqual(result["sources"]["Collectory"]["errors"],1)
        self.assertEqual(result["sources"]["KREAM"]["errors"],1)
        # Last-known values remain dated; they must not become current cache hits.
        previous=self.db["entries"][KEY]["source_crosschecks"]
        self.assertEqual({r["source"] for r in previous},{"Collectory","KREAM"})

    def test_quote_cannot_be_reused_after_field_tampering(self):
        self.cycle()
        for field,bad in [
            ("url","https://evil.example/quote"),
            ("query","다른 상품 888/999"),
            ("matched_by","name"),
            ("price_krw",900_000_000),
            ("confidence",0.2),
            ("source","DifferentSource")
        ]:
            with self.subTest(field=field):
                row=dict(self.db["entries"][KEY]["source_crosschecks"][0])
                row[field]=bad
                good=self.db["entries"][KEY]["source_crosschecks"][0]
                expected_url=market._urls(market._search_term(ROW))[good["source"]]
                self.assertFalse(market._fresh_observation(
                    row,dt.datetime.now(dt.timezone.utc),900,
                    source=good["source"],row=ROW,
                    expected_url=expected_url,
                    expected_query=market._search_term(ROW)))

    def test_future_or_invalid_price_cannot_fake_verified_cache(self):
        self.cycle()
        valid=dict(self.db["entries"][KEY]["source_crosschecks"][0])
        url=market._urls(market._search_term(ROW))[valid["source"]]
        kwargs=dict(source=valid["source"],row=ROW,expected_url=url,
                    expected_query=market._search_term(ROW))
        for value in [True,-1,0,5_000_000_000,10.5,"390000",None]:
            with self.subTest(value=value):
                invalid={**valid,"price_krw":value}
                self.assertFalse(market._fresh_observation(
                    invalid,dt.datetime.now(dt.timezone.utc),900,**kwargs))
        future={**valid,"observed_at":(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=2)).isoformat()}
        self.assertFalse(market._fresh_observation(
            future,dt.datetime.now(dt.timezone.utc),900,**kwargs))

    def test_box_code_provenance_requires_code_match(self):
        now=dt.datetime.now(dt.timezone.utc)
        box={"name":"BOX TEST","product_code":"BOX-081"}
        quote={"source":"KREAM","price_krw":120000,"confidence":.96,
               "matched_by":"product_code+name",
               "observed_at":now.isoformat(),"url":"https://kream.co.kr/search?keyword=BOX-081",
               "query":"BOX-081 BOX TEST"}
        kw=dict(source="KREAM",row=box,expected_url=quote["url"],expected_query=quote["query"])
        self.assertTrue(market._fresh_observation(quote,now,900,**kw))
        self.assertFalse(market._fresh_observation(
            quote,now,900,**{**kw,"expected_query":"BOX-082 BOX TEST"}))


if __name__=="__main__":
    unittest.main()
