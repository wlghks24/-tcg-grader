#!/usr/bin/env python3
"""V630 offline supplemental official BOX proofs and risk-aware competitor features."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from execution.official_box_coverage_audit_v623 import audit, CoverageError

ROOT = Path(__file__).resolve().parent
NODE = shutil.which("node")


class OfficialSupplementV630(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=json.loads((ROOT/"tcg_game_registry.json").read_text(encoding="utf-8"))
        cls.base=json.loads((ROOT/"tcg_official_product_catalog_v599.json").read_text(encoding="utf-8"))
        cls.extra=json.loads((ROOT/"tcg_official_product_supplement_v630.json").read_text(encoding="utf-8"))
        cls.merged={"schema_version":1,"products":cls.base["products"]+cls.extra["products"]}

    def test_supplement_keeps_user_30_and_reviewed_v599_untouched(self):
        self.assertEqual(30,len(self.registry["games"]))
        self.assertEqual(58,len(self.base["products"]))
        self.assertEqual(5,len(self.extra["products"]))
        self.assertEqual("tcg_official_product_catalog_v599.json",self.extra["base_catalog"])
        self.assertEqual(63,len(self.merged["products"]))
        self.assertEqual(len({p["id"] for p in self.merged["products"]}),63)

    def test_original_and_supplement_combined_pass_official_audit(self):
        result=audit(self.registry,self.merged)
        self.assertEqual(30,result["registry_games"])
        self.assertEqual(63,result["reviewed_official_product_records"])
        self.assertEqual(55,result["declared_game_country_pairs"])
        self.assertEqual(19,result["pairs_with_any_official_product"])
        self.assertEqual(36,result["game_country_product_coverage_gaps"])
        self.assertEqual(17,len({p["game"] for p in self.merged["products"]}))
        self.assertEqual(90,len(result["cells"]))
        self.assertTrue(all("HIT_IDENTITY" in c["noncatalog_evidence_not_audited"] for c in result["cells"]))

    def test_JP_US_box_pack_counts_and_currency_never_mixed(self):
        by_id={p["id"]:p for p in self.extra["products"]}
        self.assertEqual((24,"15",119.90,"USD","2025-09-26"),
                         (by_id["fab-SUP-US-EN"]["packs_per_box"],by_id["fab-SUP-US-EN"]["cards_per_pack"],by_id["fab-SUP-US-EN"]["msrp"]["amount"],by_id["fab-SUP-US-EN"]["msrp"]["currency"],by_id["fab-SUP-US-EN"]["release_date"]))
        self.assertEqual((24,"9",5760,"JPY","2025-09-19"),
                         (by_id["fab-SUP-JP-JA"]["packs_per_box"],by_id["fab-SUP-JP-JA"]["cards_per_pack"],by_id["fab-SUP-JP-JA"]["msrp"]["amount"],by_id["fab-SUP-JP-JA"]["msrp"]["currency"],by_id["fab-SUP-JP-JA"]["release_date"]))
        self.assertEqual((18,"12"),(by_id["ff-BLISSFUL-US-2026"]["packs_per_box"],by_id["ff-BLISSFUL-US-2026"]["cards_per_pack"]))
        self.assertFalse(by_id["ff-BLISSFUL-US-2026"]["set_code_verified"])
        self.assertEqual((16,"7"),(by_id["vg-DZ-BT14-US"]["packs_per_box"],by_id["vg-DZ-BT14-US"]["cards_per_pack"]))
        self.assertEqual((16,"7"),(by_id["vg-DZ-BT16-US"]["packs_per_box"],by_id["vg-DZ-BT16-US"]["cards_per_pack"]))
        self.assertTrue(all(not any(k in row for k in ("market_price","verified_sales","verified_stock","pull_rate","psa_grade")) for row in self.extra["products"]))

    def test_pretend_manufacturer_phishing_or_fabricated_msrp_is_rejected(self):
        fake=copy.deepcopy(self.merged)
        next(p for p in fake["products"] if p["id"]=="fab-SUP-US-EN")["source"]="https://fabtcg.com.attacker.example/en/"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_OR_UNMATCHED_OFFICIAL_SOURCE"): audit(self.registry,fake)
        fake=copy.deepcopy(self.merged)
        next(p for p in fake["products"] if p["id"]=="vg-DZ-BT14-US")["msrp"]={"currency":"JPY","amount":1,"unit":"BOX"}
        with self.assertRaisesRegex(CoverageError,"INVALID_MSRP_CURRENCY_OR_UNIT"): audit(self.registry,fake)

    @unittest.skipUnless(NODE,"Node.js not installed")
    def test_browser_validates_all_63_and_new_makers_without_paid_api(self):
        script=r"""
const assert=require('node:assert/strict');
const ui=require('./official_box_catalog_v626.js');
const base=require('./tcg_official_product_catalog_v599.json');
const extra=require('./tcg_official_product_supplement_v630.json');
const all=ui.normalizeProducts({schema_version:1,products:base.products.concat(extra.products)});
assert.equal(all.length,63);
assert.equal(new Set(all.map(x=>x.game)).size,17);
for(const p of extra.products){assert.equal(ui.validProduct(p),true,p.id);assert.equal(ui.trustedSource(p.source,p.game),true);}
assert.equal(ui.trustedSource('https://fabtcg.com.evil.test/page','Flesh and Blood TCG'),false);
assert.equal(ui.filterProducts(all,{game:'Flesh and Blood TCG'}).length,2);
assert.equal(ui.filterProducts(all,{country:'JP',kind:'BOX'}).filter(x=>x.game==='Flesh and Blood TCG').length,1);
assert.equal(ui.filterProducts(all,{search:'Blissful Eternity'}).length,1);
assert.equal(ui.paginate(all,5,12).rows.length,3);
assert.match(ui.formatPrice(extra.products.find(x=>x.country==='JP').msrp),/¥5,760/);
"""
        r=subprocess.run([NODE,"-e",script],cwd=ROOT,capture_output=True,text=True,timeout=20,check=False)
        self.assertEqual(r.returncode,0,r.stdout+"\n"+r.stderr)

    def test_html_and_js_load_supplement_without_external_account(self):
        script=(ROOT/"official_box_catalog_v626.js").read_text(encoding="utf-8")
        html=(ROOT/"official_box_catalog_v626.html").read_text(encoding="utf-8")
        self.assertIn("tcg_official_product_supplement_v630.json",script)
        self.assertIn("추가 제조사 자료 로드 실패",script)
        self.assertNotIn(".innerHTML",script)
        self.assertIn("Content-Security-Policy",html)

if __name__=="__main__":unittest.main(verbosity=2)
