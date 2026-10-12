#!/usr/bin/env python3
"""V643 Scryfall opt-in set-index tests: no paid services or box inference."""
from datetime import datetime,timedelta,timezone
from urllib.error import HTTPError
import json
from pathlib import Path
import tempfile
import unittest

import tcg_scryfall_sets_v643 as mtg

NOW=datetime(2026,10,12,11,30,tzinfo=timezone.utc)


class ScryfallFreeSafetyV643(unittest.TestCase):
    def sample(self):
        return {"object":"list","has_more":False,"data":[
          {"code":"neo","name":"Kamigawa: Neon Dynasty","set_type":"expansion",
           "card_count":302,"released_at":"2022-02-18","digital":False},
          {"code":"tla","name":"Example digital catalog set","set_type":"token",
           "card_count":1,"released_at":None,"digital":True}]}

    def test_normalization_no_image_price_or_box_promotion(self):
        rows=mtg.normalize(self.sample())
        self.assertEqual(2,len(rows))
        self.assertEqual(302,rows[0]["card_count"])
        self.assertNotIn("msrp",rows[0])
        self.assertNotIn("packs_per_box",rows[0])
        self.assertNotIn("market_price",rows[0])
        duplicate=self.sample()
        duplicate["data"].append(dict(duplicate["data"][0]))
        with self.assertRaisesRegex(ValueError,"DUPLICATE_SET_CODE"):
            mtg.normalize(duplicate)
        partial=self.sample();partial["has_more"]=True
        with self.assertRaisesRegex(ValueError,"PARTIAL"):
            mtg.normalize(partial)
        dangerous=self.sample();dangerous["data"][0]["code"]="../etc/passwd"
        with self.assertRaises(ValueError):
            mtg.normalize(dangerous)

    def test_single_https_request_then_cache_and_304(self):
        class Response:
            def __init__(self,data):self.data=json.dumps(data).encode("utf-8");self.headers={"ETag":'"x"'}
            def geturl(self):return mtg.URL
            def getcode(self):return 200
            def read(self,n):return self.data[:n]
            def __enter__(self):return self
            def __exit__(self,*args):return False
        class Opener:
            def __init__(self,response=None,error=None):
                self.response=response;self.error=error;self.calls=0;self.headers=[]
            def open(self,req,timeout):
                self.calls+=1;self.headers.append(dict(req.headers))
                if self.error is not None:
                    raise HTTPError(req.full_url,self.error,"http",{},None)
                return Response(self.response)
        with tempfile.TemporaryDirectory() as folder:
            opener=Opener(self.sample())
            first=mtg.sync(folder,opener=opener,now=NOW)
            self.assertEqual(("UPDATED_COMMUNITY_SETS",2,1),
                             (first["status"],first["sets"],first["network_calls"]))
            self.assertEqual(1,opener.calls)
            self.assertTrue(mtg.read_cache(folder))
            cached=mtg.sync(folder,opener=opener,now=NOW+timedelta(hours=1))
            self.assertEqual("FRESH_CACHE",cached["status"])
            self.assertEqual(1,opener.calls)
            not_modified=mtg.sync(folder,opener=Opener(error=304),now=NOW+timedelta(hours=25))
            self.assertEqual("NOT_MODIFIED",not_modified["status"])
            limited=mtg.sync(folder,opener=Opener(error=429),now=NOW+timedelta(days=3))
            self.assertEqual("RATE_LIMIT_STOP",limited["status"])
            self.assertTrue(limited["using_stale"])
            self.assertEqual(2,len(mtg.read_cache(folder)["sets"]))
            bad=mtg.sync(folder,opener=Opener({"object":"list","has_more":True,"data":[]}),
                         now=NOW+timedelta(days=3))
            self.assertEqual("ERROR_LAST_GOOD",bad["status"])
            self.assertEqual(2,len(mtg.read_cache(folder)["sets"]))

    def test_manual_offline_mode_can_read_empty(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(mtg.read_cache(root))
        self.assertEqual("https://api.scryfall.com/sets",mtg.URL)


if __name__=="__main__":
    unittest.main(verbosity=2)
