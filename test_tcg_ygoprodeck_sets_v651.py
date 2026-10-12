#!/usr/bin/env python3
"""V651 free, zero-key YGOPRODeck v7 set-index collector safety regression."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.error import HTTPError
import json
import tempfile
import unittest

import tcg_ygoprodeck_sets_v651 as y

NOW=datetime(2026,10,12,12,0,tzinfo=timezone.utc)


class YgoSetCollectorQA(unittest.TestCase):
    def payload(self):
        return [
          {"set_name":"Legend of Blue Eyes White Dragon","set_code":"LOB",
           "num_of_cards":126,"tcg_date":"2002-03-08"},
          {"set_name":"Duelist Nexus","set_code":"DUNE",
           "num_of_cards":101,"tcg_date":"2023-07-28"}
        ]

    def test_schema_counts_are_not_box_pack_claims(self):
        rows=y.clean_sets(self.payload())
        self.assertEqual(2,len(rows))
        self.assertEqual({"set_code","set_name","card_count_in_set","tcg_date"},set(rows[0]))
        self.assertNotIn("packs_per_box",rows[0])
        self.assertNotIn("msrp",rows[0])
        self.assertNotIn("price",rows[0])
        self.assertEqual(48,y.TTL.total_seconds()/3600)
        invalid=self.payload();invalid.append(dict(invalid[0]))
        with self.assertRaises(ValueError):y.clean_sets(invalid)
        for value in (True,-1,10001):
            invalid=self.payload();invalid[0]["num_of_cards"]=value
            with self.assertRaises(ValueError):y.clean_sets(invalid)
        wrong=self.payload();wrong[0]["set_code"]="../../escape"
        with self.assertRaises(ValueError):y.clean_sets(wrong)

    def test_one_request_with_last_good_cache_304_and_429(self):
        class Response:
            def __init__(self,data):
                self.body=json.dumps(data).encode("utf-8")
                self.headers={"ETag":'"stable"'}
            def geturl(self):return y.ENDPOINT
            def getcode(self):return 200
            def read(self,n):return self.body[:n]
            def __enter__(self):return self
            def __exit__(self,*args):return False
        class Opener:
            def __init__(self,data=None,code=None):
                self.data=data;self.code=code;self.calls=0
            def open(self,request,timeout):
                self.calls+=1
                if self.code:
                    raise HTTPError(request.full_url,self.code,"HTTP error",{},None)
                return Response(self.data)
        with tempfile.TemporaryDirectory() as tmp:
            opener=Opener(self.payload())
            initial=y.sync(tmp,clock=NOW,opener=opener)
            self.assertEqual("UPDATED_COMMUNITY_SET_INDEX",initial["status"])
            self.assertEqual((2,1),(initial["sets"],initial["network_calls"]))
            self.assertEqual(1,opener.calls)
            self.assertEqual(2,len(y.read_cached(tmp)["rows"]))
            fresh=y.sync(tmp,clock=NOW+timedelta(hours=24),opener=opener)
            self.assertEqual(("FRESH_CACHE",0),(fresh["status"],fresh["network_calls"]))
            self.assertEqual(1,opener.calls)
            unmodified=y.sync(tmp,clock=NOW+timedelta(hours=49),opener=Opener(code=304))
            self.assertEqual("NOT_MODIFIED",unmodified["status"])
            rate=y.sync(tmp,clock=NOW+timedelta(hours=100),opener=Opener(code=429))
            self.assertEqual("RATE_LIMIT_STOP",rate["status"])
            self.assertTrue(rate["using_stale"])
            malformed=y.sync(tmp,clock=NOW+timedelta(hours=100),opener=Opener([{"bad":"record"}]))
            self.assertEqual("ERROR_LAST_GOOD",malformed["status"])
            self.assertEqual(2,len(y.read_cached(tmp)["rows"]))
            self.assertEqual("NO_CACHE_OFFLINE" if y.read_cached(Path(tmp)/"empty") is None else "BAD","NO_CACHE_OFFLINE")

    def test_redirect_or_invalid_date_is_not_promoted(self):
        class Redirect:
            def geturl(self):return "https://attacker.example/fake"
            def getcode(self):return 200
            def __enter__(self):return self
            def __exit__(self,*args):return False
        class Opener:
            def open(self,req,timeout):return Redirect()
        with tempfile.TemporaryDirectory() as tmp:
            p=y.sync(tmp,clock=NOW,opener=Opener())
            self.assertEqual("REDIRECT_REVIEW",p["status"])
            self.assertIsNone(y.read_cached(tmp))
        wrong=self.payload();wrong[0]["tcg_date"]="tomorrow"
        with self.assertRaises(ValueError):y.clean_sets(wrong)
        self.assertEqual("https://db.ygoprodeck.com/api/v7/cardsets.php",y.ENDPOINT)

if __name__=="__main__":
    unittest.main(verbosity=2)
