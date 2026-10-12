#!/usr/bin/env python3
"""V671: KR CookieRun Festival Arena booster display 30x5, KRW 30000."""
import copy,shutil,subprocess,unittest
from execution.official_box_coverage_audit_v623 import ROOT,CoverageError,_load_json
from tcg_official_overlay_v671 import build,validate_v671
from tcg_source_audit_v633 import plan
NODE=shutil.which("node")
def read(n):return _load_json(ROOT/n)
class KoreaCookieV671(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.reg=read("tcg_game_registry.json")
  cls.intake=read("tcg_user_research_intake_v625.json")
  cls.base=read("tcg_official_product_catalog_v599.json")
  cls.parts=[read("tcg_official_product_supplement_v"+str(n)+".json") for n in
             (630,636,637,649,654,657,659,662,663,665,667,669,671)]
  cls.promo=read("tcg_official_promo_evidence_v663.json")
 def test_official_region_and_prior_counts(self):
  r=build()
  self.assertEqual((104,67,38,17),tuple(r["previous"][k] for k in
   ("official_products","box_samples","scope_with_box","scope_gaps")))
  self.assertEqual((105,68,55,39,16),tuple(r["current"][k] for k in
   ("official_products","box_samples","declared_scopes","scope_with_box","scope_gaps")))
  self.assertEqual(0,r["network_calls"])
  x=self.parts
  older=plan(self.reg,self.intake,self.base,*x[:4],x[4],x[5],x[6],x[7],x[8],self.promo,x[9],x[10],x[11])
  newer=plan(self.reg,self.intake,self.base,*x[:4],x[4],x[5],x[6],x[7],x[8],self.promo,x[9],x[10],x[11],x[12])
  self.assertEqual((104,67,17),(older["official_product_samples"],older["official_sealed_box_samples"],older["declared_sealed_box_spec_gaps"]))
  self.assertEqual((105,68,16),(newer["official_product_samples"],newer["official_sealed_box_samples"],newer["declared_sealed_box_spec_gaps"]))
 def test_pack_coupon_price_no_us_variant(self):
  proof=validate_v671(self.parts[-1],self.reg)[0]
  self.assertEqual(("KR",30,"5","KRW",30000),(proof["country"],proof["packs_per_box"],
    proof["cards_per_pack"],proof["msrp"]["currency"],proof["msrp"]["amount"]))
  for k,v in (("country","US"),("packs_per_box",28),
       ("cards_per_pack","9"),("source","https://cookierunbraverse.com.evil.test/"),
       ("market_price",50000),("hit_probability",0.9)):
   with self.subTest(field=k):
    fake=copy.deepcopy(self.parts[-1]);fake["products"][0][k]=v
    with self.assertRaises(CoverageError):validate_v671(fake,self.reg)
  fake=copy.deepcopy(self.parts[-1]);fake["products"][0]["msrp"]["amount"]=40000
  with self.assertRaises(CoverageError):validate_v671(fake,self.reg)
 @unittest.skipUnless(NODE,"Node unavailable")
 def test_node_all_views_105_68_16(self):
  script=r"""
const assert=require("node:assert/strict");
const reg=require("./tcg_game_registry.json"),intake=require("./tcg_user_research_intake_v625.json"),
base=require("./tcg_official_product_catalog_v599.json"),promo=require("./tcg_official_promo_evidence_v663.json");
const p=[630,636,637,649,654,657,659,662,663,665,667,669,671].map(n=>require("./tcg_official_product_supplement_v"+n+".json"));
const official=require("./official_box_catalog_v626.js"),research=require("./tcg_source_research_v634.js");
const radar=require("./tcg_coverage_radar_v652.js"),viewer=require("./tcg_30_game_catalog_v629.js");
const old=research.build(reg,intake,base,...p.slice(0,6),official,p[6],p[7],p[8],promo,p[9],p[10],p[11]);
const now=research.build(reg,intake,base,...p.slice(0,6),official,p[6],p[7],p[8],promo,p[9],p[10],p[11],p[12]);
assert.deepEqual([old.summary.official,old.summary.officialBoxes,old.summary.boxMissing],[104,67,17]);
assert.deepEqual([now.summary.official,now.summary.officialBoxes,now.summary.boxMissing],[105,68,16]);
const x=radar.build(reg,intake,base,...p.slice(0,4),{research,official},require("./tcg_region_lifecycle_v653.json"),p[4],p[5],p[6],p[7],p[8],promo,p[9],p[10],p[11],p[12]);
assert.deepEqual([x.official_product_samples,x.official_box_samples,x.declared_box_gaps,x.manual_search_tasks],[105,68,16,540]);
const counts=viewer.officialCounts({schema_version:1,products:[...base.products,...p.flatMap(x=>x.products)]},reg,official);
assert.equal(Object.values(counts).reduce((a,b)=>a+b,0),105);
"""
  p=subprocess.run([NODE,"-e",script],cwd=ROOT,text=True,capture_output=True,timeout=30)
  self.assertEqual(0,p.returncode,p.stderr)
if __name__=="__main__":unittest.main(verbosity=2)
