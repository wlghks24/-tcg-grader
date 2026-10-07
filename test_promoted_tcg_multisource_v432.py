#!/usr/bin/env python3
import unittest
import promoted_tcg_multisource_v432 as m
class V432Coverage(unittest.TestCase):
 def fixture(self):
  return {"games":[{"id":"x","canonical":"X TCG","label_ko":"X","state":"promoted",
   "regions":["KR","US"],"capabilities":{"market":True,"release":True,"promo":True,"purchase":True,"grading":False},
   "official_source":"https://official.example/products","market_source":"https://market.example/x"},
   {"id":"w","canonical":"WATCH","state":"watch","regions":["US"],
   "capabilities":{"market":True,"release":True,"promo":True,"purchase":True,"grading":False},
   "official_source":"https://watch.example/","market_source":"https://market.example/w"}]}
 def test_promoted_gets_all_nine_lanes_and_region_gap_queue(self):
  p=m.build_plan(self.fixture()); self.assertEqual(1,p["summary"]["promoted_games"])
  g=p["games"][0]; self.assertEqual(set(m.SOURCE_LANES),set(g["required_lanes"]))
  self.assertEqual(["KR","US"],g["regions"]); self.assertTrue(g["coverage_gap"])
  self.assertFalse(g["grading_enabled"])
  for row in g["region_gaps"]: self.assertIn("official_news",row["missing_lanes"])
 def test_only_verified_seed_lanes_count_as_covered(self):
  g=m.build_plan(self.fixture())["games"][0]
  status={x["lane"]:x["status"] for x in g["lanes"]}
  self.assertEqual("covered",status["official_home"]); self.assertEqual("covered",status["retailer"])
  self.assertEqual("queued",status["collaboration"]); self.assertEqual("queued",status["official_social"])
 def test_missing_urls_are_not_invented(self):
  f=self.fixture(); f["games"][0].pop("official_source"); f["games"][0].pop("market_source")
  g=m.build_plan(f)["games"][0]
  self.assertTrue(all(not x["seed_urls"] for x in g["lanes"]))
  self.assertEqual(0,g["coverage_verified_cells"])
if __name__=="__main__": unittest.main(verbosity=2)
