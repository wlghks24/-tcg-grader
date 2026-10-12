#!/usr/bin/env python3
"""V638: count genuine sealed BOX evidence independently from pack samples.

Uses local snapshots only, standard library + optional Node runtime.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from execution.official_box_coverage_audit_v623 import audit, CoverageError
from tcg_source_audit_v633 import plan, classify, manufacturer_search

ROOT=Path(__file__).resolve().parent
NODE=shutil.which("node")


class Full30SealedBoxTruthV638(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        read=lambda name:json.loads((ROOT/name).read_text(encoding="utf-8"))
        cls.reg=read("tcg_game_registry.json")
        cls.intake=read("tcg_user_research_intake_v625.json")
        cls.base=read("tcg_official_product_catalog_v599.json")
        cls.old=read("tcg_official_product_supplement_v630.json")
        cls.v636=read("tcg_official_product_supplement_v636.json")
        cls.v637=read("tcg_official_product_supplement_v637.json")
        cls.products=(cls.base["products"]+cls.old["products"]+
                      cls.v636["products"]+cls.v637["products"])

    def test_76_products_42_boxes_22_games_55_regions_and_real_38_box_gaps(self):
        audited=audit(self.reg,{"schema_version":1,"products":self.products})
        self.assertEqual(76,len(self.products))
        self.assertEqual(22,len({p["game"] for p in self.products}))
        self.assertEqual(76,audited["reviewed_official_product_records"])
        self.assertEqual(55,audited["declared_game_country_pairs"])
        self.assertEqual(25,audited["pairs_with_any_official_product"])
        self.assertEqual(30,audited["game_country_product_coverage_gaps"])
        self.assertEqual(90,len(audited["cells"]))
        self.assertEqual(17,sum(x["region_declared"] and x["official_box_count"]>0 for x in audited["cells"]))
        self.assertEqual(38,sum(x["region_declared"] and not x["official_box_count"] for x in audited["cells"]))
        self.assertEqual(42,sum(p["product_type"]=="BOX" for p in self.products))
        self.assertEqual(8,sum(x["region_declared"] and x["official_product_count"]>0
                               and x["official_box_count"]==0 for x in audited["cells"]))

    def test_offline_plan_carries_separate_sealed_box_counters(self):
        d=plan(self.reg,self.intake,self.base,self.old,self.v636,self.v637)
        self.assertEqual((30,90,55,76,42,30,38),(
            d["games"],d["market_search_scopes"],d["declared_scopes"],
            d["official_product_samples"],d["official_sealed_box_samples"],
            d["declared_official_sample_gaps"],d["declared_sealed_box_spec_gaps"]))
        self.assertEqual(198,d["product_candidate_count"])
        self.assertEqual(42,d["upcoming_candidate_count"])
        self.assertEqual(60,d["hit_candidate_count"])
        self.assertEqual(38,d["promo_candidate_count"])
        self.assertTrue(all(x["price_evidence"]=="NONE" for x in d["scopes"]))
        self.assertEqual(38,sum(x["sealed_box_status"]=="BOX_SPEC_SAMPLE_MISSING" for x in d["scopes"]))

    def test_manufacturer_domain_and_unknown_dates_not_invented(self):
        rows={x["id"]:x for x in self.v637["products"]}
        self.assertEqual(5,len(rows))
        self.assertTrue(all(x["country"]=="US" for x in rows.values()))
        self.assertEqual((24,"15",129),(
            rows["sorc-US-ARTHURIAN-LEGENDS"]["packs_per_box"],
            rows["sorc-US-ARTHURIAN-LEGENDS"]["cards_per_pack"],
            rows["sorc-US-ARTHURIAN-LEGENDS"]["msrp"]["amount"]))
        for name in ("rift-US-ORIGINS-EN","rift-US-UNLEASHED-EN",
                     "rift-US-RADIANCE-EN","sorc-US-ARTHURIAN-LEGENDS"):
            self.assertNotIn("release_date",rows[name])
            self.assertIs(rows[name]["release_date_unverified"],True)
            self.assertEqual("2026-10-12",rows[name]["source_checked_at"])
        self.assertEqual("2026-04-03",rows["ga-US-RADIANT-ORIGINS-2026"]["release_date"])
        for item in rows.values():
            self.assertEqual("BOX",item["product_type"])
            self.assertNotIn("pull_rate",item)
            self.assertNotIn("market_price",item)

    def test_original_region_and_user_candidate_count_preserved(self):
        self.assertEqual(30,len(self.intake["records"]))
        self.assertEqual(30,len({x["id"] for x in self.reg["games"]}))
        self.assertEqual(198,sum(len(x["product_name_candidates"]) for x in self.intake["records"]))
        self.assertEqual(35,len([1 for g in self.reg["games"] for c in ("KR","JP","US")
                                 if c not in g["regions"] and "GLOBAL" not in g["regions"]]))

    def test_unsafe_manufacturer_variant_does_not_pass_official_audit(self):
        import copy
        corrupted=copy.deepcopy(self.products)
        corrupted[-1]["source"]="https://sorcerytcg.com.attacker.example/fake"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_OR_UNMATCHED_OFFICIAL_SOURCE"):
            audit(self.reg,{"schema_version":1,"products":corrupted})
        self.assertEqual("BROKEN_LINK_REVIEW",classify(404))
        self.assertEqual("RATE_LIMIT_PAUSE",classify(429))
        self.assertEqual("TEMPORARY_FAILURE",classify(503))
        self.assertTrue(manufacturer_search("https://sorcerytcg.com/product/arthurian-legends",
                                            "Arthurian Legends",engine="bing")
                        .startswith("https://www.bing.com/search?"))

    @unittest.skipUnless(NODE,"Node.js absent")
    def test_js_box_filters_76_records_all_30_and_search_recovery(self):
        code=r"""
