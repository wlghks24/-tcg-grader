#!/usr/bin/env python3
"""V662 regression: 3 Japan booster displays remain distinct from packs/promos/claims."""
import copy
import json
import shutil
import subprocess
import unittest
from execution.official_box_coverage_audit_v623 import ROOT, CoverageError, _load_json
from tcg_official_overlay_v662 import build, validate_v662
from tcg_source_audit_v633 import plan
NODE=shutil.which("node")

def read(name):
    return _load_json(ROOT/name)

class JPManufacturerDisplayV662(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg=read("tcg_game_registry.json")
        cls.intake=read("tcg_user_research_intake_v625.json")
        cls.base=read("tcg_official_product_catalog_v599.json")
        cls.s=[read("tcg_official_product_supplement_v"+str(n)+".json")
               for n in (630,636,637,649,654,657,659,662)]

    def test_python_99_box62_gaps21_and_previous96_fallback(self):
        report=build()
        self.assertEqual((96,59,24),
            (report["original"]["official_products"],
             report["original"]["official_boxes"],
             report["original"]["scopes_without_box"]))
        self.assertEqual((99,62,21,34,55),
            (report["candidate"]["official_products"],
             report["candidate"]["official_boxes"],
             report["candidate"]["scopes_without_box"],
             report["candidate"]["scopes_with_box"],
             report["candidate"]["region_scopes"]))
        self.assertEqual(0,report["network_calls"])
        old=plan(self.reg,self.intake,self.base,*self.s[:-1])
        new=plan(self.reg,self.intake,self.base,*self.s)
        self.assertEqual((96,59,24),(old["official_product_samples"],old["official_sealed_box_samples"],
                                     old["declared_sealed_box_spec_gaps"]))
        self.assertEqual((99,62,21),(new["official_product_samples"],new["official_sealed_box_samples"],
                                     new["declared_sealed_box_spec_gaps"]))
        self.assertEqual(338,sum(new[key] for key in (
          "product_candidate_count","upcoming_candidate_count","hit_candidate_count","promo_candidate_count")))
        self.assertTrue(all(row["price_evidence"]=="NONE" for row in new["scopes"]))

    def test_exact_jp_box_specs_and_only_authentic_msrp(self):
        data=self.s[-1]
        products=validate_v662(data,self.reg,[*self.base["products"],*
          [p for sub in self.s[:-1] for p in sub["products"]]])
        rows={p["id"]:p for p in products}
        self.assertEqual([30,12,24],[rows[i]["packs_per_box"] for i in (
          "mtg-JP-ECL-play-booster-2026","ws-JP-ALL-bplb-2026","dbsfw-JP-FB10-cross-force-2026")])
        self.assertEqual(5280,rows["ws-JP-ALL-bplb-2026"]["msrp"]["amount"])
        self.assertFalse(any("msrp" in p for p in products if p["game"]!="Weiß Schwarz"))

    def test_forged_proof_wrong_title_wrong_price_and_parent_denied(self):
        doc=copy.deepcopy(self.s[-1])
        doc["products"][0]["source"]="https://magic.wizards.com.attacker.example/ja/news"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_V662_PRODUCT"):
            validate_v662(doc,self.reg)
        doc=copy.deepcopy(self.s[-1])
        doc["products"][1]["name"]="Fake booster"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_V662_PRODUCT"):
            validate_v662(doc,self.reg)
        doc=copy.deepcopy(self.s[-1])
        doc["products"][1]["msrp"]["amount"]=52800
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_V662_PRODUCT"):
            validate_v662(doc,self.reg)
        doc=copy.deepcopy(self.s[-1])
        doc["append_after"]="tampered.json"
        with self.assertRaisesRegex(CoverageError,"INVALID_V662_CHAIN"):
            validate_v662(doc,self.reg)

    @unittest.skipUnless(NODE,"Node.js not available")
    def test_node_same_scopes_and_untrusted_overlay_fallback(self):
        script=r"""
const assert=require('node:assert/strict');
const reg=require('./tcg_game_registry.json'),leads=require('./tcg_user_research_intake_v625.json');
const b=require('./tcg_official_product_catalog_v599.json');
const x=[630,636,637,649,654,657,659,662].map(n=>require('./tcg_official_product_supplement_v'+n+'.json'));
const official=require('./official_box_catalog_v626.js');
const research=require('./tcg_source_research_v634.js');
const radar=require('./tcg_coverage_radar_v652.js');
const historical=require('./tcg_region_lifecycle_v653.json');
const old=research.build(reg,leads,b,...x.slice(0,6),official,x[6]);
const full=research.build(reg,leads,b,...x.slice(0,6),official,x[6],x[7]);
assert.deepEqual([old.summary.official,old.summary.officialBoxes,old.summary.boxMissing],[96,59,24]);
assert.deepEqual([full.summary.official,full.summary.officialBoxes,full.summary.boxMissing],[99,62,21]);
const out=radar.build(reg,leads,b,...x.slice(0,4),{research,official},historical,
  x[4],x[5],x[6],x[7]);
assert.deepEqual([out.official_product_samples,out.official_box_samples,out.declared_box_gaps],[99,62,21]);
const fake=structuredClone(x[7]);fake.products[1].msrp.amount=900000;
assert.throws(()=>official.validateV662(fake,[]),/UNTRUSTED_V662_PRODUCT/);
"""
        run=subprocess.run([NODE,"-e",script],cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(0,run.returncode,run.stderr)

if __name__=="__main__":
    unittest.main(verbosity=2)
