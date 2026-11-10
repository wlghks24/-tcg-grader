"""Deterministic tests of actual UI declarations; no UI, network or learning run."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('node'), 'Node.js required')
class MarketInputsV1001Tests(unittest.TestCase):
    def run_js(self, names, script):
        page = (ROOT / 'index.html').read_text(encoding='utf-8')
        parts = []
        for name in names:
            match = re.search(r'(?:^|\n)((?:async )?function ' + name + r'\([^\n]*[\s\S]*?)(?=\n(?:function |async function |[A-Za-z\[]))', page)
            self.assertIsNotNone(match, name)
            parts.append(match.group(1))
        result = subprocess.run(['node', '-e', "const assert=require('node:assert/strict');\n" + '\n'.join(parts) + script], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr[-2500:])

    def test_grade_prices_need_exact_completed_sale_provenance_and_fresh_day(self):
        self.run_js(['finiteMoney', 'normalizeGradePrices', 'evidencedGradePrices'], r'''
const now=Date.parse('2026-11-10T00:30:00+09:00');
const p={grade_prices_krw:{PSA:{10:100000,9:50000}}};
assert.equal(evidencedGradePrices(p,'PSA',now)[10],0);
const e={source:'https://example.com/sold/1',price_type:'sold',observed_on:'2026-11-10'};
p.grade_price_evidence={PSA:{10:e}};
assert.equal(evidencedGradePrices(p,'PSA',now)[10],100000);
assert.equal(evidencedGradePrices(p,'PSA',now)[9],0);
for(const extra of [{source:'javascript:alert(1)'},{source:'http://example.com'}, {price_type:'asking'}, {price_type:'market_guide'}, {observed_on:'2026-11-11'}, {observed_on:'2026-11-02'}, {observed_on:'invalid'}, {observed_on:'2026-02-30'}, {observed_on:''}]){
 p.grade_price_evidence.PSA[10]={...e,...extra};assert.equal(evidencedGradePrices(p,'PSA',now)[10],0,JSON.stringify(extra));
}
p.grade_price_evidence.PSA[10]={...e,observed_on:'2026-11-03',price_type:'auction_result'};
assert.equal(evidencedGradePrices(p,'PSA',now)[10],100000);
''')

    def test_apply_profile_rejects_legacy_grade_auto_fill_but_manual_scenarios_work(self):
        self.run_js(['finiteMoney', 'normalizeGradePrices', 'evidencedGradePrices', 'applyEconomicsProfile', 'calculateGradingEconomics'], r'''
const GRADING_COMPANIES=['PSA','BGS','CGC','TAG','BRG'];
const popularityMarketEntries={k:{card_name:'Card',display:'',kind:'PSA10'}},gradedPriceProfiles={k:{grade_prices_krw:{PSA:{10:999999}}}};
let economicsPriceBook={},rendered=0;
const nodes={econCard:{value:'k'},econRaw:{value:0},econSource:{textContent:''}},document={getElementById:id=>nodes[id]};
const marketAmountKrw=()=>0,renderGradePriceInputs=()=>{},renderEconomics=()=>{rendered++};
applyEconomicsProfile();assert.equal(economicsPriceBook.PSA[10],0);assert.equal(rendered,1);
assert.match(nodes.econSource.textContent,/직접 입력은 가정 시나리오/);
assert.equal(calculateGradingEconomics({prices:{10:100000},grade:10,gradingFee:50000}).expectedProfit,50000);
''')

    def test_fx_expiry_tracks_oldest_actual_observation_not_refresh_clock(self):
        self.run_js(['fxTimestampFresh','loadExchangeRates','clearExpiredFx'], r'''
const FX_MAX_AGE_MS=72*3600000,FX_MAX_FUTURE_SKEW_MS=6*3600000;
let clock=Date.parse('2026-11-10T12:00:00Z');Date.now=()=>clock;
let fxExpiryTimer=null,fxRates={},fxUpdated='',fxTimestamp='',expired=0;
const clearFxConversionDisplay=()=>{expired++},renderCountryAnalysis=()=>{},renderTradeCatalog=()=>{},notifyMarketFx=()=>{};
const scheduleFxExpiry=()=>{};
let payload={updated_at:new Date(clock).toISOString(),source_timestamp:new Date(clock-71*3600000).toISOString(),rates:{USD_KRW:1400,JPY_KRW:9,EUR_KRW:1500}};
const fetch=async()=>({ok:true,json:async()=>payload});
(async()=>{
 assert.equal((await loadExchangeRates()).ok,true);assert.equal(fxTimestamp,payload.source_timestamp);
 clock+=2*3600000;assert.equal(clearExpiredFx(),true);assert.equal(fxRates.USD_KRW,0);
 payload.updated_at=new Date(clock).toISOString();assert.equal((await loadExchangeRates()).ok,false);
 for(const stamp of ['',null,'invalid',new Date(clock+7*3600000).toISOString()]){
  payload.source_timestamp=stamp;assert.equal((await loadExchangeRates()).ok,false);
 }
 payload.source_timestamp=new Date(clock).toISOString();payload.updated_at=new Date(clock-10*3600000).toISOString();
 assert.equal((await loadExchangeRates()).ok,true);assert.equal(fxTimestamp,payload.updated_at);
 delete payload.source_timestamp;assert.equal((await loadExchangeRates()).ok,true);assert.match(fxUpdated,/관측일 미제공/);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


if __name__ == '__main__':
    unittest.main()
