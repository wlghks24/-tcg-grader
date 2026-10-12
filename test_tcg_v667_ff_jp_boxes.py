#!/usr/bin/env python3
"""V667: exact Japan FFTCG source-backed product variants, 36 to 18 packs."""
import copy
import json
import shutil
import subprocess
import unittest
from execution.official_box_coverage_audit_v623 import ROOT,CoverageError,_load_json
from tcg_official_overlay_v667 import build,validate_v667,load_chain
from tcg_source_audit_v633 import plan
NODE=shutil.which("node")
def read(n):return _load_json(ROOT/n)
class FFJapanV667QA(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.reg=read("tcg_game_registry.json")
  cls.intake=read("tcg_user_research_intake_v625.json")
  cls.base=read("tcg_official_product_catalog_v599.json")
  cls.part=[read("tcg_official_product_supplement_v"+str(v)+".json") for v in (630,636,637,649,654,657,659,662,663,665,667)]
  cls.promo=read("tcg_official_promo_evidence_v663.json")
 def test_py_103_66_18_and_prior_101_64_19(self):
  v=build()
  self.assertEqual((101,64,19),(v["prior"]["products"],v["prior"]["boxes"],v["prior"]["box_gaps"]))
  self.assertEqual((103,66,37,18),(v["with_v667"]["products"],v["with_v667"]["boxes"],
     v["with_v667"]["with_box"],v["with_v667"]["box_gaps"]))
  self.assertEqual(55,v["with_v667"]["scopes"])
  prev=plan(self.reg,self.intake,self.base,*self.part[:-1][:5],*self.part[:-1][5:8],
     self.part[8],self.promo,self.part[9])
  new=plan(self.reg,self.intake,self.base,*self.part[:5],*self.part[5:8],
     self.part[8],self.promo,self.part[9],self.part[10])
  self.assertEqual((101,64,19),(prev["official_product_samples"],prev["official_sealed_box_samples"],prev["declared_sealed_box_spec_gaps"]))
  self.assertEqual((103,66,18),(new["official_product_samples"],new["official_sealed_box_samples"],new["declared_sealed_box_spec_gaps"]))
 def test_two_time_dated_formats_msrp_protected(self):
  _,previous,products=load_chain()
  self.assertEqual(2,len(validate_v667(self.part[-1],self.reg,previous)))
  self.assertEqual([(36,15840),(18,8910)],[(p["packs_per_box"],p["msrp"]["amount"]) for p in products])
  for field,value in (("packs_per_box",36),("release_date","2025-04-01"),
      ("source","https://jp.finalfantasy.com.bad.tld/news/5659"),
      ("market_price",99000)):
   with self.subTest(field=field):
    bad=copy.deepcopy(self.part[-1]);bad["products"][1][field]=value
    with self.assertRaises(CoverageError):validate_v667(bad,self.reg,previous)
  bad=copy.deepcopy(self.part[-1]);bad["products"][1]["msrp"]["amount"]=9999
  with self.assertRaisesRegex(CoverageError,"V667_INVALID_MANUFACTURER_SPEC"):
   validate_v667(bad,self.reg,previous)
  bad=copy.deepcopy(self.part[-1]);bad["products"][1]["msrp"]["sold_price"]=6000
  with self.assertRaisesRegex(CoverageError,"V667_INVALID_MANUFACTURER_SPEC"):
   validate_v667(bad,self.reg,previous)
 @unittest.skipUnless(NODE,"Node.js unavailable")
 def test_node_research_and_radar_version_consistency(self):
  script=r"""
const assert=require("node:assert/strict");
const reg=require("./tcg_game_registry.json"),intake=require("./tcg_user_research_intake_v625.json"),
base=require("./tcg_official_product_catalog_v599.json"),promo=require("./tcg_official_promo_evidence_v663.json");
const p=[630,636,637,649,654,657,659,662,663,665,667].map(n=>require("./tcg_official_product_supplement_v"+n+".json"));
const official=require("./official_box_catalog_v626.js"),research=require("./tcg_source_research_v634.js"),radar=require("./tcg_coverage_radar_v652.js");
const a=research.build(reg,intake,base,...p.slice(0,6),official,p[6],p[7],p[8],promo,p[9]);
const b=research.build(reg,intake,base,...p.slice(0,6),official,p[6],p[7],p[8],promo,p[9],p[10]);
assert.deepEqual([a.summary.official,a.summary.officialBoxes,a.summary.boxMissing],[101,64,19]);
assert.deepEqual([b.summary.official,b.summary.officialBoxes,b.summary.boxMissing],[103,66,18]);
const out=radar.build(reg,intake,base,...p.slice(0,4),{research,official},require("./tcg_region_lifecycle_v653.json"),p[4],p[5],p[6],p[7],p[8],promo,p[9],p[10]);
assert.deepEqual([out.official_product_samples,out.official_box_samples,out.declared_box_gaps],[103,66,18]);
const evil=structuredClone(p[10]);evil.products[1].msrp.amount=50000;
assert.throws(()=>official.validateV667(evil,[]),/UNTRUSTED_V667_PRODUCT/);
"""
  ran=subprocess.run([NODE,"-e",script],cwd=ROOT,text=True,capture_output=True,timeout=30)
  self.assertEqual(0,ran.returncode,ran.stderr)
if __name__=="__main__":unittest.main(verbosity=2)
