#!/usr/bin/env python3
"""V636: provenance-aware sealed BOX expansion and multi-region fallback regression."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from execution.official_box_coverage_audit_v623 import audit, CoverageError
from tcg_source_audit_v633 import plan

ROOT=Path(__file__).resolve().parent
NODE=shutil.which("node")


class OfficialRegionalAdditionsV636(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def data(name):return json.loads((ROOT/name).read_text(encoding="utf-8"))
        cls.registry=data("tcg_game_registry.json")
        cls.intake=data("tcg_user_research_intake_v625.json")
        cls.baseline=data("tcg_official_product_catalog_v599.json")
        cls.v630=data("tcg_official_product_supplement_v630.json")
        cls.v636=data("tcg_official_product_supplement_v636.json")
        cls.all={"schema_version":1,"products":cls.baseline["products"]+cls.v630["products"]+cls.v636["products"]}

    def test_manufacturer_records_71_and_gaps_33_without_deleting_30_inputs(self):
        report=audit(self.registry,self.all)
        self.assertEqual(8,len(self.v636["products"]))
        self.assertEqual(71,len(self.all["products"]))
        self.assertEqual(71,report["reviewed_official_product_records"])
        self.assertEqual(30,report["registry_games"])
        self.assertEqual(55,report["declared_game_country_pairs"])
        self.assertEqual(22,report["pairs_with_any_official_product"])
        self.assertEqual(33,report["game_country_product_coverage_gaps"])
        self.assertEqual(19,len({p["game"] for p in self.all["products"]}))
        self.assertEqual(90,len(report["cells"]))
        self.assertEqual(30,len(self.intake["records"]))
        self.assertEqual(198,sum(len(r["product_name_candidates"]) for r in self.intake["records"]))
        self.assertEqual(42,sum(len(r["upcoming_name_candidates"]) for r in self.intake["records"]))
        self.assertEqual(60,sum(len(r["hit_name_candidates"]) for r in self.intake["records"]))
        self.assertEqual(38,sum(len(r["promo_name_candidates"]) for r in self.intake["records"]))

    def test_country_and_box_variants_are_not_mixed(self):
        rows={p["id"]:p for p in self.v636["products"]}
        expected={
            "hl-JP-hBP09-2026":("JP",12,"8",5280),
            "hl-JP-SUMMER-2026":("JP",8,"10",5280),
            "hl-JP-GLORY-2026":("JP",12,"8",5280),
            "sv-JP-BP21-2026":("JP",12,"8",5280),
            "sv-JP-BP22-2026":("JP",12,"8",5280),
            "sv-US-BP16-2026":("US",12,"8",None),
            "sv-US-BP17-2026":("US",12,"8",None),
            "sv-US-BP18-2026":("US",12,"8",None)}
        self.assertEqual(set(expected),set(rows))
        for identity,(region,packs,cards,price) in expected.items():
            with self.subTest(product=identity):
                p=rows[identity]
                self.assertEqual((region,packs,cards),(p["country"],p["packs_per_box"],p["cards_per_pack"]))
                self.assertEqual(price,p.get("msrp",{}).get("amount"))
                self.assertEqual("BOX",p["product_type"])
                self.assertTrue(p["source"].startswith("https://"))
                for forbidden in ("market_price","verified_sales","verified_stock","psa_grade","pull_rate"):
                    self.assertNotIn(forbidden,p)
        self.assertTrue(all(x["set_code_verified"] is False for x in rows.values() if x["set_code"].startswith("LOCAL-")))

    def test_all_30_offline_research_includes_new_verified_samples(self):
        report=plan(self.registry,self.intake,self.baseline,self.v630,self.v636)
        self.assertEqual((71,90,55,33),(report["official_product_samples"],
                         report["market_search_scopes"],report["declared_scopes"],
                         report["declared_official_sample_gaps"]))
        self.assertEqual(35,sum(x["priority"]=="P2_EXPLORATORY" for x in report["scopes"]))
        self.assertEqual("NONE",report["scopes"][0]["price_evidence"])

    def test_python_audit_rejects_false_local_code_and_fake_source_domain(self):
        import copy
        corrupted=copy.deepcopy(self.all)
        row=next(p for p in corrupted["products"] if p["id"]=="hl-JP-SUMMER-2026")
        row["set_code_verified"]=True
        with self.assertRaisesRegex(CoverageError,"UNVERIFIED_LOCAL_CODE_MUST_BE_MARKED"):
            audit(self.registry,corrupted)
        corrupted=copy.deepcopy(self.all)
        row=next(p for p in corrupted["products"] if p["id"]=="sv-US-BP16-2026")
        row["source"]="https://en.shadowverse-evolve.com.attacker.example/products/bp16/"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_OR_UNMATCHED_OFFICIAL_SOURCE"):
            audit(self.registry,corrupted)

    @unittest.skipUnless(NODE,"Node.js required")
    def test_71_browser_products_30_game_v636_counts_and_71_manufacturer_routes(self):
        code=r"""
