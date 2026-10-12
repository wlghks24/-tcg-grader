#!/usr/bin/env python3
"""V658: same 3 authenticated sealed BOX sources across Python queue/audit and JS tablet."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from execution.official_box_coverage_audit_v623 import ROOT, CoverageError
from tcg_official_overlay_v657 import validate_overlay
from tcg_multi_source_queue_v639 import build_queue
from tcg_source_audit_v633 import plan

NODE = shutil.which("node")
def read(name):
    return json.loads((ROOT/name).read_text(encoding="utf-8"))

class V658SourceAlignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = read("tcg_game_registry.json")
        cls.intake = read("tcg_user_research_intake_v625.json")
        cls.b = read("tcg_official_product_catalog_v599.json")
        cls.parts = [read("tcg_official_product_supplement_v%s.json" % n)
                     for n in ("630","636","637","649","654","657")]

    def test_30_games_all_candidate_records_remain_and_8_free_links(self):
        report = build_queue()
        self.assertEqual(1014, len(report["jobs"]))
        self.assertEqual(30, report["summary"]["games_in_registry"])
        self.assertEqual(338, report["summary"]["original_candidate_records"])
        self.assertEqual(0, report["summary"]["network_calls"])
        self.assertEqual(0, report["summary"]["free_paid_dependencies"])
        self.assertEqual(8, report["summary"]["research_links_per_job"])
        self.assertTrue(all(len(j["search_links"]) == 8 for j in report["jobs"]))
        self.assertTrue(all(j["manufacturer_approved"] is False
                            and j["price_kind"] == "NONE" for j in report["jobs"]))
        for game_id in ("lorcana", "digimon", "swu"):
            rows = [j for j in report["jobs"] if j["game_id"] == game_id
                    and j["market"] == "US"]
            self.assertTrue(rows)
            self.assertTrue(all(j["official_box_samples_in_scope"] > 0 for j in rows))

    def test_python_source_audit_94_57_26_and_old_91_fallback(self):
        parts = self.parts
        old = plan(self.registry, self.intake, self.b, *parts[:5])
        new = plan(self.registry, self.intake, self.b, *parts)
        self.assertEqual((91,54,29), (old["official_product_samples"],
                         old["official_sealed_box_samples"],
                         old["declared_sealed_box_spec_gaps"]))
        self.assertEqual((94,57,26), (new["official_product_samples"],
                         new["official_sealed_box_samples"],
                         new["declared_sealed_box_spec_gaps"]))
        self.assertEqual(55, new["declared_scopes"])
        self.assertTrue(all(row["price_evidence"] == "NONE" for row in new["scopes"]))

    def test_manufacturer_overlay_never_accepts_fake_data(self):
        document = copy.deepcopy(self.parts[-1])
        self.assertEqual(3, len(validate_overlay(document, self.registry)))
        altered = copy.deepcopy(document)
        altered["products"][0]["source"] = "https://www.disneylorcana.com.attacker.test/"
        with self.assertRaisesRegex(CoverageError, "UNTRUSTED_V657_BOX_OR_LOCALE"):
            validate_overlay(altered, self.registry)
        altered = copy.deepcopy(document)
        altered["products"][1]["release_date"] = "2030-01-01"
        with self.assertRaisesRegex(CoverageError, "UNTRUSTED_V657_IDENTITY"):
            validate_overlay(altered, self.registry)

    def test_modified_file_sha256_integrity(self):
        manifest = read("integrity_manifest.json")["files"]
        for filename in (
            "tcg_multi_source_queue_v639.py", "tcg_source_audit_v633.py",
            "tcg_official_overlay_v657.py", "official_box_catalog_v626.js",
            "tcg_source_research_v634.js", "tcg_source_research_v634.html",
            "tcg_coverage_radar_v652.js", "tcg_30_game_catalog_v629.js",
            "test_tcg_official_overlay_v657.py", "test_tcg_v658_alignment.py",
            ".github/workflows/tcg-free-collector-qa.yml",
            ".github/workflows/tcg-codeql-qa.yml",
            "execution/official_box_coverage_audit_v623.py",
            "tcg_official_product_supplement_v659.json",
            "tcg_official_overlay_v659.py",
            "tcg_manufacturer_card_evidence_v660.json",
            "tcg_card_trade_evidence_v660.py",
            "test_tcg_v659_v660.py",
            "tcg_tcgdex_card_ids_v661.py",
            "test_tcg_tcgdex_card_ids_v661.py",
            "tcg_official_product_supplement_v662.json",
            "tcg_official_overlay_v662.py",
            "test_tcg_v662_official_box.py",
            "tcg_official_product_supplement_v663.json",
            "tcg_official_promo_evidence_v663.json",
            "tcg_official_overlay_v663.py",
            "test_tcg_v663_pokemon_us.py",
            "tcg_free_preflight_v664.py",
            "tcg_official_product_supplement_v665.json",
            "tcg_official_overlay_v665.py",
            "test_tcg_v665_box_and_proof_security.py",
            "tcg_manufacturer_card_evidence_v666.json",
            "tcg_country_pack_discrepancy_v666.json",
            "tcg_manufacturer_card_overlay_v666.py",
            "test_tcg_v666_card_locale_evidence.py",
            "tcg_official_product_supplement_v667.json",
            "tcg_official_overlay_v667.py",
            "test_tcg_v667_ff_jp_boxes.py",
            "tcg_tcgdex_sets_v640.py",
            "test_tcg_event_rss_v647.py",
        ):
            with self.subTest(file=filename):
                blob = (ROOT / filename).read_bytes()
                self.assertEqual(len(blob), manifest[filename]["bytes"])
                self.assertEqual(hashlib.sha256(blob).hexdigest(),
                                 manifest[filename]["sha256"])

    @unittest.skipUnless(NODE, "Node.js unavailable")
    def test_javascript_all_tablet_counts_and_spoof_defense(self):
        js = r"""
