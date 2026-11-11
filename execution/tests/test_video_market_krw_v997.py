"""Deterministic DOM-unit coverage for video-observed market display gaps.

No browser, service, live market calls, tablet writes or learning runs.
"""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('node'), 'Node.js required for JS DOM unit checks')
class VideoMarketKrwV997Tests(unittest.TestCase):
    def run_js(self, source, body):
        bootstrap = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
function node(tag){return {tag,children:[],textContent:'',className:'',innerHTML:'',style:{},
 append(...v){this.children.push(...v)},appendChild(v){this.children.push(v);return v},
 replaceChildren(...v){this.children=v},setAttribute(){},addEventListener(){},before(v){this.beforeNode=v}}}
function nodes(n){return [n,...n.children.flatMap(nodes)]}
'''
        result = subprocess.run(['node', '-e', bootstrap + '\nconst SOURCE=' + json.dumps(source) + ';\n' + body],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_hot_foreign_currency_uses_shared_fx_and_missing_rate_is_explicit(self):
        source = (ROOT / 'box_knowledge_stats.js').read_text(encoding='utf-8')
        source = source[source.index('function hotColumn('):source.index('function renderHot(')]
        self.run_js(source, r'''
const row={region:'US',name:'Exact product',score:45,row:{display:'$100',source:'https://example.com/item'},reasons:[]};
const c={document:{createElement:node,getElementById:()=>null},window:{tcgMarketFx:{format:q=>`<span class="krw-converted">KRW for ${q}</span>`}},hotRows:()=>[row],gameLabel:()=> '전체 게임'};
vm.createContext(c);vm.runInContext(SOURCE,c);
let output=c.hotColumn('HIT','HOT 카드');
assert.ok(nodes(output).some(x=>x.innerHTML.includes('KRW for $100')));
c.window.tcgMarketFx.format=()=>'';
output=c.hotColumn('BOX','HOT BOX');
assert.ok(nodes(output).some(x=>x.textContent.includes('원화 환산 대기')));
row.row.display='₩100,000';output=c.hotColumn('HIT','HOT 카드');
assert.ok(!nodes(output).some(x=>x.textContent.includes('원화 환산 대기')));
c.window.tcgMarketFx=undefined;row.row.display='¥1000';output=c.hotColumn('BOX','HOT BOX');
assert.ok(nodes(output).some(x=>x.textContent.includes('원화 환산 대기')));
''')

    def test_radar_stale_and_fx_changes_repaint_unchanged_quote(self):
        source = (ROOT / 'tablet_image_library_v1.js').read_text(encoding='utf-8')
        source = source.split('/* v4.7: private US-market opportunity research, no purchase action. */', 1)[1]
        source = source.split('/* TCG v4.8:', 1)[0]
        self.run_js(source, r'''
(async()=>{
 const created=[],events={},intervals=[],parent=node('parent');
 let fx='fresh',item={product_id:'p1',variant:'Normal',market_price_usd:100,checked_at:'2026-11-10T00:00:00Z',game_id:'pokemon',kind:'CARD',name:'Card',series:'S',stale:false};
 const payload=()=>({ok:true,summary:{registered_games:1,total:1,with_market_price:1},items:[{...item}]});
 const c={document:{hidden:false,head:node('head'),body:parent,createElement:tag=>{const n=node(tag);created.push(n);return n},getElementById:id=>id==='box12section'?parent:null,querySelector:()=>null,addEventListener(){}},
 window:{tcgMarketFx:{fingerprint:()=>fx,format:q=>fx==='fresh'?`<span class="krw-converted">KRW ${q}</span>`:''},addEventListener:(k,v)=>events[k]=v},
 Option:function(label,value){return {label,value}},URLSearchParams,fetch:async url=>({ok:true,json:async()=>String(url).startsWith('tcg_game_registry')?{games:[]}:payload()}),setInterval:fn=>intervals.push(fn),console};
 vm.createContext(c);vm.runInContext(SOURCE,c);
 const flush=async()=>{for(let i=0;i<5;i++)await new Promise(setImmediate)};await flush();
 const cards=created.find(x=>x.className==='radar-items');assert.ok(cards);
 assert.ok(nodes(cards).some(x=>x.innerHTML.includes('KRW $100.00')));
 assert.ok(!nodes(cards).some(x=>x.textContent.includes('갱신일 지남')));
 item.stale=true;await intervals[0]();await flush();
 assert.ok(nodes(cards).some(x=>x.textContent.includes('갱신일 지남')),'same quote must repaint its changed freshness flag');
 fx='expired';events['tcg-fx-updated']();await flush();
 assert.ok(nodes(cards).some(x=>x.textContent.includes('원화 환산 대기')));
 assert.ok(!nodes(cards).some(x=>x.innerHTML.includes('KRW $100.00')));
 item.market_price_usd=true;await intervals[0]();await flush();
 assert.ok(nodes(cards).some(x=>x.textContent==='가격 미확인'),'boolean is not a dollar price');
})().catch(e=>{console.error(e);process.exit(1)});
''')


if __name__ == '__main__':
    unittest.main()
