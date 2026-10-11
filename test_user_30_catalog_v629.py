#!/usr/bin/env python3
"""V629: 30 user-entered TCG research records are preserved and browsable, never auto-promoted."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
NODE = shutil.which("node")

class UserEntered30IntegrityV629(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = json.loads((ROOT/"tcg_game_registry.json").read_text(encoding="utf-8"))
        cls.intake = json.loads((ROOT/"tcg_user_research_intake_v625.json").read_text(encoding="utf-8"))
        cls.official = json.loads((ROOT/"tcg_official_product_catalog_v599.json").read_text(encoding="utf-8"))

    def test_entire_input_remains_present_not_only_official(self):
        rows = self.intake["records"]
        self.assertEqual(30, len(rows))
        self.assertEqual({g["id"] for g in self.reg["games"]}, {r["game_id"] for r in rows})
        self.assertEqual(198, sum(len(r["product_name_candidates"]) for r in rows))
        self.assertEqual(42, sum(len(r["upcoming_name_candidates"]) for r in rows))
        self.assertEqual(60, sum(len(r["hit_name_candidates"]) for r in rows))
        self.assertEqual(38, sum(len(r["promo_name_candidates"]) for r in rows))
        self.assertEqual(58, len(self.official["products"]))
        self.assertTrue(all(r["status"] == "USER_SUBMITTED_UNVERIFIED" for r in rows))

    def test_candidate_page_is_linked_from_official_page(self):
        html = (ROOT/"tcg_30_game_catalog_v629.html").read_text(encoding="utf-8")
        official = (ROOT/"official_box_catalog_v626.html").read_text(encoding="utf-8")
        self.assertIn("tcg_30_game_catalog_v629.js", html)
        self.assertIn("Content-Security-Policy", html)
        self.assertIn('href="./tcg_30_game_catalog_v629.html"', official)
        self.assertIn("tcg_user_research_intake_v625.json", html)
        for id_ in ("user30App", "user30Game", "user30Search", "user30Results",
                    "user30Summary", "user30Prev", "user30Next", "user30Page"):
            self.assertIn('id="' + id_ + '"', html)

    def test_script_does_not_auto_certify_candidates(self):
        js = (ROOT/"tcg_30_game_catalog_v629.js").read_text(encoding="utf-8")
        self.assertNotIn(".innerHTML", js)
        self.assertNotIn("localStorage", js)
        self.assertNotIn("market_prices.json", js)
        self.assertIn("USER_SUBMITTED_UNVERIFIED", js)
        self.assertIn("textContent", js)
        self.assertIn('fetch(path, { cache: "no-store" })', js)

    @unittest.skipUnless(NODE, "Node not installed")
    def test_js_filter_search_pagination_and_safe_evidence_separation(self):
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const api = require('./tcg_30_game_catalog_v629.js');
const intake = JSON.parse(fs.readFileSync('./tcg_user_research_intake_v625.json','utf8'));
const reg = JSON.parse(fs.readFileSync('./tcg_game_registry.json','utf8'));
const official = JSON.parse(fs.readFileSync('./tcg_official_product_catalog_v599.json','utf8'));
assert.equal(api.validIntake(intake,reg),true);
assert.deepEqual(api.counts(intake.records),{games:30,product:198,upcoming:42,hit:60,promo:38});
const refs=api.officialCounts(official,reg);
assert.equal(Object.values(refs).reduce((a,b)=>a+b,0),58);
assert.equal(refs.pokemon,10);
assert.equal(refs.naruto,1);
assert.equal(api.filtered(intake.records,reg,'ALL','').length,30);
assert.equal(api.filtered(intake.records,reg,'naruto','').length,1);
assert.equal(api.filtered(intake.records,reg,'ALL','OP-01').some(r=>r.game_id==='onepiece'),true);
let all=[];
for(let i=0;i<5;i++)all.push(...api.paginate(intake.records,i).rows.map(r=>r.game_id));
assert.equal(new Set(all).size,30);
assert.equal(api.paginate(intake.records,5).current,4);
let corrupt=JSON.parse(JSON.stringify(intake));
corrupt.records[0].status='VERIFIED';
assert.equal(api.validIntake(corrupt,reg),false);
corrupt=JSON.parse(JSON.stringify(intake));
corrupt.records[1].game_id=corrupt.records[0].game_id;
assert.equal(api.validIntake(corrupt,reg),false);
"""
        run = subprocess.run([NODE, "-e", script], cwd=ROOT, capture_output=True,
                             text=True, check=False, timeout=15)
        self.assertEqual(0, run.returncode, run.stdout+"\n"+run.stderr)

if __name__ == "__main__":
    unittest.main(verbosity=2)
