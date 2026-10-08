#!/usr/bin/env python3
"""V537: HOT rankings use the same verified observation date as activity gating."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class BoxHotObservationV537Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "box_knowledge_stats.js").read_text(encoding="utf-8")

    def test_rank_and_recency_use_the_same_observation(self):
        self.assertIn("const fresh=freshnessPoints(row?.market_observed_at||row?.source_date)", self.js)
        self.assertIn("daysOld(a.row?.market_observed_at||a.row?.source_date)", self.js)
        self.assertIn("daysOld(b.row?.market_observed_at||b.row?.source_date)", self.js)
        self.assertIn("!recentVerifiedMarketSignal(row))return false", self.js)
        self.assertNotIn("freshnessPoints(row.source_date)", self.js)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for executable regression")
    def test_observation_date_wins_over_old_source_date(self):
        src = self.js
        helpers = src[src.index("function parseDate("):src.index("function ensureGameToolbar(")]
        ranking = src[src.index("function daysOld("):src.index("function ensureHotUi(")]
        setup = """
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
function dateAt(delta){
  const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()+delta);
  return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
}
"""
        cases = """
const row=(observed,source)=>({
 display:'₩63,000',market_observed_at:dateAt(observed),source_date:dateAt(source),
 source:'https://pokard.io/',link_status:'정상',kind:'판매 호가',transactions:'표시가격 참고'
});
marketCache.entries={
 'JP|old source current observation|BOX':row(-1,-90),
 'JP|new source older observation|BOX':row(-12,-1),
 'JP|stale observation fresh source|BOX':row(-20,-1),
 'JP|future observation|BOX':row(1,-1),
 'JP|fallback source|BOX':{...row(-1,-2),market_observed_at:''}
};
const scored=hotRows('BOX');
const names=scored.map(x=>x.name);
console.log(JSON.stringify({
 top:names[0],
 excludedStale:!names.includes('stale observation fresh source'),
 excludedFuture:!names.includes('future observation'),
 fallback:names.includes('fallback source'),
 currentBetter:scored.find(x=>x.name==='old source current observation')?.score >
               scored.find(x=>x.name==='new source older observation')?.score
}));
"""
        run=subprocess.run(
            ["node", "-e", setup+helpers+"\n"+ranking+"\n"+cases],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=15,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        result=json.loads(run.stdout)
        self.assertEqual(result["top"], "old source current observation")
        for key in ("excludedStale","excludedFuture","fallback","currentBetter"):
            self.assertTrue(result[key], key)

    @unittest.skipUnless(shutil.which("node"), "Node.js not installed")
    def test_javascript_syntax(self):
        subprocess.run(["node","--check",str(ROOT/"box_knowledge_stats.js")],
                       cwd=ROOT, check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
