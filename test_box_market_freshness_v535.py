#!/usr/bin/env python3
"""V535: stale/unknown BOX prices never masquerade as recent market activity."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class RecentBoxMarketEvidenceV535(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "box_knowledge_stats.js").read_text(encoding="utf-8")

    def test_both_trading_surfaces_and_hot_use_same_gate(self):
        self.assertIn("const RECENT_MARKET_DAYS=14;", self.source)
        self.assertIn("!recentVerifiedMarketSignal(v))continue", self.source)
        self.assertIn("if(recentVerifiedMarketSignal(v))trading.add(k)", self.source)
        self.assertIn("!recentVerifiedMarketSignal(row))return false", self.source)
        self.assertIn("최근 14일 시세 확인", self.source)
        self.assertNotIn("if(priced(v))trading.add(k)", self.source)

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for runtime verification")
    def test_actual_javascript_rejects_stale_future_unknown_and_unverified(self):
        src = self.source
        helpers = src[src.index("function parseDate("):src.index("function ensureGameToolbar(")]
        age = src[src.index("function daysOld("):src.index("function freshnessPoints(")]
        setup = """
const priced=v=>{const d=String(v?.display||'').trim();return !!d&&!/가격 확인 중|확인 중|미정/.test(d)};
function countryOfKey(k){return String(k||'').split('|')[0]||''}
function assetOfKey(k){return String(k||'').split('|')[2]||''}
function nameOfKey(k){return String(k||'').split('|')[1]||''}
function uniqueKey(c,n){return String(c)+'|'+String(n||'').trim().toLowerCase()}
"""
        cases = """
