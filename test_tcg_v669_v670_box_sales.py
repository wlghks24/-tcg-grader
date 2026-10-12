#!/usr/bin/env python3
"""V669/670: manufacturer sealed Japan BOX and eBay sold-listing observation firewalls."""
import copy
import shutil
import subprocess
import unittest
from decimal import Decimal
from execution.official_box_coverage_audit_v623 import ROOT,CoverageError,_load_json
from tcg_official_overlay_v669 import build,validate_v669
from tcg_sold_listing_audit_v670 import FILE as SOLD_FILE,validate_sold_listing_observations,report
from tcg_source_audit_v633 import plan
NODE=shutil.which("node")
def read(path):return _load_json(ROOT/path)
class MarketScopeProofV669V670(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.registry=read("tcg_game_registry.json")
  cls.intake=read("tcg_user_research_intake_v625.json")
  cls.base=read("tcg_official_product_catalog_v599.json")
  cls.parts=[read("tcg_official_product_supplement_v"+str(v)+".json")
    for v in (630,636,637,649,654,657,659,662,663,665,667,669)]
  cls.promo=read("tcg_official_promo_evidence_v663.json")
  cls.sold=read(SOLD_FILE)
 def test_manufacturer_104_67_17_scopes(self):
  b=build()
  self.assertEqual((103,66,18),(b["previous"]["products"],b["previous"]["boxes"],b["previous"]["gaps"]))
  self.assertEqual((104,67,55,38,17),tuple(b["current"][k] for k in
     ("products","boxes","scopes","with_box","gaps")))
  base=self.parts
  old=plan(self.registry,self.intake,self.base,*base[:4],base[4],base[5],
     base[6],base[7],base[8],self.promo,base[9],base[10])
  new=plan(self.registry,self.intake,self.base,*base[:4],base[4],base[5],
     base[6],base[7],base[8],self.promo,base[9],base[10],base[11])
  self.assertEqual((103,66,18),(old["official_product_samples"],
      old["official_sealed_box_samples"],old["declared_sealed_box_spec_gaps"]))
  self.assertEqual((104,67,17),(new["official_product_samples"],
      new["official_sealed_box_samples"],new["declared_sealed_box_spec_gaps"]))
 def test_godzilla_japan_pack_msrp_and_integrity(self):
  p=validate_v669(self.parts[-1],self.registry)[0]
  self.assertEqual((12,"7",5280,"JPY"),(p["packs_per_box"],p["cards_per_pack"],
        p["msrp"]["amount"],p["msrp"]["currency"]))
  for field,value in (("packs_per_box",24),("source","https://godzilla-cardgame.com.evil.test/"),
      ("country","US"),("hit_probability",0.9),("market_price",10000)):
   with self.subTest(field=field):
    fake=copy.deepcopy(self.parts[-1]);fake["products"][0][field]=value
    with self.assertRaises(CoverageError):validate_v669(fake,self.registry)
  fake=copy.deepcopy(self.parts[-1]);fake["products"][0]["msrp"]["amount"]=5500
  with self.assertRaises(CoverageError):validate_v669(fake,self.registry)
 def test_four_ebay_sold_flags_but_zero_proven_settlements(self):
  rows=validate_sold_listing_observations(self.sold)
  self.assertEqual(4,len(rows))
  self.assertTrue(all(x["listing_status_observed"]=="SOLD" for x in rows))
  self.assertTrue(all(x["settlement_verified"] is False and x["eligible_for_public_price_index"] is False for x in rows))
  stats=report()
  self.assertEqual((4,"159.99","189.99","169.995",0),(
   stats["sold_page_observations"],stats["displayed_usd_sample_min"],
   stats["displayed_usd_sample_max"],stats["displayed_usd_sample_median"],
   stats["settlement_verified_count"]))
 def test_invalid_sale_settlement_shipping_currency_price_rejected(self):
  for key,value in (("settlement_verified",True),("eligible_for_public_price_index",True),
    ("displayed_price_usd",199),("source_url","https://www.ebay.com.evil.test/itm/336825478808"),
    ("currency","JPY"),("shipping_tax_fees_unknown",False),("quantity",2)):
   with self.subTest(field=key):
    fake=copy.deepcopy(self.sold);fake["records"][0][key]=value
    with self.assertRaises(ValueError):validate_sold_listing_observations(fake)
  fake=copy.deepcopy(self.sold);fake["records"].append(fake["records"][0])
  with self.assertRaises(ValueError):validate_sold_listing_observations(fake)
 @unittest.skipUnless(NODE,"Node.js missing")
 def test_real_node_scope_104_67_17_and_fallback(self):
  js=r"""
const assert=require("node:assert/strict"), reg=require("./tcg_game_registry.json"),
intake=require("./tcg_user_research_intake_v625.json"),
base=require("./tcg_official_product_catalog_v599.json");
const s=[630,636,637,649,654,657,659,662,663,665,667,669].map(n=>require("./tcg_official_product_supplement_v"+n+".json"));
const promo=require("./tcg_official_promo_evidence_v663.json");
const off=require("./official_box_catalog_v626.js"),r=require("./tcg_source_research_v634.js"),
radar=require("./tcg_coverage_radar_v652.js");
const before=r.build(reg,intake,base,...s.slice(0,6),off,s[6],s[7],s[8],promo,s[9],s[10]);
const now=r.build(reg,intake,base,...s.slice(0,6),off,s[6],s[7],s[8],promo,s[9],s[10],s[11]);
assert.deepEqual([before.summary.official,before.summary.officialBoxes,before.summary.boxMissing],[103,66,18]);
assert.deepEqual([now.summary.official,now.summary.officialBoxes,now.summary.boxMissing],[104,67,17]);
const rd=radar.build(reg,intake,base,...s.slice(0,4),{research:r,official:off},
require("./tcg_region_lifecycle_v653.json"),s[4],s[5],s[6],s[7],s[8],promo,s[9],s[10],s[11]);
assert.deepEqual([rd.official_product_samples,rd.official_box_samples,rd.declared_box_gaps],[104,67,17]);
const bad=structuredClone(s[11]);bad.products[0].msrp.amount=999999;
assert.throws(()=>off.validateV669(bad,[]),/UNTRUSTED_V669_PRODUCT/);
"""
  p=subprocess.run([NODE,"-e",js],cwd=ROOT,capture_output=True,text=True,timeout=30)
  self.assertEqual(0,p.returncode,p.stderr)
if __name__=="__main__":unittest.main(verbosity=2)
