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

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_hot_sale_points_require_reviewed_exact_unique_sales(self):
        src = self.js
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
function dateAt(delta){
 const d=new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()+delta);
 return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
}
"""
        cases = r"""
const common={display:'₩9,000',market_observed_at:dateAt(-1),source_date:dateAt(-1),
 source:'https://www.ebay.com/itm/1234',link_status:'정상',kind:'판매완료 100건',
 transactions:'체결 999건',identity_key:'Pokemon|JP|001|NM|regular',
 verification_status:'verified',review_status:'manual_verified'};
const sale={sale_id:'ebay:12345678901',identity_key:common.identity_key,
 evidence_type:'completed_sale',transaction_finality:'sold',
 verification_status:'verified',review_status:'manual_verified',
 review_method:'source_page_crosscheck',currency:'JPY',price:1000,
 source_date:dateAt(-1),source:'https://www.ebay.com/itm/12345678901'};
const row={...common,verified_sales:[sale]};
assert.equal(evidencePoints(common),0,'text claiming 999 sales is not evidence');
assert.equal(evidencePoints({...common,transactions:'5000건 거래완료'}),0);
assert.equal(evidencePoints({...row,review_status:'pending'}),0);
assert.equal(evidencePoints({...row,verified_sales:[{...sale,identity_key:'another-card'}]}),0);
assert.equal(evidencePoints({...row,verified_sales:[{...sale,evidence_type:'asking'}]}),0);
assert.equal(evidencePoints({...row,verified_sales:[{...sale,transaction_finality:'listing'}]}),0);
assert.equal(evidencePoints({...row,verified_sales:[{...sale,source_date:dateAt(-40)}]}),0);
assert.equal(evidencePoints({...row,verified_sales:[{...sale,source_date:dateAt(1)}]}),0);
assert.equal(evidencePoints({...row,verified_sales:[{...sale,source:'http://example.com'}]}),0);
assert.equal(evidencePoints({...row,verified_sales:[{...sale,price:'1000'}]}),0);
assert.equal(evidencePoints({...row,verified_sales:[{...sale,review_status:'unreviewed'}]}),0);
assert.equal(evidencePoints({...row,verified_sales:[{...sale,currency:'unknown'}]}),0);
assert.equal(evidencePoints({...row,verified_sales:[sale,sale]}),2,'duplicate sale ID cannot inflate count');
assert.equal(evidencePoints(row),2,'one reviewed sale earns 2 activity points');
const rows6=Array.from({length:6},(_,i)=>({...sale,sale_id:'ebay:'+String(12345678901+i)}));
assert.equal(evidencePoints({...row,verified_sales:rows6}),12);
marketCache.entries={
 'JP|unreviewed text|BOX':common,
 'JP|reviewed sale|BOX':row
};
const ranked=hotRows('BOX');
const fake=ranked.find(x=>x.name==='unreviewed text'),good=ranked.find(x=>x.name==='reviewed sale');
assert.ok(fake&&good);
assert.ok(good.score>fake.score,'verified source evidence adds points');
assert.ok(!fake.reasons.some(x=>x.includes('검증 완료거래')),'unreviewed text cannot make verified badge');
assert.ok(good.reasons.some(x=>x.includes('검증 완료거래 1건')));
console.log(JSON.stringify({pass:true,checked:18,ranked:ranked.map(x=>x.name)}));
"""
        proc = subprocess.run(
            ["node", "-e", setup + helpers + "\n" + ranking + "\n" + cases],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertTrue(result["pass"])
        self.assertEqual(result["checked"], 18)

    @unittest.skipUnless(shutil.which("node"), "Node.js not installed")
    def test_javascript_syntax(self):
        subprocess.run(["node","--check",str(ROOT/"box_knowledge_stats.js")],
                       cwd=ROOT, check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