const assert=require('node:assert/strict');
const reg=require('./tcg_game_registry.json');
const intake=require('./tcg_user_research_intake_v625.json');
const base=require('./tcg_official_product_catalog_v599.json');
const v630=require('./tcg_official_product_supplement_v630.json');
const v636=require('./tcg_official_product_supplement_v636.json');
const official=require('./official_box_catalog_v626.js');
const research=require('./tcg_source_research_v634.js');
const routes=require('./tcg_source_routes_v633.js');
const rows=base.products.concat(v630.products,v636.products);
assert.equal(official.normalizeProducts({schema_version:1,products:rows}).length,71);
const report=research.build(reg,intake,base,v630,v636);
assert.deepEqual(report.summary,{games:30,searchScopes:90,declared:55,missing:33,
 boxMissing:41,officialBoxes:37,official:71,product:198,upcoming:42,hit:60,promo:38});
let gathered=[];
for(let i=0;i<15;i++)gathered.push(...research.paginate(report.scopes,i).rows);
assert.equal(gathered.length,90);
for(const product of rows){
 const link=routes.sourceRoutes(product,reg);
 assert.ok(link,product.id);
 assert.ok(link.officialIndex,product.id);
 assert.ok(link.manufacturerSiteSearch,product.id);
 assert.ok(link.alternateSiteSearch,product.id);
}
assert.equal(research.filtered(report.scopes,{priority:'MISSING'}).length,33);
const koreanPokemon=report.scopes.find(x=>x.game.id==='pokemon'&&x.region==='KR');
assert.equal(koreanPokemon.sourceHints[0].includes('pokemoncard.co.kr'),true);
const japanesePokemon=report.scopes.find(x=>x.game.id==='pokemon'&&x.region==='JP');
assert.equal(japanesePokemon.sourceHints[0].includes('pokemon-card.com'),true);
const japaneseHolo=report.scopes.find(x=>x.game.id==='hololive-ocg'&&x.region==='JP');
assert.equal(japaneseHolo.sourceHints.length,3);
const englishShadowverse=report.scopes.find(x=>x.game.id==='shadowverse-evolve'&&x.region==='US');
assert.equal(englishShadowverse.sourceHints.length,3);
assert.equal(official.filterProducts(rows,{game:'hololive OFFICIAL CARD GAME',country:'JP'}).length,3);
assert.equal(official.filterProducts(rows,{game:'Shadowverse: Evolve',country:'US'}).length,3);
"""
        p=subprocess.run([NODE,"-e",code],cwd=ROOT,check=False,capture_output=True,text=True,timeout=25)
        self.assertEqual(0,p.returncode,p.stdout+"\n"+p.stderr)

    def test_source_loader_still_falls_back_on_missing_supplement(self):
        files=("official_box_catalog_v626.js","tcg_30_game_catalog_v629.js",
               "tcg_source_research_v634.js","tcg_source_audit_v633.py")
        for filename in files:
            with self.subTest(filename=filename):
                s=(ROOT/filename).read_text(encoding="utf-8")
                self.assertIn("tcg_official_product_supplement_v636.json",s)
        source=(ROOT/"official_box_catalog_v626.js").read_text(encoding="utf-8")
        self.assertIn("catch (_) { supplementWarning=true; }",source)
        self.assertNotIn(".innerHTML",source)


if __name__=="__main__":unittest.main(verbosity=2)
