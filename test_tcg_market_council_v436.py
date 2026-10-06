import unittest
from datetime import datetime,timezone
from tcg_market_council_v436 import assess_game,build_tablet_plan
NOW=datetime(2026,10,6,tzinfo=timezone.utc)
class V436(unittest.TestCase):
 def game(self,catalog=2000,stamp="2026-10-05T00:00:00+00:00",state="watch"):
  return {"id":"x","canonical":"X","state":state,"regions":["KR","US"],"capabilities":{"grading":False},"evidence":{"official_live":True,"organized_play":True,"collector_rarity_signal":True,"marketplace_catalog_count":catalog,"last_verified_at":stamp}}
 def test_deep_fresh_market_can_be_candidate_but_not_auto_grade(self):
  r=assess_game(self.game(),now=NOW);self.assertEqual("PROMOTION_CANDIDATE",r["decision"]);self.assertFalse(r["grading_enabled"])
 def test_stale_is_reverify_not_promote(self):
  self.assertEqual("REVERIFY",assess_game(self.game(stamp="2026-01-01T00:00:00+00:00"),now=NOW)["decision"])
 def test_thin_catalog_not_promoted(self):
  self.assertNotEqual("PROMOTION_CANDIDATE",assess_game(self.game(catalog=100),now=NOW)["decision"])
 def test_plan_bounded(self):
  p=build_tablet_plan({"games":[self.game()]},now=NOW);self.assertFalse(p["autonomy"]["may_auto_enable_grading"]);self.assertFalse(p["autonomy"]["may_predict_profit"])
if __name__=="__main__":unittest.main()