const assert=require('node:assert/strict');
const official=require('./official_box_catalog_v626.js');
const research=require('./tcg_source_research_v634.js');
const radar=require('./tcg_coverage_radar_v652.js');
const gameUI=require('./tcg_30_game_catalog_v629.js');
const reg=require('./tcg_game_registry.json');
const intake=require('./tcg_user_research_intake_v625.json');
const base=require('./tcg_official_product_catalog_v599.json');
const filenames=['630','636','637','649','654','657'];
const parts=filenames.map(n=>require('./tcg_official_product_supplement_v'+n+'.json'));
const history=require('./tcg_region_lifecycle_v653.json');
const before=research.build(reg,intake,base,...parts.slice(0,5));
const after=research.build(reg,intake,base,...parts,official);
assert.equal(before.summary.official,91);
assert.deepEqual([after.summary.official,after.summary.officialBoxes,after.summary.boxMissing],[94,57,26]);
const snapshot=radar.build(reg,intake,base,...parts.slice(0,4),{research,official},history,parts[4],parts[5]);
assert.deepEqual([snapshot.official_product_samples,snapshot.official_box_samples,
 snapshot.declared_box_gaps,snapshot.manual_search_tasks],[94,57,26,540]);
const full=base.products.concat(...parts.map(p=>p.products));
const values=gameUI.officialCounts({schema_version:1,products:full},reg,official);
assert.equal(Object.values(values).reduce((x,y)=>x+y,0),94);
const hostile=structuredClone(parts[5]);
hostile.products[0].source='https://disneylorcana.com.attacker.example/box';
assert.throws(()=>research.build(reg,intake,base,...parts.slice(0,5),hostile,official),/UNTRUSTED_V657_PRODUCT/);
assert.throws(()=>radar.build(reg,intake,base,...parts.slice(0,4),{research,official},history,parts[4],hostile),
 /UNTRUSTED_V657_PRODUCT/);
const html=require('node:fs').readFileSync('tcg_source_research_v634.html','utf8');
assert.ok(html.indexOf('official_box_catalog_v626.js')<html.indexOf('tcg_source_research_v634.js'));
assert.ok(require('node:fs').readFileSync('tcg_coverage_radar_v652.js','utf8')
 .includes('tcg_official_product_supplement_v657.json'));
assert.ok(require('node:fs').readFileSync('official_box_catalog_v626.js','utf8')
 .includes('tcg_official_product_supplement_v657.json'));
"""
        test = subprocess.run([NODE,"-e",js],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(0,test.returncode,test.stderr)

if __name__ == "__main__":
    unittest.main(verbosity=2)
