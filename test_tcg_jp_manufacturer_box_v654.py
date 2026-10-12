#!/usr/bin/env python3
"""V654: three newly cited Japanese manufacturer BOX scopes plus no regressions."""
from datetime import date
from pathlib import Path
import copy
import json
import shutil
import subprocess
import unittest

from execution.official_box_coverage_audit_v623 import audit, CoverageError
from tcg_source_audit_v633 import plan

ROOT=Path(__file__).resolve().parent
NODE=shutil.which("node")

class V654ManufacturerBoxProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        read=lambda name:json.loads((ROOT/name).read_text(encoding="utf-8"))
        cls.reg=read("tcg_game_registry.json")
        cls.intake=read("tcg_user_research_intake_v625.json")
        cls.b=read("tcg_official_product_catalog_v599.json")
        cls.a=read("tcg_official_product_supplement_v630.json")
        cls.c=read("tcg_official_product_supplement_v636.json")
        cls.d=read("tcg_official_product_supplement_v637.json")
        cls.e=read("tcg_official_product_supplement_v649.json")
        cls.jp=read("tcg_official_product_supplement_v654.json")
        cls.old=cls.b["products"]+cls.a["products"]+cls.c["products"]+cls.d["products"]+cls.e["products"]
        cls.all=cls.old+cls.jp["products"]

    def test_91_official_products_54_actual_boxes_and_29_box_region_gaps(self):
        report=audit(self.reg,{"schema_version":1,"products":self.all},
                     as_of=date(2026,10,12))
        self.assertEqual(91,report["reviewed_official_product_records"])
        self.assertEqual(30,report["registry_games"])
        self.assertEqual(55,report["declared_game_country_pairs"])
        self.assertEqual(36,report["pairs_with_any_official_product"])
        self.assertEqual(19,report["game_country_product_coverage_gaps"])
        self.assertEqual(54,sum(row["official_box_count"] for row in report["cells"]))
        self.assertEqual(26,sum(bool(row["official_box_count"]) and row["region_declared"]
                                for row in report["cells"]))
        self.assertEqual(29,sum(not row["official_box_count"] and row["region_declared"]
                                for row in report["cells"]))
        self.assertEqual(90,len(report["cells"]))

    def test_regional_variant_and_msrp_are_specific_to_manufacturer(self):
        self.assertEqual(3,len(self.jp["products"]))
        self.assertEqual("tcg_official_product_supplement_v649.json",self.jp["append_after"])
        by_game={p["game"]:p for p in self.jp["products"]}
        self.assertEqual(("2026-10-09",16,"7",6160),
                         (by_game["Cardfight!! Vanguard"]["release_date"],
                          by_game["Cardfight!! Vanguard"]["packs_per_box"],
                          by_game["Cardfight!! Vanguard"]["cards_per_pack"],
                          by_game["Cardfight!! Vanguard"]["msrp"]["amount"]))
        self.assertEqual(("2025-04-19",24,"6"),
                         (by_game["Digimon Card Game"]["release_date"],
                          by_game["Digimon Card Game"]["packs_per_box"],
                          by_game["Digimon Card Game"]["cards_per_pack"]))
        self.assertEqual(("2024-04-27",30,"5"),
                         (by_game["Yu-Gi-Oh!"]["release_date"],
                          by_game["Yu-Gi-Oh!"]["packs_per_box"],
                          by_game["Yu-Gi-Oh!"]["cards_per_pack"]))
        self.assertTrue(all(p["country"]=="JP" and p["product_type"]=="BOX"
                            for p in self.jp["products"]))
        self.assertTrue(all("market_price" not in p and "pull_rate" not in p
                            for p in self.jp["products"]))

    def test_py_offline_audit_appends_jp_proof_while_old_signature_still_works(self):
        updated=plan(self.reg,self.intake,self.b,self.a,self.c,self.d,self.e,self.jp)
        self.assertEqual((91,54,29,19),(updated["official_product_samples"],
                          updated["official_sealed_box_samples"],
                          updated["declared_sealed_box_spec_gaps"],
                          updated["declared_official_sample_gaps"]))
        old=plan(self.reg,self.intake,self.b,self.a,self.c,self.d,self.e)
        self.assertEqual((88,51,32),(old["official_product_samples"],
                        old["official_sealed_box_samples"],
                        old["declared_sealed_box_spec_gaps"]))
        self.assertEqual((198,42,60,38),(updated["product_candidate_count"],
                         updated["upcoming_candidate_count"],
                         updated["hit_candidate_count"],updated["promo_candidate_count"]))
        tamper=copy.deepcopy(self.jp);tamper["append_after"]="WRONG"
        with self.assertRaisesRegex(ValueError,"INVALID_V654_SUPPLEMENT"):
            plan(self.reg,self.intake,self.b,self.a,self.c,self.d,self.e,tamper)
        fake=copy.deepcopy(self.all);fake[-1]["source"]="https://yu-gi-oh.jp.attacker.example/news"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_OR_UNMATCHED_OFFICIAL_SOURCE"):
            audit(self.reg,{"schema_version":1,"products":fake})

    @unittest.skipUnless(NODE,"Node unavailable")
    def test_browser_91_official_and_29_box_gaps_without_false_promotion(self):
        js=r"""
const assert=require('node:assert/strict');
const registry=require('./tcg_game_registry.json');
const intake=require('./tcg_user_research_intake_v625.json');
const base=require('./tcg_official_product_catalog_v599.json');
const a=require('./tcg_official_product_supplement_v630.json');
const b=require('./tcg_official_product_supplement_v636.json');
const c=require('./tcg_official_product_supplement_v637.json');
const d=require('./tcg_official_product_supplement_v649.json');
const e=require('./tcg_official_product_supplement_v654.json');
const history=require('./tcg_region_lifecycle_v653.json');
const official=require('./official_box_catalog_v626.js');
const research=require('./tcg_source_research_v634.js');
const radar=require('./tcg_coverage_radar_v652.js');
const all=[...base.products,...a.products,...b.products,...c.products,...d.products,...e.products];
assert.equal(official.normalizeProducts({schema_version:1,products:all}).length,91);
assert.equal(research.build(registry,intake,base,a,b,c,d,e).summary.boxMissing,29);
const result=radar.build(registry,intake,base,a,b,c,d,
                        {research,official},history,e);
assert.equal(result.declared_box_gaps,29);
assert.equal(result.currently_prioritized_box_gaps,28);
assert.equal(result.official_product_samples,91);
assert.equal(result.official_box_samples,54);
assert.equal(result.manual_search_tasks,540);
const old=radar.build(registry,intake,base,a,b,c,d,{research,official},history);
assert.equal(old.official_product_samples,88);
assert.equal(old.declared_box_gaps,32);
const fake=structuredClone(e);fake.products[0].source='https://cf-vanguard.com.attacker.example/fake';
assert.throws(()=>research.build(registry,intake,base,a,b,c,d,fake),/UNTRUSTED_V654_PRODUCT/);
"""
        result=subprocess.run([NODE,"-e",js],cwd=ROOT,capture_output=True,
                              text=True,check=False,timeout=30)
        self.assertEqual(0,result.returncode,result.stderr)

if __name__=="__main__":
    unittest.main(verbosity=2)
