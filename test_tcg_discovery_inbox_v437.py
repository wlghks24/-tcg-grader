import unittest
from datetime import datetime,timezone
from tcg_discovery_inbox_v437 import normalize_candidate,build_inbox
NOW=datetime(2026,10,6,tzinfo=timezone.utc)
class V437(unittest.TestCase):
 def row(self,**kw):
  x={"canonical":"New TCG","official_source":"https://official.example/game","market_source":"https://market.example/game","regions":["US"],"marketplace_catalog_count":900,"official_live":True,"organized_play":True,"collector_rarity_signal":False};x.update(kw);return x
 def test_verified_candidate_is_watch_only(self):
  r=normalize_candidate(self.row(),now=NOW);self.assertEqual("WATCH_CANDIDATE",r["decision"]);self.assertFalse(r["grading_enabled"])
 def test_no_official_url_is_rejected(self):self.assertIsNone(normalize_candidate(self.row(official_source="http://bad.example"),now=NOW))
 def test_existing_not_duplicated(self):self.assertEqual([],build_inbox([self.row()],{"New TCG"},now=NOW)["watch_candidates"])
 def test_thin_unorganized_candidate_held(self):
  r=normalize_candidate(self.row(marketplace_catalog_count=20,organized_play=False),now=NOW);self.assertEqual("DISCOVERY_HOLD",r["decision"])
if __name__=="__main__":unittest.main()