const assert=require('node:assert/strict');
const reg=require('./tcg_game_registry.json');
const intake=require('./tcg_user_research_intake_v625.json');
const a=require('./tcg_official_product_catalog_v599.json');
const b=require('./tcg_official_product_supplement_v630.json');
const c=require('./tcg_official_product_supplement_v636.json');
const d=require('./tcg_official_product_supplement_v637.json');
const viewer=require('./official_box_catalog_v626.js');
const app=require('./tcg_source_research_v634.js');
const routes=require('./tcg_source_routes_v633.js');
const all=[...a.products,...b.products,...c.products,...d.products];
assert.equal(viewer.normalizeProducts({schema_version:1,products:all}).length,76);
const report=app.build(reg,intake,a,b,c,d);
assert.deepEqual(report.summary,{games:30,searchScopes:90,declared:55,
 missing:30,boxMissing:38,officialBoxes:42,official:76,
 product:198,upcoming:42,hit:60,promo:38});
assert.equal(app.filtered(report.scopes,{priority:'BOX_MISSING'}).length,38);
assert.equal(app.filtered(report.scopes,{priority:'MISSING'}).length,30);
assert.equal(app.filtered(report.scopes,{priority:'EXPLORATORY'}).length,35);
assert.equal(app.filtered(report.scopes,{game:'sorcery-contested-realm'}).length,3);
assert.equal(app.filtered(report.scopes,{game:'riftbound'}).length,3);
for(const p of all){
 const r=routes.sourceRoutes(p,reg);
 assert.ok(r&&r.officialIndex&&r.manufacturerSiteSearch&&r.alternateSiteSearch,p.id);
}
const fake=JSON.parse(JSON.stringify(d));fake.append_after='WRONG';
assert.throws(()=>app.build(reg,intake,a,b,c,fake));
"""
        p=subprocess.run([NODE,"-e",code],cwd=ROOT,text=True,
                         capture_output=True,check=False,timeout=25)
        self.assertEqual(0,p.returncode,p.stdout+"\n"+p.stderr)

    @unittest.skipUnless(NODE,"Node.js absent")
    def test_node_syntax_latest(self):
        for filename in ("official_box_catalog_v626.js","tcg_30_game_catalog_v629.js",
                         "tcg_source_research_v634.js","tcg_source_routes_v633.js"):
            with self.subTest(filename=filename):
                p=subprocess.run([NODE,"--check",filename],cwd=ROOT,
                                 text=True,capture_output=True,check=False,timeout=15)
                self.assertEqual(0,p.returncode,p.stderr)


if __name__=="__main__":
    unittest.main(verbosity=2)