function dateAt(delta) {
 const d = new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()+delta);
 return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
}
const good={display:'₩63,000',source_date:dateAt(-1),source:'https://pokard.io/',link_status:'정상'};
const examples={
 good:recentVerifiedMarketSignal(good),
 boundary:recentVerifiedMarketSignal({...good,source_date:dateAt(-14)}),
 stale:recentVerifiedMarketSignal({...good,source_date:dateAt(-15)}),
 veryOld:recentVerifiedMarketSignal({...good,source_date:'2020-01-01'}),
 unknown:recentVerifiedMarketSignal({...good,source_date:''}),
 malformed:recentVerifiedMarketSignal({...good,source_date:'2026-02-31'}),
 future:recentVerifiedMarketSignal({...good,source_date:dateAt(1)}),
 networkError:recentVerifiedMarketSignal({...good,link_status:'네트워크 지연'}),
 badProtocol:recentVerifiedMarketSignal({...good,source:'http://pokard.io/'}),
 credentials:recentVerifiedMarketSignal({...good,source:'https://user:pass@pokard.io/'}),
 noPrice:recentVerifiedMarketSignal({...good,display:'가격 확인 중'}),
 noLink:recentVerifiedMarketSignal({...good,source:''}),
 boxOnly:[...marketTradingSet({'KR|fresh|BOX':good,'KR|old|BOX':{...good,source_date:dateAt(-90)},'KR|hit|HIT':good})].join(',')==='KR|fresh',
};
console.log(JSON.stringify(examples));
"""
        proc = subprocess.run(
            ["node", "-e", setup + helpers + "\n" + age + "\n" + cases],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        for field in ("good", "boundary", "boxOnly"):
            self.assertTrue(result[field], field)
        for field in ("stale", "veryOld", "unknown", "malformed", "future",
                      "networkError", "badProtocol", "credentials", "noPrice", "noLink"):
            self.assertFalse(result[field], field)

    @unittest.skipUnless(shutil.which("node"), "Node.js syntax checker unavailable")
    def test_source_syntax(self):
        subprocess.run(["node", "--check", str(ROOT / "box_knowledge_stats.js")],
                       check=True, timeout=15)



    @unittest.skipUnless(shutil.which("node"), "Node.js required for V572 BOX pricing")
    def test_box_observed_price_and_sale_reference_v572(self):
        js = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('box_knowledge_stats.js','utf8');
const addon=src.slice(src.lastIndexOf('/* V572: BOX observed price bounds'));
assert.ok(addon.startsWith('/* V572:'),'V572 pricing engine missing');
const context={window:{addEventListener(){}},document:{readyState:'loading',addEventListener(){}},URL,Date,Set,Math,Object,Number,Intl,Array,String,RegExp};
vm.runInNewContext(addon,context,{timeout:1500});
const engine=context.window.TCGBoxPriceProofV572;
assert.ok(engine);
const now=Date.UTC(2026,9,15,8),key='JP|메가 심포니아|BOX',base={game:'Pokémon',display:'₩37,000',source_date:'2026-10-08',link_status:'정상',source:'https://pokard.io/'};
let result=engine.evaluate(key,'Pokémon',base,now);
assert.equal(result.low,37000);assert.equal(result.high,37000);assert.equal(result.recommended,null);
assert.equal(result.sources,1);assert.equal(result.status,'HOLD');
result=engine.evaluate('KR|블랙볼트|BOX','Pokémon',{...base,display:'₩50,000~₩58,000',source:'https://kream.co.kr/products/627575'},now);
assert.equal(result.low,50000);assert.equal(result.high,58000);assert.equal(result.recommended,null);
assert.equal(engine.legacy('¥25,000'),null);
assert.equal(engine.legacy('₩1,000/8BOX'),null);
const sale=(id,n,price)=>({product_key:key,game:'Pokémon',unit:'BOX',sealed:true,unit_quantity:1,currency:'KRW',verification_status:'verified',price_krw:price,observed_at:'2026-10-15',reviewed_at:'2026-10-15',review_status:'manual_verified',review_method:'source_page_crosscheck',source_id:id,source_url:id==='ebay'?'https://www.ebay.com/itm/12345678901':'https://kream.co.kr/products/42',lineage_key:id+':'+n,evidence_type:'completed_sale',sale_id:id==='ebay'?'ebay:12345678901':id+':'+n,transaction_finality:'sold'});
const a=sale('ebay','123',30000),b=sale('kream','456',50000);
result=engine.evaluate(key,'Pokémon',{game:'Pokémon',box_price_evidence:[a,b]},now);
assert.equal(result.recommended,40000);assert.equal(result.low,30000);assert.equal(result.high,50000);assert.equal(result.status,'REFERENCE');
const checkHold=(rows)=>assert.equal(engine.evaluate(key,'Pokémon',{game:'Pokémon',box_price_evidence:rows},now).recommended,null);
checkHold([a,{...b,product_key:'JP|wrong|BOX'}]);
checkHold([a,{...b,game:'ONE PIECE'}]);
checkHold([a,{...a,lineage_key:'ebay:other'}]);
checkHold([a,{...b,observed_at:'2026-08-15'}]);
checkHold([a,{...b,observed_at:'2026-10-16'}]);
checkHold([a,{...b,source_url:'https://kream.co.kr.evil.example'}]);
checkHold([a,{...b,currency:'JPY'}]);
checkHold([a,{...b,unit_quantity:8}]);
checkHold([a,{...b,sealed:false}]);
checkHold([a,{...b,evidence_type:'asking'}]);
checkHold([a,{...b,verification_status:'unverified'}]);
checkHold([a,{...b,price_krw:NaN}]);
checkHold([a,{...b,transaction_finality:'for_sale'}]);
checkHold([a,{...b,review_status:'unverified'}]);
checkHold([a,{...b,reviewed_at:'2026-10-16'}]);
checkHold([a,{...b,review_method:'search_snippet'}]);
checkHold([a,{...b,sale_id:'ebay:arbitrary',source_id:'ebay'}]);
checkHold([a,{...b,sale_id:a.sale_id}]);
assert.equal(engine.evaluate(key,'ONE PIECE',{game:'Pokémon',box_price_evidence:[a,b]},now).recommended,null);
assert.equal(engine.evaluate('KR|히로인즈 에디션 8BOX|BOX','Pokémon',{...base,game:'Pokémon'},now).low,null);
assert.equal(engine.evaluate(key,'Pokémon',{...base,source_date:'2026-02-31'},now).low,null);
assert.equal(engine.evaluate(key,'Pokémon',{...base,source_date:'2026-01-01'},now).low,null);
console.log('V572 VERIFIED: 28 independent checks');
"""
        result = subprocess.run(["node", "-e", js], cwd=ROOT, capture_output=True,
                                text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("V572 VERIFIED", result.stdout)

    def test_box_price_ui_v572_is_readable_and_fail_closed(self):
        css = (ROOT / "box_knowledge_stats.css").read_text(encoding="utf-8")
        for token in ("관측 최저가", "관측 최고가", "판매추천가",
                      "판매추천가 보류", "box_price_evidence",
                      "전체 시장의 최저/최고가 아님", "boxm-quote"):
            self.assertIn(token, self.source)
        for token in (".boxm-prices", "grid-template-columns",
                      "min-width:0", "word-break:keep-all"):
            self.assertIn(token, css)
        self.assertIn('<script src="box_knowledge_stats.js">', (ROOT / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
