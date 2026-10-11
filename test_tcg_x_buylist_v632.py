#!/usr/bin/env python3
"""V632 tablet UI and Python query-generation parity across all 90 scopes."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

import tcg_x_buylist_search_v631 as py

ROOT=Path(__file__).resolve().parent
NODE=shutil.which("node")


class XBuylistTabletV632(unittest.TestCase):
    def test_usable_tablet_page_has_link_and_clear_evidence_labels(self):
        html=(ROOT/"tcg_x_buylist_v632.html").read_text(encoding="utf-8")
        js=(ROOT/"tcg_x_buylist_v632.js").read_text(encoding="utf-8")
        candidate=(ROOT/"tcg_30_game_catalog_v629.html").read_text(encoding="utf-8")
        official=(ROOT/"official_box_catalog_v626.html").read_text(encoding="utf-8")
        for page in (candidate,official):self.assertIn("tcg_x_buylist_v632.html",page)
        for dom_id in ("xGame","xRegion","xKind","xRarity","xQuery","xOpen","xStatus","xCoverage"):
            self.assertIn('id="'+dom_id+'"',html)
        self.assertIn('Content-Security-Policy',html)
        self.assertIn("실제 매장 매입 확정가",html)
        self.assertIn("tcg_game_registry.json",js)
        self.assertIn('id="xBroad"',html)
        self.assertIn("excludeNoise",js)
        self.assertNotIn(".innerHTML",js)
        self.assertNotIn("api.x.com",js)
        self.assertNotIn("localStorage",js)
        self.assertIn('textContent',js)

    @unittest.skipUnless(NODE,"node unavailable")
    def test_js_registry_and_all_90_market_queries(self):
        script=r"""
const assert=require('node:assert/strict');
const x=require('./tcg_x_buylist_v632.js');
const registry=require('./tcg_game_registry.json');
assert.equal(x.validRegistry(registry),true);
const cases=[];
for(const g of registry.games)for(const region of ['JP','KR','US']){
 const q=x.query(g,region,'card','');
 const box=x.query(g,region,'box','');
 assert.match(q,/filter:images/);
 assert.match(box,/filter:images/);
 assert.equal(q.includes('price is confirmed'),false);
 assert.equal(x.url(q).startsWith('https://x.com/search?q='),true);
 cases.push({id:g.id,region,q,box});
}
assert.equal(cases.length,90);
assert.equal(x.query(registry.games[0],'JP','card','SAR').includes('SAR'),true);
assert.equal(x.query(registry.games[0],'JP','card','').includes('SAR'),false);
assert.equal(x.query(registry.games[0],'KR','box','').includes('미개봉'),true);
assert.equal(x.query(registry.games[0],'US','card','').includes('buylist'),true);
assert.equal(x.query(registry.games[0],'JP','card','',true,false).includes('-販売'),false);
assert.equal(x.query(registry.games[0],'JP','card','',true,true).includes('-販売'),true);
assert.throws(()=>x.query(registry.games[0],'US','box','SIR'));
assert.throws(()=>x.query(registry.games[0],'US','card','lang:ja'));
process.stdout.write(JSON.stringify(cases));
"""
        r=subprocess.run([NODE,"-e",script],cwd=ROOT,capture_output=True,text=True,timeout=20,check=False)
        self.assertEqual(0,r.returncode,r.stdout[:300]+"\n"+r.stderr)
        rows=json.loads(r.stdout)
        self.assertEqual(90,len(rows))
        for row in rows:
            self.assertEqual(py.generate_twitter_query(row["id"],region=row["region"]),row["q"])
            self.assertEqual(py.generate_twitter_query(row["id"],region=row["region"],kind="box"),row["box"])

    @unittest.skipUnless(NODE,"node unavailable")
    def test_js_syntax(self):
        r=subprocess.run([NODE,"--check","tcg_x_buylist_v632.js"],
                         cwd=ROOT,capture_output=True,text=True,timeout=15,check=False)
        self.assertEqual(0,r.returncode,r.stderr)

if __name__=="__main__":unittest.main(verbosity=2)
