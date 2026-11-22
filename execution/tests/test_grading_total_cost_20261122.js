/* Offline DOM harness. It proves calculation/hold behavior, not device rendering. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ROOT=path.resolve(__dirname,'../..');
const original=fs.readFileSync(path.join(ROOT,'grading_total_cost.js'),'utf8');
const source=original.replace(/\}\)\(\);\s*$/, 'window.__cost={verifiedUsdRate,toKrw,predictedGrade,expectedSale,load,calc};\n})();');
assert.notEqual(source,original,'instrumentation requires the actual production closure');
const index=fs.readFileSync(path.join(ROOT,'index.html'),'utf8');
// Use the real shared policy. Mocking it would remove the provenance failure.
const policy=index.slice(index.indexOf('const FX_MAX_AGE_MS='),index.indexOf('function clearFxConversionDisplay('));
const HOUR=3600000;
const clock={now:Date.parse('2026-11-22T00:00:00Z')};
class ClockDate extends Date { constructor(...args){super(...(args.length?args:[clock.now]));}static now(){return clock.now;} }
const stamp=()=>new Date(clock.now).toISOString();
function snapshot(){return {base:'KRW',source:'https://api.frankfurter.dev/v2/rates?base=USD',source_route:'frankfurter-v2',updated_at:stamp(),source_timestamp:stamp(),rates:{USD_KRW:1400}};}
function fixture(){
 const nodes={},events={};
 for(const id of ['gradingTotalCostPanel','gtcCompany','gtcService','gtcRoute','gtcExtra','gtcQuote','gtcQuoteWrap','gtcGrade','gtcBase','gtcTotal','gtcSale','gtcProfit','gtcNote','econCompany','econGrade','econBuy','econSellingFee']){
  nodes[id]={value:'',textContent:'',innerHTML:'',className:'',hidden:false,options:[],addEventListener(){}};
 }
 Object.assign(nodes.gtcCompany,{value:'PSA'});Object.assign(nodes.gtcService,{value:'Basic'});Object.assign(nodes.gtcRoute,{value:'direct',options:[{value:'direct'}]});
 for(const id of ['gtcExtra','gtcQuote','econBuy','econSellingFee'])nodes[id].value='0';
 nodes.econCompany.value='CGC';nodes.econGrade.value='8';
 let payload=snapshot(),fail=false,throws=false,rendered='',calls=0;
 const context={document:{readyState:'loading',hidden:false,addEventListener(){},getElementById:id=>nodes[id]||null},window:{tcgLastGrades:{PSA:10,BGS:9.5},addEventListener:(name,callback)=>{events[name]=callback}},URL,Date:ClockDate,console,
 setInterval(){return 1},clearInterval(){},
 renderEconomics(){calls++;rendered=nodes.econCompany.value+' '+nodes.econGrade.value;if(throws)throw new Error('renderer failure');return {expectedSale:100000};},
 fetch:async url=>{if(fail)throw new Error('offline');return {ok:true,json:async()=>String(url).startsWith('/api/grading-costs')?{companies:{PSA:{currency:'USD',services:[{name:'Basic',fee:20}]}}}:String(url).startsWith('/api/grading-proxy-costs')?{providers:[]}:payload};}
 };
 vm.createContext(context);vm.runInContext(policy+'\n'+source,context,{timeout:2000});
 return {nodes,events,context,cost:context.window.__cost,setPayload:x=>payload=x,setFail:x=>fail=x,setThrow:x=>throws=x,rendered:()=>rendered,calls:()=>calls};
}
(async()=>{
 let cases=0;
 const f=fixture(),p=snapshot();
 assert.equal(f.cost.verifiedUsdRate(p),1400);cases++;
 for(const mutate of [x=>x.updated_at='2026-10-08T00:00:00Z',x=>x.source_timestamp='2026-10-08T00:00:00Z',x=>x.source_timestamp='2026-11-23T00:00:00Z',x=>delete x.source_timestamp,x=>x.source='https://evil.invalid/',x=>x.source='https://api.frankfurter.dev@evil.invalid/',x=>x.source_route='unknown',x=>x.base='USD',x=>x.rates.USD_KRW=true,x=>x.rates.USD_KRW='1400',x=>x.rates.USD_KRW=Infinity,x=>x.rates.USD_KRW=-1,x=>x.rates.USD_KRW=5000]){
  const bad=snapshot();mutate(bad);assert.equal(f.cost.verifiedUsdRate(bad),0);cases++;
 }
 const missing=fixture();vm.runInContext('verifiedFxSource=undefined',missing.context);assert.equal(missing.cost.verifiedUsdRate(p),0);cases++;
 for(const value of [null,undefined,'',true,0,-1,11,Infinity,'9e0',{},[],9.7]){f.context.window.tcgLastGrades.PSA=value;assert.ok(Number.isNaN(f.cost.predictedGrade('PSA')));cases++;}
 assert.equal(f.cost.predictedGrade('BGS'),9.5);assert.equal(f.cost.expectedSale('BGS',9.5),0);cases++;
 f.context.window.tcgLastGrades.TAG=9.5;assert.ok(Number.isNaN(f.cost.predictedGrade('TAG')));cases++;
 f.context.window.tcgLastGrades.PSA=10;
 await f.cost.load();
 assert.equal(f.cost.toKrw(20,'USD'),28000);assert.equal(f.nodes.gtcTotal.textContent,'₩28,000');assert.equal(f.nodes.gtcProfit.textContent,'₩72,000');cases++;
 f.nodes.econSellingFee.value='10';f.nodes.econBuy.value='10000';f.nodes.gtcExtra.value='2000';f.cost.calc();assert.equal(f.nodes.gtcProfit.textContent,'₩50,000');cases++;
 assert.equal(f.nodes.econCompany.value,'CGC');assert.equal(f.nodes.econGrade.value,'8');assert.equal(f.rendered(),'CGC 8');cases++;
 f.setThrow(true);assert.equal(f.cost.expectedSale('PSA',10),0);assert.equal(f.nodes.econCompany.value,'CGC');assert.equal(f.nodes.econGrade.value,'8');f.setThrow(false);cases++;
 f.nodes.gtcService.value='Missing';f.cost.calc();assert.equal(f.nodes.gtcProfit.textContent,'계산 대기');assert.equal(f.nodes.gtcTotal.textContent,'계산 대기');cases++;
 f.nodes.gtcService.value='Basic';
 for(const [id,value] of [['gtcExtra','-1000'],['econSellingFee','101'],['econBuy','not-a-number']]){const before=f.nodes[id].value;f.nodes[id].value=value;f.cost.calc();assert.equal(f.nodes.gtcProfit.textContent,'계산 대기');f.nodes[id].value=before;cases++;}
 const before=clock.now;clock.now+=73*HOUR;f.cost.calc();assert.equal(f.cost.toKrw(20,'USD'),0);assert.equal(f.nodes.gtcProfit.textContent,'계산 대기');assert.ok(f.nodes.gtcNote.textContent.includes('환율 미확인'));clock.now=before;cases++;
 f.setPayload(snapshot());await f.cost.load();assert.notEqual(f.nodes.gtcProfit.textContent,'계산 대기');f.setFail(true);await f.cost.load();assert.equal(f.cost.toKrw(20,'USD'),0);assert.equal(f.nodes.gtcProfit.textContent,'계산 대기');cases++;
 for(const amount of [true,-1,Infinity,'20',NaN]){assert.equal(f.cost.toKrw(amount,'KRW'),0);cases++;}
 assert.equal(f.cost.toKrw(25000,'KRW'),25000);cases++;
 f.context.window.tcgLastGrades.PSA=null;f.cost.calc();assert.equal(f.nodes.gtcGrade.textContent,'앞·뒷면 분석 대기');assert.equal(f.nodes.gtcProfit.textContent,'계산 대기');cases++;
 // Shared FX refresh events reload fees/FX and recover only from valid new input.
 const refresh=fixture();await refresh.cost.load();
 refresh.setFail(true);await refresh.events['tcg-fx-updated']();
 assert.equal(refresh.cost.toKrw(20,'USD'),0);assert.equal(refresh.nodes.gtcProfit.textContent,'계산 대기');cases++;
 const recovered=snapshot();recovered.rates.USD_KRW=1500;refresh.setPayload(recovered);refresh.setFail(false);
 await refresh.events['tcg-fx-updated']();assert.equal(refresh.cost.toKrw(20,'USD'),30000);assert.equal(refresh.nodes.gtcProfit.textContent,'₩70,000');cases++;
 const stale=snapshot();stale.source_timestamp='2026-10-08T00:00:00Z';refresh.setPayload(stale);
 await refresh.events['tcg-fx-updated']();assert.equal(refresh.cost.toKrw(20,'USD'),0);assert.equal(refresh.nodes.gtcProfit.textContent,'계산 대기');cases++;
 const flush=async()=>{for(let i=0;i<6;i++)await new Promise(setImmediate)};
 // Resolve an old successful request AFTER a newer failed refresh; no resurrection.
 const race=fixture(),realFetch=race.context.fetch;let release;
 const gate=new Promise(resolve=>{release=resolve});
 race.context.fetch=async url=>{const response=await realFetch(url),data=await response.json();await gate;return {ok:response.ok,json:async()=>data}};
 const oldSuccess=race.cost.load();await flush();
 race.context.fetch=realFetch;race.setFail(true);await race.events['tcg-fx-updated']();
 release();await oldSuccess;assert.equal(race.cost.toKrw(20,'USD'),0);assert.equal(race.nodes.gtcProfit.textContent,'계산 대기');cases++;
 // A late old failure cannot revoke a newer verified successful recovery.
 let rejectOld;
 race.context.fetch=async()=>new Promise((_,reject)=>{rejectOld=reject});
 const oldFailure=race.cost.load();await flush();race.context.fetch=realFetch;race.setFail(false);
 await race.events['tcg-fx-updated']();assert.equal(race.cost.toKrw(20,'USD'),28000);
 rejectOld(new Error('late failed response'));await oldFailure;
 assert.equal(race.cost.toKrw(20,'USD'),28000);assert.equal(race.nodes.gtcProfit.textContent,'₩72,000');cases++;
 // HTTP errors do not authorize otherwise plausible JSON fees/FX.
 race.context.fetch=async()=>({ok:false,json:async()=>snapshot()});await race.events['tcg-fx-updated']();
 assert.equal(race.cost.toKrw(20,'USD'),0);assert.equal(race.nodes.gtcProfit.textContent,'계산 대기');cases++;
 console.log(`PASS grading total cost: ${cases} deterministic scenarios (offline DOM; no physical device)`);
})().catch(error=>{console.error(error);process.exitCode=1;});
