#!/usr/bin/env python3
"""V540: HOT/trading evidence may not treat a date substring as a real observation."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JS = ROOT / "box_knowledge_stats.js"


class BoxStrictMarketDateV540(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = JS.read_text(encoding="utf-8")

    def test_market_observation_requires_exact_iso_day(self):
        block = self.source.split("function daysOld(", 1)[1].split(
            "function freshnessPoints(", 1
        )[0]
        self.assertIn(r"/^20\d{2}-\d{2}-\d{2}$/.test(source)", block)
        self.assertIn("if(!d||d.getTime()>today.getTime())return 9999", block)
        self.assertIn("!recentVerifiedMarketSignal(row))return false", self.source)
        self.assertIn("if(recentVerifiedMarketSignal(v))trading.add(k)", self.source)

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_actual_hot_and_trading_exclude_date_like_garbage(self):
        src = self.source
        helpers = src[src.index("function parseDate("):src.index("function ensureGameToolbar(")]
        ranking = src[src.index("function daysOld("):src.index("function ensureHotUi(")]
        setup = r"""
const assert=require('node:assert/strict');
const priced=v=>{const d=String(v?.display||'').trim();return !!d&&!/가격 확인 중|확인 중|미정/.test(d)};
function countryOfKey(k){return String(k||'').split('|')[0]||''}
function assetOfKey(k){return String(k||'').split('|')[2]||''}
function nameOfKey(k){return String(k||'').split('|')[1]||''}
function uniqueKey(c,n){return String(c)+'|'+String(n||'').trim().toLowerCase()}
function hotKey(c,n,a){return String(c)+'|'+String(n||'').trim().toLowerCase()+'|'+String(a)}
function marketGame(){return 'Pokémon'}
const document={getElementById:()=>null};
const watchCache={items:[]};
const marketCache={entries:{}};
function dateAt(delta) {
 const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()+delta);
 return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
}
"""
        cases = r"""
const valid=dateAt(-1),future=dateAt(1),boundary=dateAt(-14),old=dateAt(-15);
const good={game:'Pokémon',display:'₩63,000',source:'https://pokard.io/',link_status:'정상',
 source_date:valid,kind:'판매 호가',transactions:'표시가격 참고'};
const bad=[valid+'oops','prefix '+valid,valid+'T23:30:00Z','>'+valid,
  valid+' GMT','2026-02-31',future,old,'',null,0];
for(const date of bad) {
 assert.equal(recentVerifiedMarketSignal({...good,source_date:date}),false,String(date));
 assert.equal(daysOld(date),9999,String(date));
}
assert.equal(recentVerifiedMarketSignal(good),true);
assert.equal(recentVerifiedMarketSignal({...good,source_date:boundary}),true);
marketCache.entries={
 'JP|verified|BOX':good,
 'JP|suffix contamination|BOX':{...good,source_date:valid+'junk'},
 'JP|unknown observation|BOX':{...good,market_observed_at:'invalid'},
 'JP|unsupported timestamp|BOX':{...good,source_date:valid+'T10:00:00Z'},
 'JP|future listing|BOX':{...good,source_date:future}
};
const ranked=hotRows('BOX').map(x=>x.name);
assert.deepEqual(ranked,['verified']);
const trading=[...marketTradingSet(marketCache.entries)].sort();
assert.deepEqual(trading,['JP|verified']);
console.log(JSON.stringify({pass:true,rejected:bad.length,ranked,trading}));
"""
        run = subprocess.run(
            ["node", "-e", setup + helpers + "\n" + ranking + "\n" + cases],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        result = json.loads(run.stdout)
        self.assertTrue(result["pass"])
        self.assertEqual(result["rejected"], 11)

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_js_syntax(self):
        subprocess.run(["node", "--check", str(JS)], cwd=ROOT, check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
