#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V649 30/30 manufacturer product rows and legitimate sealed BOX coverage."""
import copy
import json
from datetime import date
from pathlib import Path
import shutil
import subprocess
import unittest

from execution.official_box_coverage_audit_v623 import audit, CoverageError
from tcg_source_audit_v633 import plan
import tcg_multi_source_queue_v639 as queue

ROOT=Path(__file__).resolve().parent
NODE=shutil.which("node")


class OfficialFull30ProductSamplesV649(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        read=lambda name:json.loads((ROOT/name).read_text(encoding="utf-8"))
        cls.registry=read("tcg_game_registry.json")
        cls.leads=read("tcg_user_research_intake_v625.json")
        cls.base=read("tcg_official_product_catalog_v599.json")
        cls.a=read("tcg_official_product_supplement_v630.json")
        cls.b=read("tcg_official_product_supplement_v636.json")
        cls.c=read("tcg_official_product_supplement_v637.json")
        cls.d=read("tcg_official_product_supplement_v649.json")
        cls.products=cls.base["products"]+cls.a["products"]+cls.b["products"]+cls.c["products"]+cls.d["products"]

    def test_registry_all_30_manufacturer_samples_and_remaining_box_gaps(self):
        report=audit(self.registry,{"schema_version":1,"products":self.products},
                     as_of=date(2026,10,12))
        self.assertEqual(88,report["reviewed_official_product_records"])
        self.assertEqual(30,report["registry_games"])
        self.assertEqual(55,report["declared_game_country_pairs"])
        self.assertEqual(33,report["pairs_with_any_official_product"])
        self.assertEqual(22,report["game_country_product_coverage_gaps"])
        self.assertEqual(51,sum(r["official_box_count"] for r in report["cells"]))
        self.assertEqual(23,sum(r["region_declared"] and r["official_box_count"]>0 for r in report["cells"]))
        self.assertEqual(32,sum(r["region_declared"] and not r["official_box_count"] for r in report["cells"]))
        self.assertEqual(30,len({r["game"] for r in self.products}))
        self.assertEqual(30,len(self.registry["games"]))
        self.assertEqual(90,len(report["cells"]))

    def test_no_free_api_paid_costs_or_mixed_regional_box_claims(self):
        self.assertEqual(12,len(self.d["products"]))
        self.assertEqual("tcg_official_product_supplement_v637.json",self.d["append_after"])
        for p in self.d["products"]:
            self.assertIn(p["country"],("KR","JP","US"))
            self.assertIn(p["product_type"],("BOX","BOOSTER_PACK"))
            self.assertNotIn("pull_rate",p)
            self.assertNotIn("verified_sales",p)
            self.assertNotIn("market_price",p)
            self.assertNotIn("verified_stock",p)
            self.assertTrue(p["source"].startswith("https://"))
            if not p.get("release_date"):
                self.assertTrue(p.get("release_date_unverified"),p["id"])
                self.assertTrue(p.get("source_checked_at"),p["id"])
            if p["product_type"]=="BOOSTER_PACK":
                self.assertNotIn("packs_per_box",p)
        cookie=[p for p in self.d["products"] if p["game"]=="CookieRun: Braverse TCG"]
        self.assertEqual(2,len(cookie))
        self.assertTrue(all(p["country"]=="US" and p["cards_per_pack"]=="9" for p in cookie))
        self.assertTrue(all(p["product_type"]=="BOOSTER_PACK" for p in cookie))
        self.assertEqual(32,next(p["packs_per_box"] for p in self.d["products"] if p["game"]=="Alpha Clash"))
        self.assertEqual(14,next(p["packs_per_box"] for p in self.d["products"] if p["game"]=="WIXOSS"))

    def test_offline_audit_reports_counts_and_keeps_original_338_names(self):
        report=plan(self.registry,self.leads,self.base,self.a,self.b,self.c,self.d)
        self.assertEqual((30,90,55,88,51,22,32),(
            report["games"],report["market_search_scopes"],report["declared_scopes"],
            report["official_product_samples"],report["official_sealed_box_samples"],
            report["declared_official_sample_gaps"],report["declared_sealed_box_spec_gaps"]))
        self.assertEqual((198,42,60,38),(
            report["product_candidate_count"],report["upcoming_candidate_count"],
            report["hit_candidate_count"],report["promo_candidate_count"]))
        self.assertEqual(90,len(report["scopes"]))
        self.assertTrue(all(x["price_evidence"]=="NONE" for x in report["scopes"]))

    def test_tampered_manufacturer_domain_or_duplicate_product_fails_closed(self):
        modified=copy.deepcopy(self.products)
        modified[-1]["source"]="https://cyberpunktcg.com.attacker.example/pack"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_OR_UNMATCHED_OFFICIAL_SOURCE"):
            audit(self.registry,{"schema_version":1,"products":modified})
        modified=copy.deepcopy(self.products)
        modified[-1]["id"]=modified[0]["id"]
        with self.assertRaisesRegex(CoverageError,"DUPLICATE_OFFICIAL_PRODUCT_ID"):
            audit(self.registry,{"schema_version":1,"products":modified})
        wrong=copy.deepcopy(self.d)
        wrong["append_after"]="WRONG"
        with self.assertRaisesRegex(ValueError,"INVALID_V649_SUPPLEMENT"):
            plan(self.registry,self.leads,self.base,self.a,self.b,self.c,wrong)

    def test_no_candidate_loss_queue_all_1014(self):
        result=queue.build_queue()
        self.assertEqual(1014,result["summary"]["jobs_returned"])
        self.assertEqual(1014,len({row["task_id"] for row in result["jobs"]}))
        self.assertEqual(30,len({row["game_id"] for row in result["jobs"]}))
        self.assertEqual(0,result["summary"]["network_calls"])
        self.assertTrue(all(row["price_kind"]=="NONE" for row in result["jobs"]))

    @unittest.skipUnless(NODE,"Node.js unavailable")
    def test_js_official_88_and_original_76_backward_compatibility(self):
        code=r"""
const assert=require('node:assert/strict');
const reg=require('./tcg_game_registry.json');
const intake=require('./tcg_user_research_intake_v625.json');
const a=require('./tcg_official_product_catalog_v599.json');
const b=require('./tcg_official_product_supplement_v630.json');
const c=require('./tcg_official_product_supplement_v636.json');
const d=require('./tcg_official_product_supplement_v637.json');
const e=require('./tcg_official_product_supplement_v649.json');
const viewer=require('./official_box_catalog_v626.js');
const app=require('./tcg_source_research_v634.js');
const routes=require('./tcg_source_routes_v633.js');
const all=[...a.products,...b.products,...c.products,...d.products,...e.products];
assert.equal(all.length,88);
assert.equal(viewer.normalizeProducts({schema_version:1,products:all}).length,88);
const newReport=app.build(reg,intake,a,b,c,d,e);
assert.deepEqual(newReport.summary,{games:30,searchScopes:90,declared:55,
 missing:22,boxMissing:32,officialBoxes:51,official:88,
 product:198,upcoming:42,hit:60,promo:38});
assert.equal(app.filtered(newReport.scopes,{priority:'BOX_MISSING'}).length,32);
assert.equal(app.filtered(newReport.scopes,{priority:'MISSING'}).length,22);
const old=app.build(reg,intake,a,b,c,d);
assert.equal(old.summary.official,76);
assert.equal(old.summary.boxMissing,38);
for(const p of all){
 assert.ok(viewer.validProduct(p),p.id);
 assert.ok(routes.sourceRoutes(p,reg).officialIndex,p.id);
}
const malformed=structuredClone(e);malformed.append_after='WRONG';
assert.throws(()=>app.build(reg,intake,a,b,c,d,malformed),/INVALID_V649_SUPPLEMENT/);
"""
        p=subprocess.run([NODE,"-e",code],cwd=ROOT,text=True,
                         capture_output=True,check=False,timeout=30)
        self.assertEqual(0,p.returncode,p.stdout+"\n"+p.stderr)

    @unittest.skipUnless(NODE,"Node.js unavailable")
    def test_node_parse_four_browser_surfaces(self):
        for file in ("official_box_catalog_v626.js","tcg_30_game_catalog_v629.js",
                     "tcg_source_research_v634.js","tcg_event_intelligence_v646.js"):
            with self.subTest(file=file):
                p=subprocess.run([NODE,"--check",file],cwd=ROOT,
                                 capture_output=True,text=True,check=False,timeout=12)
                self.assertEqual(0,p.returncode,p.stderr)


if __name__=="__main__":
    unittest.main(verbosity=2)
