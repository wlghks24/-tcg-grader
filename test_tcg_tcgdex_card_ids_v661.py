#!/usr/bin/env python3
"""V661: no-cost one-GET TCGdex Pokemon set IDs, offline cache, attack/error tests."""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from tcg_tcgdex_card_ids_v661 import endpoint,normalize,cache_file,cached,sync_one

NOW=datetime(2026,10,12,9,0,tzinfo=timezone.utc)
SAMPLE={"id":"sv01","name":"Scarlet & Violet","cards":[
    {"id":"sv01-001","localId":"001","name":"Sprigatito","image":"https://example.test/pic"},
    {"id":"sv01-002","localId":"002","name":"Floragato"}
]}

class Response:
    def __init__(self,url,value):
        self.url=url;self.body=json.dumps(value).encode("utf-8")
        self.headers={"ETag":'"mock"'}
    def geturl(self):return self.url
    def getcode(self):return 200
    def read(self,n):return self.body[:n]
    def __enter__(self):return self
    def __exit__(self,*_):return False

class Client:
    def __init__(self,payload=None,status=None):
        self.payload=payload or SAMPLE;self.status=status;self.calls=0
    def open(self,req,timeout):
        self.calls+=1
        if self.status:
            raise HTTPError(req.full_url,self.status,"mock",{},None)
        return Response(req.full_url,self.payload)

class FreePokemonCardsV661(unittest.TestCase):
    def test_offline_cache_and_no_image_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            c=Client()
            r=sync_one("en","sv01",folder,opener=c,clock=NOW)
            self.assertEqual(("UPDATED_COMMUNITY_CARD_IDS",2,1),
                             (r["status"],r["cards"],r["network_calls"]))
            self.assertEqual(1,c.calls)
            doc=cached(folder,"en","sv01")
            self.assertEqual(2,len(doc["cards"]))
            self.assertTrue(all(set(x)=={"id","local_id","name"} for x in doc["cards"]))
            again=sync_one("en","sv01",folder,opener=c,clock=NOW+timedelta(hours=2))
            self.assertEqual("FRESH_CACHE",again["status"])
            self.assertEqual(1,c.calls)
            failed=sync_one("en","sv01",folder,opener=Client(status=429),
                            clock=NOW+timedelta(hours=30))
            self.assertEqual("RATE_LIMIT_STOP",failed["status"])
            self.assertTrue(failed["using_stale"])
            self.assertEqual(2,len(cached(folder,"en","sv01")["cards"]))

    def test_exact_set_scope_and_duplicate_rejection(self):
        self.assertEqual(2,len(normalize(SAMPLE,"sv01")))
        with self.assertRaises(ValueError):endpoint("kr","sv01")
        with self.assertRaises(ValueError):endpoint("en","../secrets")
        bad={**SAMPLE,"id":"other"}
        with self.assertRaisesRegex(ValueError,"SET_ID_MISMATCH"):normalize(bad,"sv01")
        bad={**SAMPLE,"cards":SAMPLE["cards"]+[SAMPLE["cards"][0]]}
        with self.assertRaisesRegex(ValueError,"UNSAFE_OR_DUPLICATE_CARD_ID"):
            normalize(bad,"sv01")
        bad={**SAMPLE,"cards":[{"id":"sv01-009","localId":"009","name":"X"},
                                   {"id":"../evil","localId":"001","name":"Y"}]}
        with self.assertRaises(ValueError):normalize(bad,"sv01")

    def test_corrupted_network_does_not_destroy_old_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            c=Client()
            self.assertEqual("UPDATED_COMMUNITY_CARD_IDS",
                             sync_one("ja","sv01",folder,opener=c,clock=NOW)["status"])
            bad={**SAMPLE,"cards":[{"id":"other-001","localId":"001","name":"Wrong set"}]}
            out=sync_one("ja","sv01",folder,opener=Client(payload=bad),
                         clock=NOW+timedelta(days=2))
            self.assertEqual("ERROR_LAST_GOOD",out["status"])
            self.assertEqual("Sprigatito",cached(folder,"ja","sv01")["cards"][0]["name"])

if __name__=="__main__":
    unittest.main(verbosity=2)
