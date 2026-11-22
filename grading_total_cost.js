(()=>{
'use strict';
const $=id=>document.getElementById(id);
const COMPANIES=['PSA','BGS','CGC','TAG','BRG'];
let official={},proxies=[],usdKrw=0,fxObservation=null,loadEpoch=0;
const krw=n=>Number.isFinite(Number(n))?`₩${Math.round(Number(n)).toLocaleString('ko-KR')}`:'-';
const norm=s=>typeof s==='string'?s.normalize('NFKC').trim().toLowerCase().replace(/\s+/g,' '):'';
const MAX_COST_KRW=1_000_000_000_000;
function costNumber(value){return typeof value==='number'&&Number.isFinite(value)&&value>0&&value<=MAX_COST_KRW?value:NaN}
function enteredNumber(value){
 if(typeof value==='string'){const text=value.trim();if(!text||text.length>32||!/^(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$/.test(text))return NaN;value=Number(text)}
 return typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=MAX_COST_KRW?value:NaN;
}
function availableService(row){return row&&typeof row==='object'&&!Array.isArray(row)&&typeof row.name==='string'&&row.name.trim()&&(row.availability===undefined||row.availability==='open')}
function selectedProxy(){
 const route=$('gtcRoute')?.value,company=$('gtcCompany')?.value;
 if(typeof route!=='string'||!/^proxy:(0|[1-9][0-9]*)$/.test(route))return null;
 const index=Number(route.slice(6));
 if(!Number.isSafeInteger(index)||index>=proxies.length||!COMPANIES.includes(company))return null;
 const row=proxies[index];return row&&typeof row==='object'&&!Array.isArray(row)&&row.grader===company?row:null;
}
function verifiedUsdRate(snapshot){
 // Reuse the same provenance, numeric and clock policy as the market UI.
 if(typeof fxTimestampFresh!=='function'||typeof verifiedFxSource!=='function'||typeof numericFxRate!=='function')return 0;
 if(!snapshot||typeof snapshot!=='object'||Array.isArray(snapshot)||snapshot.base!=='KRW'
    ||!snapshot.rates||typeof snapshot.rates!=='object'||Array.isArray(snapshot.rates)
    ||!verifiedFxSource(snapshot.source,snapshot.source_route)
    ||!fxTimestampFresh(snapshot.updated_at)||!fxTimestampFresh(snapshot.source_timestamp))return 0;
 return numericFxRate(snapshot.rates.USD_KRW,500,3000);
}
function toKrw(fee,currency){
 const n=costNumber(fee);
 if(!Number.isFinite(n))return 0;
 usdKrw=verifiedUsdRate(fxObservation);
 const result=currency==='KRW'?n:(currency==='USD'&&usdKrw?n*usdKrw:0);
 return Number.isFinite(result)&&result>0&&result<=MAX_COST_KRW?Math.round(result):0;
}
function predictedGrade(company){
 if(!COMPANIES.includes(company))return NaN;
 const raw=window.tcgLastGrades?.[company];
 if(typeof raw!=='number'&&!(typeof raw==='string'&&raw.length<=16&&/^\s*(?:[1-9](?:\.5|\.0)?|10(?:\.0)?)\s*$/.test(raw)))return NaN;
 const grade=Number(raw);
 return Number.isFinite(grade)&&grade>=1&&grade<=10&&Number.isInteger(grade*2)
   &&!(company==='PSA'&&!Number.isInteger(grade))&&!(company==='TAG'&&grade===9.5)?grade:NaN;
}
function expectedSale(company,grade){
 // Existing economics supports integer grades only. Never borrow grade 9/10
 // prices for a measured 9.5, or manufacture a grade before both-side analysis.
 if(!COMPANIES.includes(company)||!Number.isInteger(grade)||grade<1||grade>10)return 0;
 const c=$('econCompany'),g=$('econGrade');
 if(!c||!g||typeof renderEconomics!=='function')return 0;
 const oc=c.value,og=g.value;
 try{
  c.value=company;g.value=String(grade);
  if(c.value!==company||g.value!==String(grade))return 0;
  const value=renderEconomics()?.expectedSale;
  return typeof value==='number'&&Number.isFinite(value)&&value>0?value:0;
 }catch(_){return 0}
 finally{
  c.value=oc;g.value=og;
  try{renderEconomics()}catch(_){} // Restore the visible economics scenario too.
 }
}
function mount(){if($('gradingTotalCostPanel'))return true;const anchor=$('gradingProxyPanel')||$('gradingCostPanel')||$('autoGradeMarketFlow')||$('gradingEconomics');if(!anchor)return false;const s=document.createElement('section');s.id='gradingTotalCostPanel';s.className='card grading-total-panel';s.innerHTML=`<div class="gtc-head"><div><h3>🧾 총 예상비용 · 예상 순이익</h3><p>공식 감정비 + 대행비 + 실제 배송·보험/기타비용을 합산하고 예상 판매가와 비교합니다.</p></div><span class="gtc-badge">AUTO</span></div>
<div class="gtc-grid"><label>등급사<select id="gtcCompany">${COMPANIES.map(x=>`<option>${x}</option>`).join('')}</select></label><label>공식 서비스<select id="gtcService"></select></label><label>접수 방법<select id="gtcRoute"><option value="direct">직접 접수</option></select></label><label>추가 배송·보험/기타비용<input id="gtcExtra" type="number" min="0" step="1000" value="0" inputmode="numeric"><small>실제 결제금액 입력 · 대행가격에 포함이면 0원</small></label><label id="gtcQuoteWrap" hidden>대행사 견적 총액<input id="gtcQuote" type="number" min="0" step="1000" value="0" inputmode="numeric"><small>동적 견적 업체만 입력</small></label></div>
<div class="gtc-summary"><div><span>예상등급</span><b id="gtcGrade">-</b></div><div><span>기본 감정/대행비</span><b id="gtcBase">-</b></div><div><span>총 예상비용</span><b id="gtcTotal">-</b></div><div><span>등급 후 예상판매가</span><b id="gtcSale">-</b></div><div class="gtc-profit"><span>예상 순이익</span><b id="gtcProfit">-</b></div></div><div id="gtcNote" class="gtc-note"></div>`;anchor.insertAdjacentElement('afterend',s);['gtcCompany','gtcService','gtcRoute','gtcExtra','gtcQuote'].forEach(id=>$(id)?.addEventListener('input',()=>{if(id==='gtcCompany'){syncServices();syncRoutes()}else if(id==='gtcRoute')syncQuote();calc()}));return true}
async function load(){
 const epoch=++loadEpoch;
 try{
  const read=async url=>{const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw new Error('cost inputs HTTP');return response.json()};
  const [a,b,x]=await Promise.all([
   read('/api/grading-costs?t='+Date.now()),read('/api/grading-proxy-costs?t='+Date.now()),read('exchange_rates.json?t='+Date.now())
  ]);
  // A slow older request cannot reinstate a quote withdrawn by a later one.
  if(epoch!==loadEpoch)return;
  official=a.companies&&typeof a.companies==='object'&&!Array.isArray(a.companies)?a.companies:{};
  proxies=Array.isArray(b.providers)?b.providers:[];
  fxObservation=x;usdKrw=verifiedUsdRate(fxObservation);syncServices();syncRoutes();calc();
 }catch(_){
  if(epoch!==loadEpoch)return;
  official={};proxies=[];fxObservation=null;usdKrw=0;syncServices();syncRoutes();calc();
  if($('gtcNote'))$('gtcNote').textContent='서버 연결 후 최신 감정비·대행비·환율을 불러올 수 있습니다.';
 }
}

function syncServices(){
 const c=$('gtcCompany')?.value||'PSA',sel=$('gtcService');if(!sel)return;
 const source=official[c]?.services,rows=Array.isArray(source)?source.filter(availableService):[];
 const prev=sel.value;
 sel.innerHTML=rows.map(x=>`<option value="${x.name}">${x.name}</option>`).join('')||'<option value="">공식요금 확인 필요</option>';
 if(rows.some(x=>x.name===prev))sel.value=prev;
}
function syncRoutes(){const c=$('gtcCompany')?.value||'PSA',sel=$('gtcRoute');if(!sel)return;const prev=sel.value;sel.innerHTML='<option value="direct">직접 접수</option>'+proxies.filter(x=>x&&typeof x==='object'&&!Array.isArray(x)&&x.grader===c).map(p=>`<option value="proxy:${proxies.indexOf(p)}">대행 · ${p.provider}</option>`).join('');if([...sel.options].some(o=>o.value===prev))sel.value=prev;syncQuote()}
function syncQuote(){const p=selectedProxy();if($('gtcQuoteWrap'))$('gtcQuoteWrap').hidden=p?.pricing_type!=='dynamic_quote'}
function serviceFee(){
 const c=$('gtcCompany')?.value,name=$('gtcService')?.value,cfg=official[c]||{},rows=cfg.services;
 const matches=COMPANIES.includes(c)&&typeof name==='string'&&name.trim()&&Array.isArray(rows)?rows.filter(x=>availableService(x)&&x.name===name):[];
 const svc=matches.length===1?matches[0]:null;
 return {krw:toKrw(svc?.fee,cfg.currency),svc,cfg};
}
function routeBase(){
 const direct=serviceFee(),route=$('gtcRoute')?.value;
 if(route==='direct')return {amount:direct.krw,label:'공식 감정비',complete:direct.krw>0};
 const p=selectedProxy();
 if(!p)return {amount:0,label:'대행정보 확인 필요',complete:false};
 if(p.pricing_type==='total_service_price'){
  // Different service tiers cannot stand in for the selected one. Preserve
  // meaningful name punctuation and reject ambiguous duplicate matches.
  const wanted=norm($('gtcService')?.value),rows=p.services;
  const matches=direct.svc&&wanted&&Array.isArray(rows)?rows.filter(x=>availableService(x)&&norm(x.name)===wanted):[];
  const amount=matches.length===1?costNumber(matches[0].price_krw):NaN;
  return {amount:Number.isFinite(amount)?amount:0,label:`${p.provider} 공개 총 대행가격`,complete:Number.isFinite(amount)};
 }
 if(p.pricing_type==='proxy_fee_plus_actual'){
  const fee=costNumber(p.proxy_fee_from_krw),amount=direct.krw+fee;
  // A published 'from' fee is a lower bound, never a confirmed final bill.
  return {amount:direct.krw>0&&Number.isFinite(fee)&&amount<=MAX_COST_KRW?amount:0,label:`공식 감정비 + ${p.provider} 최소 대행수수료 · 최종 견적 확인 필요`,complete:false};
 }
 if(p.pricing_type==='dynamic_quote'){
  const amount=enteredNumber($('gtcQuote')?.value);
  return {amount:Number.isFinite(amount)?amount:0,label:`${p.provider} 실제 견적 총액`,complete:Number.isFinite(amount)&&amount>0};
 }
 return {amount:0,label:'대행가격 유형 확인 필요',complete:false};
}

function calc(){
 if(!$('gradingTotalCostPanel'))return;
 usdKrw=verifiedUsdRate(fxObservation);
 const c=$('gtcCompany')?.value||'PSA',g=predictedGrade(c),base=routeBase();
 const extra=enteredNumber($('gtcExtra')?.value),buy=enteredNumber($('econBuy')?.value),feePct=enteredNumber($('econSellingFee')?.value);
 const inputsValid=[extra,buy,feePct].every(Number.isFinite)&&extra>=0&&buy>=0&&feePct>=0&&feePct<=40;
 const total=base.amount+extra,sale=expectedSale(c,g);
 const ready=base.complete&&Number.isFinite(base.amount)&&base.amount>0&&Number.isFinite(total)&&total<=MAX_COST_KRW&&inputsValid;
 const profit=ready&&sale>0?sale*(1-feePct/100)-buy-total:NaN;
 $('gtcGrade').textContent=Number.isFinite(g)?`${c} ${g}`:'앞·뒷면 분석 대기';
 $('gtcBase').textContent=base.complete?krw(base.amount):'견적/요금 확인 필요';
 $('gtcTotal').textContent=ready?krw(total):'계산 대기';
 $('gtcSale').textContent=sale>0?krw(sale):'해당 등급 거래자료 없음';
 $('gtcProfit').textContent=Number.isFinite(profit)?krw(profit):'계산 대기';
 $('gtcProfit').className=Number.isFinite(profit)?(profit>=0?'plus':'minus'):'';
 const rate=usdKrw?`USD/KRW ${usdKrw.toLocaleString('ko-KR')} · ${fxObservation.source_timestamp.slice(0,10)} 관측`:'환율 미확인';
 $('gtcNote').textContent=`${base.label} · ${rate} · 배송/보험처럼 실제 결제 시 달라지는 비용은 위 추가비용 칸의 실제 금액을 사용합니다. 총 대행가격은 공식 감정비와 중복 합산하지 않습니다.`;
}

let calcTimer=0;
function startCalcTimer(){if(calcTimer||document.hidden)return;calcTimer=setInterval(calc,1000)}
function stopCalcTimer(){if(calcTimer){clearInterval(calcTimer);calcTimer=0}}
function boot(){let tries=0;const t=setInterval(()=>{tries++;if(mount()||tries>20)clearInterval(t)},250);mount();load();startCalcTimer();document.addEventListener('visibilitychange',()=>{if(document.hidden)stopCalcTimer();else{calc();startCalcTimer()}})}
if(typeof window.addEventListener==='function')window.addEventListener('tcg-fx-updated',()=>load());
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
