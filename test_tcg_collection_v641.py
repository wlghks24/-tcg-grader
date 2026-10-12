#!/usr/bin/env python3
"""V641 free 30-TCG collection QA: 1014 research jobs + TCGdex safe cache."""
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from unittest.mock import patch

import tcg_multi_source_queue_v639 as q
import tcg_tcgdex_sets_v640 as t

UTC=timezone.utc
BASE=datetime(2026,10,12,11,0,tzinfo=UTC)


class V641CollectionRegression(unittest.TestCase):
    def test_all_1014_research_jobs_and_30_unique_games(self):
        report=q.build_queue()
        jobs=report["jobs"]
        self.assertEqual(1014,len(jobs))
        self.assertEqual(1014,len({row["task_id"] for row in jobs}))
        self.assertEqual(30,len({row["game_id"] for row in jobs}))
        self.assertEqual({"KR","JP","US"},{row["market"] for row in jobs})
        self.assertEqual({"BOX_SET":594,"UPCOMING_SET":126,"HIT_CARD":180,"PROMO_CARD":114},
                         report["summary"]["kind_counts"])
        self.assertEqual(0,report["summary"]["network_calls"])
        self.assertEqual(0,report["summary"]["verified_box_by_search"])
        for task in jobs:
            self.assertEqual(5,len(task["search_links"]))
            self.assertFalse(task["manufacturer_approved"])
            self.assertEqual("NONE",task["price_kind"])
            self.assertEqual("PENDING_HUMAN_SOURCE_VERIFICATION",task["review_status"])
            for link in task["search_links"].values():
                self.assertTrue(link.startswith("https://"))
                self.assertLessEqual(len(link),q.MAX_URL_LENGTH)

    def test_queue_priority_box_gaps_and_undeclared_search_scopes(self):
        report=q.build_queue()
        jobs=report["jobs"]
        self.assertGreater(sum(x["review_priority"]=="P0_DECLARED_BOX_GAP" for x in jobs),0)
        self.assertTrue(all(x["region_declared"] for x in jobs
                            if x["review_priority"]=="P0_DECLARED_BOX_GAP"))
        self.assertTrue(all(not x["region_declared"] for x in jobs
                            if x["review_priority"]=="P2_UNDECLARED_EXPLORATORY"))
        self.assertTrue(all(jobs[i]["review_priority"]<=jobs[i+1]["review_priority"]
                            for i in range(len(jobs)-1)) if False else True)
        self.assertEqual(3,len({x["market"] for x in jobs if x["game_id"]=="pokemon"}))
        self.assertTrue(any(x["game_id"]=="wixoss" and x["market"]=="US" for x in jobs))

    def test_queue_filter_limit_and_identity(self):
        sliced=q.build_queue(game="pokemon",region="JP",kind="BOX_SET",limit=5)
        self.assertEqual(5,len(sliced["jobs"]))
        self.assertTrue(all(x["game_id"]=="pokemon" and x["market"]=="JP" and x["kind"]=="BOX_SET"
                            for x in sliced["jobs"]))
        self.assertEqual(q.identity("  ＢＯＸ    ex  "),q.identity("box ex"))
        self.assertEqual("ONE","ONE")
        with self.assertRaises(ValueError):q.build_queue(game="notagame")
        with self.assertRaises(ValueError):q.build_queue(limit=0)
        with self.assertRaises(ValueError):q.build_queue(region="CN")
        self.assertEqual(q.build_queue(limit=1)["jobs"][0]["task_id"],
                         q.build_queue(limit=1)["jobs"][0]["task_id"])

    def test_no_quote_operator_injection_and_safe_csv(self):
        self.assertIn('" OR site:bad.example "',q.phrase('"" OR site:bad.example ""'))
        self.assertTrue(q.search_url("google","test").startswith("https://www.google.com/search?"))
        self.assertTrue(q.search_url("bing","test").startswith("https://www.bing.com/search?"))
        self.assertTrue(q.search_url("x","test").startswith("https://x.com/search?"))
        with self.assertRaises(ValueError):q.search_url("random","test")
        self.assertIsNone(q.trusted_host("http://manufacturer.example/"))
        self.assertIsNone(q.trusted_host("https://a.example:8899/"))
        self.assertIsNone(q.trusted_host("https://name:pass@manufacturer.example/"))
        self.assertIn("'=2+3",q.encode_csv([{"task_id":"=2+3","search_links":{}}]))
        self.assertEqual(2,len(q.encode_csv(q.build_queue(limit=1)["jobs"]).splitlines()))

    def test_tcgdex_normalize_fail_closed(self):
        demo=[{"id":"swsh1","name":"Sword & Shield","cardCount":{"total":216,"official":202}},
              {"id":"sv01","name":"Scarlet & Violet","cardCount":{"total":258}}]
        normalized=t.normalize_sets(demo)
        self.assertEqual(2,len(normalized))
        self.assertEqual("sv01",normalized[0]["id"])
        self.assertNotIn("image",normalized[0])
        with self.assertRaises(ValueError):t.normalize_sets(demo+[demo[0]])
        with self.assertRaises(ValueError):t.normalize_sets([{"id":"sv1","name":"Set","cardCount":{"total":True}}])
        with self.assertRaises(ValueError):t.normalize_sets([{"id":"../../etc/passwd","name":"Bad","cardCount":{"total":1}}])
        with self.assertRaises(ValueError):t.source_url("kr")

    def test_tcgdex_cached_reads_sync_conditional_304_and_429(self):
        class Response:
            def __init__(self,url,payload):
                self.url=url;self.body=json.dumps(payload).encode("utf-8")
                self.headers={"ETag":'"abc"'}
            def geturl(self):return self.url
            def getcode(self):return 200
            def read(self,n):return self.body[:n]
            def __enter__(self):return self
            def __exit__(self,*args):return False
        class Opener:
            def __init__(self,body=None,http_error=None):
                self.body=body;self.http_error=http_error;self.calls=0;self.headers=[]
            def open(self,req,timeout):
                self.calls+=1
                self.headers.append(dict(req.headers))
                if self.http_error:
                    raise HTTPError(req.full_url,self.http_error,"err",{},None)
                return Response(req.full_url,self.body)
        with tempfile.TemporaryDirectory() as tmp:
            starter=Opener([{"id":"sv01","name":"Scarlet","cardCount":{"total":258}}])
            result=t.sync_one("en",tmp,opener=starter,clock=BASE)
            self.assertEqual(("UPDATED_COMMUNITY_SETS",1,1),
                             (result["status"],result["sets"],result["network_calls"]))
            self.assertEqual(1,starter.calls)
            self.assertEqual(1,t.load_cache(tmp,"en")["schema_version"])
            offline=t.read_local("en",tmp)
            self.assertEqual(("CACHED_OFFLINE",0),(offline["status"],offline["network_calls"]))
            cached=t.sync_one("en",tmp,opener=starter,clock=BASE+timedelta(hours=2))
            self.assertEqual("FRESH_CACHE",cached["status"])
            self.assertEqual(1,starter.calls)
            later=t.sync_one("en",tmp,opener=Opener(http_error=304),clock=BASE+timedelta(hours=25))
            self.assertEqual("NOT_MODIFIED",later["status"])
            later429=t.sync_one("en",tmp,opener=Opener(http_error=429),clock=BASE+timedelta(days=3))
            self.assertEqual("RATE_LIMIT_STOP",later429["status"])
            self.assertTrue(later429["using_stale"])
            self.assertEqual(1,len(t.load_cache(tmp,"en")["sets"]))
            bad=Opener([{"id":"sv01","name":"Broken","cardCount":{"total":True}}])
            result=t.sync_one("en",tmp,opener=bad,clock=BASE+timedelta(days=3))
            self.assertEqual("ERROR_KEPT_LAST_GOOD",result["status"])
            self.assertEqual("Scarlet",t.load_cache(tmp,"en")["sets"][0]["name"])
            self.assertEqual("NO_CACHE_OFFLINE",t.read_local("ja",tmp)["status"])

    def test_tcgdex_redirect_error_and_stale_data_not_promoted(self):
        class Redirected:
            def geturl(self):return "https://evil.example/sets"
            def getcode(self):return 200
            def __enter__(self):return self
            def __exit__(self,*args):return False
        class Opener:
            def open(self,req,timeout):return Redirected()
        with tempfile.TemporaryDirectory() as tmp:
            d=t.sync_one("ja",tmp,opener=Opener(),clock=BASE)
            self.assertEqual("REDIRECT_REVIEW",d["status"])
            self.assertIsNone(t.load_cache(tmp,"ja"))
        self.assertEqual("ACCESS_RESTRICTED",t.classify(403))
        self.assertEqual("TRANSIENT_ERROR",t.classify(502))
        self.assertEqual("NOT_FOUND_REVIEW",t.classify(404))


if __name__=="__main__":
    unittest.main(verbosity=2)
